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


# ── VLM segmentation path tests ───────────────────────────────────────────────


def _fake_middle_json_two_pages() -> dict:
    """Minimal middle_json with 2 pages, 3 blocks total (one discarded)."""
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "title",
                        "bbox": [50.0, 50.0, 300.0, 80.0],
                        "lines": [
                            {
                                "bbox": [50.0, 50.0, 300.0, 80.0],
                                "spans": [{"content": "Document Title"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [50.0, 100.0, 400.0, 150.0],
                        "lines": [
                            {
                                "bbox": [50.0, 100.0, 400.0, 150.0],
                                "spans": [{"content": "First paragraph text."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 750.0, 200.0, 780.0],
                        "lines": [
                            {
                                "bbox": [50.0, 750.0, 200.0, 780.0],
                                "spans": [{"content": "1"}],
                            }
                        ],
                    }
                ],
            },
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 50.0, 400.0, 120.0],
                        "lines": [
                            {
                                "bbox": [50.0, 50.0, 400.0, 120.0],
                                "spans": [{"content": "Page two paragraph."}],
                            }
                        ],
                    }
                ],
                "discarded_blocks": [],
            },
        ]
    }


@pytest.fixture
def client_vlm_segment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client wired to a fake VLM parse_doc_fn (no real model loaded)."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    # Ensure the VLM path is active (not yolo).
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_VLM_PARSE_DOC_FN", lambda _bytes: _fake_middle_json_two_pages())

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    return client


