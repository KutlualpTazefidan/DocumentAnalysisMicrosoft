from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def app_with_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    # Inject fake YOLO predict_fn via a module-level hook on the segments router.
    import local_pdf.api.routers.segments as seg_mod
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox

    def fake_predict(_pdf):
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                    YOLOPredictedBox(
                        class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88
                    ),
                ],
            ),
            YOLOPagePrediction(
                page=2,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="table", bbox=(15, 30, 580, 700), confidence=0.91)
                ],
            ),
        ]

    seg_mod._YOLO_PREDICT_FN = fake_predict

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    yield client, root, "doc"

    seg_mod._YOLO_PREDICT_FN = None


def test_segment_streams_ndjson_and_persists(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        assert resp.status_code == 200
        lines = [json.loads(ln) for ln in resp.iter_lines() if ln]
    assert lines[0] == {"type": "start", "total_pages": 2}
    assert {ln["type"] for ln in lines} == {"start", "page", "complete"}
    assert lines[-1]["type"] == "complete"
    assert lines[-1]["boxes_total"] == 3

    seg_path = root / slug / "segments.json"
    assert seg_path.exists()
    payload = json.loads(seg_path.read_text(encoding="utf-8"))
    assert len(payload["boxes"]) == 3
    assert {b["page"] for b in payload["boxes"]} == {1, 2}


def test_segment_writes_yolo_json_immutable(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    assert (root / slug / "yolo.json").exists()


def test_get_segments_returns_persisted_boxes(app_with_doc) -> None:
    client, _, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    resp = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == slug
    assert len(body["boxes"]) == 3


def test_get_segments_404_when_not_yet_run(app_with_doc) -> None:
    client, _, slug = app_with_doc
    resp = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_segment_unknown_slug_404(app_with_doc) -> None:
    client, _, _ = app_with_doc
    resp = client.post("/api/docs/missing/segment", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404
