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


def test_segment_streams_worker_events_and_persists(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        assert resp.status_code == 200
        lines = [json.loads(ln) for ln in resp.iter_lines() if ln]
    types = [ln["type"] for ln in lines]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    assert "work-progress" in types
    assert "work-complete" in types
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"
    progress = [ln for ln in lines if ln["type"] == "work-progress"]
    assert progress[-1]["current"] == 2 and progress[-1]["total"] == 2
    complete = next(ln for ln in lines if ln["type"] == "work-complete")
    assert complete["items_processed"] == 3
    for ln in lines:
        assert ln["model"] == "DocLayout-YOLO"

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


def _ensure_segmented(client, slug):
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())


def test_put_box_updates_kind_and_persists(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p1-b0",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "list_item"},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b0")
    assert target["kind"] == "list_item"


def test_put_box_updates_bbox(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p1-b0",
        headers={"X-Auth-Token": "tok"},
        json={"bbox": [11, 22, 99, 199]},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b0")
    assert target["bbox"] == [11.0, 22.0, 99.0, 199.0]


def test_put_unknown_box_returns_404(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p9-b9",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "heading"},
    )
    assert resp.status_code == 404


def test_delete_box_assigns_discard_kind(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.delete(f"/api/docs/{slug}/segments/p1-b1", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b1")
    assert target["kind"] == "discard"


def test_merge_boxes_creates_one_with_union_bbox(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/merge",
        headers={"X-Auth-Token": "tok"},
        json={"box_ids": ["p1-b0", "p1-b1"]},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    page1 = [b for b in body["boxes"] if b["page"] == 1]
    assert len(page1) == 1
    merged = page1[0]
    assert merged["bbox"] == [10.0, 20.0, 100.0, 200.0]


def test_merge_rejects_cross_page(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/merge",
        headers={"X-Auth-Token": "tok"},
        json={"box_ids": ["p1-b0", "p2-b0"]},
    )
    assert resp.status_code == 400


def test_split_box_at_y(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/split",
        headers={"X-Auth-Token": "tok"},
        json={"box_id": "p1-b1", "split_y": 130},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    page1 = [b for b in body["boxes"] if b["page"] == 1]
    assert "p1-b1" not in {b["box_id"] for b in page1}
    new = [b for b in page1 if b["box_id"] != "p1-b0"]
    assert len(new) == 2
    ys = sorted([(b["bbox"][1], b["bbox"][3]) for b in new])
    assert ys == [(60.0, 130.0), (130.0, 200.0)]


def test_create_box(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments",
        headers={"X-Auth-Token": "tok"},
        json={"page": 1, "bbox": [200, 300, 400, 500], "kind": "heading"},
    )
    assert resp.status_code == 201
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    new_boxes = [b for b in body["boxes"] if b["bbox"] == [200.0, 300.0, 400.0, 500.0]]
    assert len(new_boxes) == 1
    assert new_boxes[0]["kind"] == "heading"