def _run_segment_vlm(client, slug: str, start: int | None = None, end: int | None = None) -> None:
    qs = ""
    if start is not None and end is not None:
        qs = f"?start={start}&end={end}"
    elif start is not None:
        qs = f"?start={start}"
    elif end is not None:
        qs = f"?end={end}"
    r = client.post(
        f"/api/admin/docs/{slug}/segment{qs}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200


def test_vlm_segment_boxes_have_page_block_ids(client_vlm_segment) -> None:
    """box_id format must be p{page}-b{idx}."""
    _run_segment_vlm(client_vlm_segment, "doc")
    r = client_vlm_segment.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    boxes = r.json()["boxes"]
    ids = {b["box_id"] for b in boxes}
    # Expect p1-b0, p1-b1 (para), p1-b2 (discarded), p2-b0 (para on page 2)
    assert "p1-b0" in ids
    assert "p1-b1" in ids
    assert "p2-b0" in ids


def test_vlm_segment_kind_mapping(client_vlm_segment) -> None:
    """title → heading, text → paragraph, discarded → auxiliary."""
    _run_segment_vlm(client_vlm_segment, "doc")
    r = client_vlm_segment.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"})
    boxes = {b["box_id"]: b for b in r.json()["boxes"]}

    assert boxes["p1-b0"]["kind"] == "heading"  # "title" → heading
    assert boxes["p1-b1"]["kind"] == "paragraph"  # "text" → paragraph
    assert boxes["p1-b2"]["kind"] == "auxiliary"  # discarded → auxiliary
    assert boxes["p2-b0"]["kind"] == "paragraph"  # "text" → paragraph


def test_vlm_segment_bbox_in_pixel_space(client_vlm_segment) -> None:
    """Bboxes must be scaled from PDF pts to pixel space at raster_dpi=288."""
    _run_segment_vlm(client_vlm_segment, "doc")
    r = client_vlm_segment.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"})
    boxes = {b["box_id"]: b for b in r.json()["boxes"]}

    # title block bbox in pts: [50, 50, 300, 80]
    # scale = 288/72 = 4.0 → px: [200, 200, 1200, 320]
    bbox = boxes["p1-b0"]["bbox"]
    assert pytest.approx(bbox[0], rel=1e-3) == 50.0 * 4
    assert pytest.approx(bbox[1], rel=1e-3) == 50.0 * 4
    assert pytest.approx(bbox[2], rel=1e-3) == 300.0 * 4
    assert pytest.approx(bbox[3], rel=1e-3) == 80.0 * 4


def test_vlm_segment_writes_mineru_json(client_vlm_segment) -> None:
    """mineru.json must exist with elements carrying the same box_ids."""
    _run_segment_vlm(client_vlm_segment, "doc")
    import os

    from local_pdf.storage.sidecar import read_mineru

    root_str = os.environ.get("LOCAL_PDF_DATA_ROOT")
    from pathlib import Path

    data = read_mineru(Path(root_str), "doc")
    assert data is not None
    element_ids = {e["box_id"] for e in data["elements"]}
    assert "p1-b0" in element_ids
    assert "p1-b1" in element_ids
    assert "p2-b0" in element_ids


def test_vlm_segment_writes_html_with_sections(client_vlm_segment) -> None:
    """html.html must contain section[data-page=...] wrappers."""
    _run_segment_vlm(client_vlm_segment, "doc")
    r = client_vlm_segment.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    html = r.json()["html"]
    assert '<section data-page="1">' in html
    assert '<section data-page="2">' in html


def test_vlm_segment_confidence_and_reading_order(client_vlm_segment) -> None:
    """Confidence must be 1.0; manually_activated must be False."""
    _run_segment_vlm(client_vlm_segment, "doc")
    r = client_vlm_segment.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"})
    for box in r.json()["boxes"]:
        assert box["confidence"] == 1.0
        assert box["manually_activated"] is False


def test_vlm_segment_partial_preserves_other_pages(tmp_path, monkeypatch) -> None:
    """Partial VLM re-segmentation must preserve boxes from untouched pages."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_VLM_PARSE_DOC_FN", lambda _bytes: _fake_middle_json_two_pages())

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    # Full segment to seed both pages.
    _run_segment_vlm(client, "doc")
    full_boxes = client.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"}).json()[
        "boxes"
    ]
    page1_ids = {b["box_id"] for b in full_boxes if b["page"] == 1}
    assert page1_ids  # sanity

    # Re-segment only page 2.
    _run_segment_vlm(client, "doc", start=2, end=2)
    partial_boxes = client.get(
        "/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"}
    ).json()["boxes"]
    partial_ids = {b["box_id"] for b in partial_boxes if b["page"] == 1}

    # Page 1 boxes must be unchanged.
    assert page1_ids == partial_ids


def test_vlm_segment_yolo_fallback_uses_yolo_path(tmp_path, monkeypatch) -> None:
    """LOCAL_PDF_SEGMENT_BACKEND=yolo must route to YOLO worker, not VLM."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.setenv("LOCAL_PDF_SEGMENT_BACKEND", "yolo")

    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox

    def fake_predict(pdf_path):
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(
                        class_name="plain text",
                        bbox=(10.0, 10.0, 100.0, 50.0),
                        confidence=0.9,
                    )
                ],
            )
        ]

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_YOLO_PREDICT_FN", fake_predict)

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    r = client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200

    # YOLO path writes yolo.json; VLM path does not.
    from local_pdf.storage.sidecar import read_yolo

    yolo = read_yolo(root, "doc")
    assert yolo is not None, "YOLO path must write yolo.json"
    assert len(yolo["boxes"]) == 1


# ── Per-bbox re-extract tests ─────────────────────────────────────────────────


