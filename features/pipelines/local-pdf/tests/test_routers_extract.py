from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def app_with_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    import local_pdf.api.routers.extract as ext_mod
    import local_pdf.api.routers.segments as seg_mod
    from local_pdf.workers.mineru import MinerUResult
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox

    seg_mod._YOLO_PREDICT_FN = lambda _p: [
        YOLOPagePrediction(
            page=1,
            width=600,
            height=800,
            boxes=[
                YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
            ],
        )
    ]

    def fake_extract(_pdf, box):
        tag = "h1" if box.kind.value == "heading" else "p"
        return MinerUResult(
            box_id=box.box_id, html=f'<{tag} data-source-box="{box.box_id}">{box.box_id}</{tag}>'
        )

    ext_mod._MINERU_EXTRACT_FN = fake_extract

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    with client.stream("POST", "/api/docs/doc/segment", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    yield client, root, "doc"

    seg_mod._YOLO_PREDICT_FN = None
    ext_mod._MINERU_EXTRACT_FN = None


def test_extract_streams_worker_events_one_progress_per_box(app_with_segments) -> None:
    client, _, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        assert resp.status_code == 200
        lines = [json.loads(ln) for ln in resp.iter_lines() if ln]
    types = [ln["type"] for ln in lines]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    progress = [ln for ln in lines if ln["type"] == "work-progress"]
    assert len(progress) == 2  # two boxes
    assert progress[-1]["current"] == 2 and progress[-1]["total"] == 2
    assert types[-3] == "work-complete"
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"
    for ln in lines:
        assert ln["model"] == "MinerU 3"


def test_extract_persists_html_and_mineru_out(app_with_segments) -> None:
    client, root, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    assert (root / slug / "html.html").exists()
    assert (root / slug / "mineru-out.json").exists()
    html = (root / slug / "html.html").read_text(encoding="utf-8")
    assert 'data-source-box="p1-b0"' in html
    assert 'data-source-box="p1-b1"' in html


def test_extract_region_runs_one_box_only(app_with_segments) -> None:
    client, _root, slug = app_with_segments
    # First do a full extract so html exists.
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    resp = client.post(
        f"/api/docs/{slug}/extract/region",
        headers={"X-Auth-Token": "tok"},
        json={"box_id": "p1-b0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["box_id"] == "p1-b0"
    assert body["html"].startswith("<h1")


def test_extract_unknown_slug_404(app_with_segments) -> None:
    client, _, _ = app_with_segments
    resp = client.post("/api/docs/missing/extract", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_export_writes_sourceelements_and_marks_done(app_with_segments) -> None:
    client, root, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    resp = client.post(f"/api/docs/{slug}/export", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_pipeline"] == "local-pdf"
    assert (root / slug / "sourceelements.json").exists()
    meta = client.get(f"/api/docs/{slug}", headers={"X-Auth-Token": "tok"}).json()
    assert meta["status"] == "done"
