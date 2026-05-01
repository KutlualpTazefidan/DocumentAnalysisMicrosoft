from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client_with_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    box = SegmentBox(
        box_id="p1-aaa",
        page=1,
        bbox=(0.0, 0.0, 100.0, 50.0),
        kind=BoxKind.paragraph,
        confidence=0.95,
        reading_order=0,
    )
    write_segments(root, "spec", SegmentsFile(slug="spec", boxes=[box]))
    return client


def test_admin_get_segments(client_with_segments) -> None:
    r = client_with_segments.get("/api/admin/docs/spec/segments", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["boxes"][0]["box_id"] == "p1-aaa"


def test_admin_update_box(client_with_segments) -> None:
    r = client_with_segments.put(
        "/api/admin/docs/spec/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "heading"},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "heading"


def test_admin_delete_box(client_with_segments) -> None:
    r = client_with_segments.delete(
        "/api/admin/docs/spec/segments/p1-aaa", headers={"X-Auth-Token": "tok"}
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "discard"


def test_admin_create_box(client_with_segments) -> None:
    r = client_with_segments.post(
        "/api/admin/docs/spec/segments",
        headers={"X-Auth-Token": "tok"},
        json={"page": 1, "bbox": [0.0, 60.0, 100.0, 110.0], "kind": "paragraph"},
    )
    assert r.status_code == 201
    assert r.json()["page"] == 1


# ── Reset endpoint fixtures & tests ───────────────────────────────────────────


@pytest.fixture
def client_with_yolo(tmp_path, monkeypatch):
    """Client with both segments.json and yolo.json seeded."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments, write_yolo

    client = TestClient(create_app())
    import io

    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    # Original YOLO boxes: page 1 (2 boxes) + page 2 (1 box)
    yolo_boxes = [
        {
            "box_id": "p1-y1",
            "page": 1,
            "bbox": [0.0, 0.0, 100.0, 50.0],
            "kind": "paragraph",
            "confidence": 0.9,
            "reading_order": 0,
        },
        {
            "box_id": "p1-y2",
            "page": 1,
            "bbox": [0.0, 60.0, 100.0, 120.0],
            "kind": "heading",
            "confidence": 0.85,
            "reading_order": 1,
        },
        {
            "box_id": "p2-y1",
            "page": 2,
            "bbox": [10.0, 10.0, 80.0, 40.0],
            "kind": "figure",
            "confidence": 0.8,
            "reading_order": 0,
        },
    ]
    write_yolo(root, "spec", {"boxes": yolo_boxes})

    # Current segments.json — page 1 box edited, a new user box, plus page 2 untouched
    seg_boxes = [
        SegmentBox(
            box_id="p1-y1",
            page=1,
            bbox=(5.0, 5.0, 90.0, 45.0),
            kind="heading",
            confidence=0.5,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p1-u1",
            page=1,
            bbox=(0.0, 130.0, 100.0, 200.0),
            kind="paragraph",
            confidence=1.0,
            reading_order=2,
        ),
        SegmentBox(
            box_id="p2-y1",
            page=2,
            bbox=(10.0, 10.0, 80.0, 40.0),
            kind="figure",
            confidence=0.8,
            reading_order=0,
        ),
    ]
    write_segments(root, "spec", SegmentsFile(slug="spec", boxes=seg_boxes))
    return client


def test_reset_page_restores_yolo_originals(client_with_yolo) -> None:
    r = client_with_yolo.post(
        "/api/admin/docs/spec/segments/reset?page=1",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    data = r.json()
    boxes = data["boxes"]
    page1 = [b for b in boxes if b["page"] == 1]
    page2 = [b for b in boxes if b["page"] == 2]

    # Page 1 must match YOLO originals exactly (2 boxes)
    assert len(page1) == 2
    ids = {b["box_id"] for b in page1}
    assert ids == {"p1-y1", "p1-y2"}
    y1 = next(b for b in page1 if b["box_id"] == "p1-y1")
    assert y1["bbox"] == [0.0, 0.0, 100.0, 50.0]
    assert y1["kind"] == "paragraph"
    assert y1["confidence"] == 0.9

    # Page 2 must be untouched
    assert len(page2) == 1
    assert page2[0]["box_id"] == "p2-y1"


def test_reset_page_404_when_no_yolo(tmp_path, monkeypatch) -> None:
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Spec.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    box = SegmentBox(
        box_id="p1-x",
        page=1,
        bbox=(0.0, 0.0, 10.0, 10.0),
        kind="paragraph",
        confidence=0.9,
        reading_order=0,
    )
    write_segments(root, "spec", SegmentsFile(slug="spec", boxes=[box]))

    r = client.post("/api/admin/docs/spec/segments/reset?page=1", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 404
    assert "no yolo output" in r.json()["detail"]


def test_reset_box_restores_bbox_kind_confidence(client_with_yolo) -> None:
    r = client_with_yolo.post(
        "/api/admin/docs/spec/segments/p1-y1/reset",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    box = r.json()
    assert box["box_id"] == "p1-y1"
    assert box["bbox"] == [0.0, 0.0, 100.0, 50.0]
    assert box["kind"] == "paragraph"
    assert box["confidence"] == 0.9


def test_reset_box_409_when_not_yolo_detected(client_with_yolo) -> None:
    # p1-u1 was user-created, not in yolo.json
    r = client_with_yolo.post(
        "/api/admin/docs/spec/segments/p1-u1/reset",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 409
    assert "no original" in r.json()["detail"]


# ── manually_activated tests ───────────────────────────────────────────────────


def test_box_defaults_manually_activated_false(client_with_segments) -> None:
    r = client_with_segments.get("/api/admin/docs/spec/segments", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["boxes"][0]["manually_activated"] is False


def test_put_can_set_manually_activated_true(client_with_segments) -> None:
    r = client_with_segments.put(
        "/api/admin/docs/spec/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"manually_activated": True},
    )
    assert r.status_code == 200
    assert r.json()["manually_activated"] is True


def test_reset_box_restores_manually_activated_false(client_with_yolo) -> None:
    # First activate a YOLO-detected box
    client_with_yolo.put(
        "/api/admin/docs/spec/segments/p1-y1",
        headers={"X-Auth-Token": "tok"},
        json={"manually_activated": True},
    )
    # Then reset it — manually_activated must go back to False
    r = client_with_yolo.post(
        "/api/admin/docs/spec/segments/p1-y1/reset",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    assert r.json()["manually_activated"] is False


# ── merge-down / merge-up tests ───────────────────────────────────────────────


@pytest.fixture
def client_two_pages(tmp_path, monkeypatch):
    """Client seeded with 2 boxes on page 1 and 2 boxes on page 2."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    seg_boxes = [
        SegmentBox(
            box_id="p1-a",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p1-b",
            page=1,
            bbox=(0.0, 60.0, 100.0, 120.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=1,
        ),
        SegmentBox(
            box_id="p2-a",
            page=2,
            bbox=(0.0, 5.0, 100.0, 55.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p2-b",
            page=2,
            bbox=(0.0, 60.0, 100.0, 120.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=1,
        ),
    ]
    write_segments(root, "doc", SegmentsFile(slug="doc", boxes=seg_boxes))
    return client


def test_merge_down_links_source_and_target(client_two_pages) -> None:
    r = client_two_pages.post(
        "/api/admin/docs/doc/segments/p1-b/merge-down",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    boxes = {b["box_id"]: b for b in r.json()["boxes"]}
    # source gets continues_to pointing to topmost box on page 2 (smallest y0 = 5.0 → p2-a)
    assert boxes["p1-b"]["continues_to"] == "p2-a"
    assert boxes["p2-a"]["continues_from"] == "p1-b"
    # unrelated boxes untouched
    assert boxes["p1-a"]["continues_to"] is None
    assert boxes["p2-b"]["continues_from"] is None


def test_merge_down_409_when_source_on_last_page(client_two_pages) -> None:
    r = client_two_pages.post(
        "/api/admin/docs/doc/segments/p2-a/merge-down",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 409
    assert "no box on next page" in r.json()["detail"]


def test_merge_down_409_when_next_page_all_discard(tmp_path, monkeypatch) -> None:
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    seg_boxes = [
        SegmentBox(
            box_id="p1-a",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p2-x",
            page=2,
            bbox=(0.0, 5.0, 100.0, 55.0),
            kind=BoxKind.discard,
            confidence=0.9,
            reading_order=0,
        ),
    ]
    write_segments(root, "doc", SegmentsFile(slug="doc", boxes=seg_boxes))
    r = client.post("/api/admin/docs/doc/segments/p1-a/merge-down", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 409
    assert "no box on next page" in r.json()["detail"]


def test_merge_down_409_when_already_linked(client_two_pages) -> None:
    # First merge
    client_two_pages.post(
        "/api/admin/docs/doc/segments/p1-b/merge-down",
        headers={"X-Auth-Token": "tok"},
    )
    # Second merge on same source must 409
    r = client_two_pages.post(
        "/api/admin/docs/doc/segments/p1-b/merge-down",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 409
    assert "already linked" in r.json()["detail"]


def test_merge_up_links_source_and_target(client_two_pages) -> None:
    r = client_two_pages.post(
        "/api/admin/docs/doc/segments/p2-a/merge-up",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    boxes = {b["box_id"]: b for b in r.json()["boxes"]}
    # source gets continues_from pointing to bottommost box on page 1 (largest y1 = 120.0 → p1-b)
    assert boxes["p2-a"]["continues_from"] == "p1-b"
    assert boxes["p1-b"]["continues_to"] == "p2-a"


def test_merge_up_409_when_source_on_first_page(client_two_pages) -> None:
    r = client_two_pages.post(
        "/api/admin/docs/doc/segments/p1-a/merge-up",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 409
    assert "no box on previous page" in r.json()["detail"]


def test_merge_up_409_when_already_linked(client_two_pages) -> None:
    client_two_pages.post(
        "/api/admin/docs/doc/segments/p2-a/merge-up",
        headers={"X-Auth-Token": "tok"},
    )
    r = client_two_pages.post(
        "/api/admin/docs/doc/segments/p2-a/merge-up",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 409
    assert "already linked" in r.json()["detail"]


def test_reset_box_clears_continues_fields(tmp_path, monkeypatch) -> None:
    """Per-box reset must clear continues_from and continues_to."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments, write_yolo

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    yolo_boxes = [
        {
            "box_id": "p1-a",
            "page": 1,
            "bbox": [0.0, 0.0, 100.0, 50.0],
            "kind": "paragraph",
            "confidence": 0.9,
            "reading_order": 0,
        },
        {
            "box_id": "p2-a",
            "page": 2,
            "bbox": [0.0, 5.0, 100.0, 55.0],
            "kind": "paragraph",
            "confidence": 0.9,
            "reading_order": 0,
        },
    ]
    write_yolo(root, "doc", {"boxes": yolo_boxes})

    seg_boxes = [
        SegmentBox(
            box_id="p1-a",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
            continues_to="p2-a",
        ),
        SegmentBox(
            box_id="p2-a",
            page=2,
            bbox=(0.0, 5.0, 100.0, 55.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
            continues_from="p1-a",
        ),
    ]
    write_segments(root, "doc", SegmentsFile(slug="doc", boxes=seg_boxes))

    r = client.post("/api/admin/docs/doc/segments/p1-a/reset", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    assert r.json()["continues_to"] is None
    assert r.json()["continues_from"] is None


# ── unmerge-down / unmerge-up tests ──────────────────────────────────────────


@pytest.fixture
def client_linked(tmp_path, monkeypatch):
    """Client with two linked boxes: p1-a → p2-a."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    seg_boxes = [
        SegmentBox(
            box_id="p1-a",
            page=1,
            bbox=(0.0, 0.0, 100.0, 50.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
            continues_to="p2-a",
        ),
        SegmentBox(
            box_id="p2-a",
            page=2,
            bbox=(0.0, 5.0, 100.0, 55.0),
            kind="paragraph",
            confidence=0.9,
            reading_order=0,
            continues_from="p1-a",
        ),
    ]
    write_segments(root, "doc", SegmentsFile(slug="doc", boxes=seg_boxes))
    return client


def test_unmerge_down_clears_both_ends(client_linked) -> None:
    r = client_linked.post(
        "/api/admin/docs/doc/segments/p1-a/unmerge-down",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    boxes = {b["box_id"]: b for b in r.json()["boxes"]}
    assert boxes["p1-a"]["continues_to"] is None
    assert boxes["p2-a"]["continues_from"] is None


def test_unmerge_down_409_when_no_continues_to(client_linked) -> None:
    # p2-a has no continues_to
    r = client_linked.post(
        "/api/admin/docs/doc/segments/p2-a/unmerge-down",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 409
    assert "continues_to not set" in r.json()["detail"]


def test_unmerge_up_clears_both_ends(client_linked) -> None:
    r = client_linked.post(
        "/api/admin/docs/doc/segments/p2-a/unmerge-up",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200
    boxes = {b["box_id"]: b for b in r.json()["boxes"]}
    assert boxes["p2-a"]["continues_from"] is None
    assert boxes["p1-a"]["continues_to"] is None


def test_unmerge_up_404_when_box_missing(tmp_path, monkeypatch) -> None:
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_segments

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    write_segments(
        root,
        "doc",
        SegmentsFile(
            slug="doc",
            boxes=[
                SegmentBox(
                    box_id="p1-a",
                    page=1,
                    bbox=(0.0, 0.0, 100.0, 50.0),
                    kind="paragraph",
                    confidence=0.9,
                    reading_order=0,
                )
            ],
        ),
    )
    r = client.post(
        "/api/admin/docs/doc/segments/nonexistent/unmerge-up",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 404