def _make_client_with_mineru(tmp_path, monkeypatch):
    """Helper: client with segments.json AND mineru.json already seeded."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import write_mineru, write_segments

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    box = SegmentBox(
        box_id="p1-aaa",
        page=1,
        bbox=(10.0, 10.0, 200.0, 80.0),
        kind=BoxKind.paragraph,
        confidence=1.0,
        reading_order=0,
    )
    write_segments(root, "doc", SegmentsFile(slug="doc", boxes=[box], raster_dpi=288))
    write_mineru(
        root,
        "doc",
        {
            "elements": [{"box_id": "p1-aaa", "html_snippet": "<p>old content</p>"}],
            "diagnostics": [],
        },
    )
    return client, root


def _stub_extract(html: str):
    """Return a deterministic vlm_extract_bbox stub that ignores geometry."""

    def _fn(pdf_bytes, page, bbox_pts, user_kind, *, box_id, **_kw):
        return html

    return _fn


def test_put_bbox_change_triggers_reextract(tmp_path, monkeypatch) -> None:
    """PATCH with a bbox change must update html_snippet in mineru.json."""
    import local_pdf.api.routers.admin.segments as seg_mod

    stub_html = "<p>fresh bbox content</p>"
    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", _stub_extract(stub_html))

    client, root = _make_client_with_mineru(tmp_path, monkeypatch)

    r = client.put(
        "/api/admin/docs/doc/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"bbox": [20.0, 20.0, 210.0, 90.0]},
    )
    assert r.status_code == 200

    from local_pdf.storage.sidecar import read_mineru

    data = read_mineru(root, "doc")
    assert data is not None
    el = next(e for e in data["elements"] if e["box_id"] == "p1-aaa")
    assert el["html_snippet"] == stub_html


def test_put_kind_change_triggers_reextract(tmp_path, monkeypatch) -> None:
    """PATCH with a kind change (no bbox change) must also trigger re-extract."""
    import local_pdf.api.routers.admin.segments as seg_mod

    stub_html = "<h2>heading content</h2>"
    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", _stub_extract(stub_html))

    client, root = _make_client_with_mineru(tmp_path, monkeypatch)

    r = client.put(
        "/api/admin/docs/doc/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "heading"},
    )
    assert r.status_code == 200

    from local_pdf.storage.sidecar import read_mineru

    data = read_mineru(root, "doc")
    assert data is not None
    el = next(e for e in data["elements"] if e["box_id"] == "p1-aaa")
    assert el["html_snippet"] == stub_html


def test_put_no_geometry_no_kind_change_skips_reextract(tmp_path, monkeypatch) -> None:
    """PATCH that changes only reading_order must NOT call re-extract."""
    import local_pdf.api.routers.admin.segments as seg_mod

    calls: list = []

    def _recording_stub(pdf_bytes, page, bbox_pts, user_kind, *, box_id, **_kw):
        calls.append(box_id)
        return "<p>should not appear</p>"

    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", _recording_stub)

    client, _root = _make_client_with_mineru(tmp_path, monkeypatch)

    r = client.put(
        "/api/admin/docs/doc/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"reading_order": 5},
    )
    assert r.status_code == 200
    assert calls == [], "re-extract must not fire when bbox/kind unchanged"


def test_put_reextract_false_skips_reextract(tmp_path, monkeypatch) -> None:
    """?reextract=false must skip re-extract even when bbox changes."""
    import local_pdf.api.routers.admin.segments as seg_mod

    calls: list = []

    def _recording_stub(pdf_bytes, page, bbox_pts, user_kind, *, box_id, **_kw):
        calls.append(box_id)
        return "<p>should not appear</p>"

    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", _recording_stub)

    client, _root = _make_client_with_mineru(tmp_path, monkeypatch)

    r = client.put(
        "/api/admin/docs/doc/segments/p1-aaa?reextract=false",
        headers={"X-Auth-Token": "tok"},
        json={"bbox": [30.0, 30.0, 220.0, 100.0]},
    )
    assert r.status_code == 200
    assert calls == [], "re-extract must not fire when ?reextract=false"


def test_post_new_box_triggers_reextract(tmp_path, monkeypatch) -> None:
    """POST /segments (create box) must add a new element to mineru.json via re-extract."""
    import local_pdf.api.routers.admin.segments as seg_mod

    stub_html = "<p>brand new box content</p>"

    def _stub(pdf_bytes, page, bbox_pts, user_kind, *, box_id, **_kw):
        return stub_html

    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", _stub)

    client, root = _make_client_with_mineru(tmp_path, monkeypatch)

    r = client.post(
        "/api/admin/docs/doc/segments",
        headers={"X-Auth-Token": "tok"},
        json={"page": 1, "bbox": [50.0, 100.0, 300.0, 200.0], "kind": "paragraph"},
    )
    assert r.status_code == 201
    new_box_id = r.json()["box_id"]

    from local_pdf.storage.sidecar import read_mineru

    data = read_mineru(root, "doc")
    assert data is not None
    ids = {e["box_id"] for e in data["elements"]}
    assert new_box_id in ids
    el = next(e for e in data["elements"] if e["box_id"] == new_box_id)
    assert el["html_snippet"] == stub_html
