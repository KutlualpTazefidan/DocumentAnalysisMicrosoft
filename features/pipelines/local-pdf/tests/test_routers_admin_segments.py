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


def _fake_middle_json_with_list() -> dict:
    """Single page with one list block containing 3 line entries."""
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
                                "spans": [{"content": "Heading"}],
                            }
                        ],
                    },
                    {
                        "type": "list",
                        "bbox": [50.0, 100.0, 400.0, 250.0],
                        "lines": [
                            {
                                "bbox": [50.0, 100.0, 400.0, 130.0],
                                "spans": [{"content": "First bullet"}],
                            },
                            {
                                "bbox": [50.0, 140.0, 400.0, 170.0],
                                "spans": [{"content": "Second bullet"}],
                            },
                            {
                                "bbox": [50.0, 180.0, 400.0, 210.0],
                                "spans": [{"content": "Third bullet"}],
                            },
                        ],
                    },
                ],
                "discarded_blocks": [],
            }
        ]
    }


def test_vlm_segment_list_decomposes_into_per_bullet_boxes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A MinerU list block with N lines must produce N list_item SegmentBoxes."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_VLM_PARSE_DOC_FN", lambda _bytes: _fake_middle_json_with_list())

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)

    r = client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200

    boxes = client.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"}).json()[
        "boxes"
    ]
    # 1 heading + 3 list_item bullets = 4 boxes total
    assert len(boxes) == 4

    by_id = {b["box_id"]: b for b in boxes}
    # heading at p1-b0, then three list_items at p1-b1, p1-b2, p1-b3
    assert by_id["p1-b0"]["kind"] == "heading"
    assert by_id["p1-b1"]["kind"] == "list_item"
    assert by_id["p1-b2"]["kind"] == "list_item"
    assert by_id["p1-b3"]["kind"] == "list_item"

    # Bullet bboxes must match the line bboxes (scaled 4x).
    assert by_id["p1-b1"]["bbox"][1] == pytest.approx(100.0 * 4)
    assert by_id["p1-b1"]["bbox"][3] == pytest.approx(130.0 * 4)
    assert by_id["p1-b2"]["bbox"][1] == pytest.approx(140.0 * 4)
    assert by_id["p1-b3"]["bbox"][3] == pytest.approx(210.0 * 4)


def test_vlm_segment_list_emits_li_html_per_bullet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each per-bullet element in mineru.json must be <li data-source-box=...>."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_VLM_PARSE_DOC_FN", lambda _bytes: _fake_middle_json_with_list())

    from pathlib import Path as _Path

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.storage.sidecar import read_mineru

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    data = read_mineru(_Path(tmp_path / "raw-pdfs"), "doc")
    assert data is not None
    by_id = {e["box_id"]: e["html_snippet"] for e in data["elements"]}
    # Each bullet emits an <li> with click-mapping + positional attrs.
    for bid, text in [
        ("p1-b1", "First bullet"),
        ("p1-b2", "Second bullet"),
        ("p1-b3", "Third bullet"),
    ]:
        snip = by_id[bid]
        assert snip.startswith("<li ")
        assert f'data-source-box="{bid}"' in snip
        assert f">{text}</li>" in snip


def test_vlm_segment_injects_data_source_box_into_non_list_blocks(
    client_vlm_segment,
) -> None:
    """Every emitted snippet must carry data-source-box for click-to-highlight."""
    _run_segment_vlm(client_vlm_segment, "doc")
    r = client_vlm_segment.get("/api/admin/docs/doc/mineru", headers={"X-Auth-Token": "tok"})
    elements = r.json()["elements"]
    for el in elements:
        assert f'data-source-box="{el["box_id"]}"' in el["html_snippet"], (
            f"missing data-source-box in {el['box_id']}: {el['html_snippet'][:120]!r}"
        )


def _fake_middle_json_with_aux_row() -> dict:
    """One page with a paragraph, two header-zone aux blocks, two footer-zone aux."""
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 200.0, 400.0, 300.0],
                        "lines": [
                            {
                                "bbox": [50.0, 200.0, 400.0, 300.0],
                                "spans": [{"content": "Body paragraph."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    # Two header-zone aux: emit RIGHT-side first to test x-sort.
                    {
                        "type": "text",
                        "bbox": [400.0, 30.0, 550.0, 50.0],
                        "lines": [
                            {
                                "bbox": [400.0, 30.0, 550.0, 50.0],
                                "spans": [{"content": "Page 7"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [50.0, 30.0, 200.0, 50.0],
                        "lines": [
                            {
                                "bbox": [50.0, 30.0, 200.0, 50.0],
                                "spans": [{"content": "Section A"}],
                            }
                        ],
                    },
                    # Two footer-zone aux: emit RIGHT-side first.
                    {
                        "type": "text",
                        "bbox": [400.0, 750.0, 550.0, 780.0],
                        "lines": [
                            {
                                "bbox": [400.0, 750.0, 550.0, 780.0],
                                "spans": [{"content": "Rev. 1"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [50.0, 750.0, 200.0, 780.0],
                        "lines": [
                            {
                                "bbox": [50.0, 750.0, 200.0, 780.0],
                                "spans": [{"content": "1 of 42"}],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def test_vlm_segment_aux_blocks_get_zone_attrs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """is_discarded blocks must carry data-aux-zone and data-aux-x."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod, "_VLM_PARSE_DOC_FN", lambda _bytes: _fake_middle_json_with_aux_row()
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    r = client.get("/api/admin/docs/doc/mineru", headers={"X-Auth-Token": "tok"})
    snippets_by_id = {e["box_id"]: e["html_snippet"] for e in r.json()["elements"]}

    # Body paragraph: no aux-zone
    assert "data-aux-zone" not in snippets_by_id["p1-b0"]
    # Aux blocks: header-zone for the two near top, footer-zone for the two near bottom.
    aux_snippets = [s for k, s in snippets_by_id.items() if k != "p1-b0"]
    headers = [s for s in aux_snippets if 'data-aux-zone="header"' in s]
    footers = [s for s in aux_snippets if 'data-aux-zone="footer"' in s]
    assert len(headers) == 2
    assert len(footers) == 2


def test_vlm_segment_html_aux_row_top_and_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """html.html must wrap aux blocks into top/bottom flex rows."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod, "_VLM_PARSE_DOC_FN", lambda _bytes: _fake_middle_json_with_aux_row()
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]
    # Stack wrappers carry the zone class; same-y items sit in one .aux-row.
    top_stack_tag = '<div class="aux-stack aux-stack--top">'
    bot_stack_tag = '<div class="aux-stack aux-stack--bottom">'
    assert top_stack_tag in html
    assert bot_stack_tag in html

    # Each zone has exactly ONE row (both aux items at the same y).
    assert html.count('<div class="aux-row">') == 2  # 1 top + 1 bottom

    # Within the row, items must be sorted left-to-right by x0.
    top_open = html.index(top_stack_tag)
    top_block = html[top_open : html.index("</div></div>", top_open)]
    assert top_block.index("Section A") < top_block.index("Page 7")

    # Alignment: x0=50 → left, x0=400 → right (page width 612pts).
    assert 'data-aux-align="left"' in top_block
    assert 'data-aux-align="right"' in top_block

    bot_open = html.index(bot_stack_tag)
    bot_block = html[bot_open : html.index("</div></div>", bot_open)]
    assert bot_block.index("1 of 42") < bot_block.index("Rev. 1")
    assert 'data-aux-align="left"' in bot_block
    assert 'data-aux-align="right"' in bot_block

    # Stacks sit OUTSIDE the body paragraph (top before, bottom after).
    body_pos = html.index("Body paragraph")
    assert top_open < body_pos < bot_open


def _fake_middle_json_with_multiline_header() -> dict:
    """Single page with a multi-line header aux block (3 lines stacked)."""
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 250.0, 400.0, 350.0],
                        "lines": [
                            {
                                "bbox": [50.0, 250.0, 400.0, 350.0],
                                "spans": [{"content": "Body paragraph."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    # ONE discarded block covering 3 stacked header lines.
                    {
                        "type": "text",
                        "bbox": [50.0, 30.0, 550.0, 110.0],
                        "lines": [
                            {
                                "bbox": [50.0, 30.0, 550.0, 50.0],
                                "spans": [{"content": "Customer ACME"}],
                            },
                            {
                                "bbox": [50.0, 60.0, 550.0, 80.0],
                                "spans": [{"content": "Project Alpha"}],
                            },
                            {
                                "bbox": [50.0, 90.0, 550.0, 110.0],
                                "spans": [{"content": "Revision 1.2"}],
                            },
                        ],
                    },
                ],
            }
        ]
    }


def test_vlm_segment_multiline_aux_decomposes_into_per_line_boxes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A discarded block with multiple lines must produce one aux box per line."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_multiline_header(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    boxes = client.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"}).json()[
        "boxes"
    ]
    # 1 paragraph + 3 per-line aux = 4 boxes total
    assert len(boxes) == 4
    aux_boxes = [b for b in boxes if b["kind"] == "auxiliary"]
    assert len(aux_boxes) == 3

    # Per-line bboxes follow the line bboxes (scaled 4x).
    aux_y0s = sorted(int(b["bbox"][1]) for b in aux_boxes)
    assert aux_y0s == [120, 240, 360]  # 30*4, 60*4, 90*4


def test_vlm_segment_multiline_aux_renders_as_stacked_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-line aux must render as multiple stacked aux-row inside one stack."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_multiline_header(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    # One top stack, no bottom stack. Three lines at different y → 3 rows.
    assert '<div class="aux-stack aux-stack--top">' in html
    assert '<div class="aux-stack aux-stack--bottom">' not in html
    assert html.count('<div class="aux-row">') == 3

    top_open = html.index('<div class="aux-stack aux-stack--top">')
    # End of stack: closing </div> after the last </div> of inner rows.
    # We use rindex on a window that covers the stack.
    top_block = html[top_open : html.index("</section>", top_open)]

    # Top-down ordering (y0 ascending) — items underneath others come later.
    pos_customer = top_block.index("Customer ACME")
    pos_project = top_block.index("Project Alpha")
    pos_revision = top_block.index("Revision 1.2")
    assert pos_customer < pos_project < pos_revision


def _fake_middle_json_with_three_alignments() -> dict:
    """Page with three header aux at same y, one each in left/center/right."""
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 200.0, 400.0, 300.0],
                        "lines": [
                            {
                                "bbox": [50.0, 200.0, 400.0, 300.0],
                                "spans": [{"content": "Body."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    # Center aux at x_center ≈ 306 (50% of 612) → "center"
                    {
                        "type": "text",
                        "bbox": [256.0, 30.0, 356.0, 50.0],
                        "lines": [
                            {
                                "bbox": [256.0, 30.0, 356.0, 50.0],
                                "spans": [{"content": "Title"}],
                            }
                        ],
                    },
                    # Left aux at x_center ≈ 100 (16% of 612) → "left"
                    {
                        "type": "text",
                        "bbox": [50.0, 30.0, 150.0, 50.0],
                        "lines": [
                            {
                                "bbox": [50.0, 30.0, 150.0, 50.0],
                                "spans": [{"content": "Section A"}],
                            }
                        ],
                    },
                    # Right aux at x_center ≈ 510 (83% of 612) → "right"
                    {
                        "type": "text",
                        "bbox": [460.0, 30.0, 560.0, 50.0],
                        "lines": [
                            {
                                "bbox": [460.0, 30.0, 560.0, 50.0],
                                "spans": [{"content": "Page 7"}],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def test_vlm_segment_aux_horizontal_alignment_left_center_right(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each aux must carry data-aux-align matching its bbox center vs page width."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_three_alignments(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    snippets_by_text = {}
    for el in client.get("/api/admin/docs/doc/mineru", headers={"X-Auth-Token": "tok"}).json()[
        "elements"
    ]:
        for label in ("Section A", "Title", "Page 7"):
            if label in el["html_snippet"]:
                snippets_by_text[label] = el["html_snippet"]
                break

    assert 'data-aux-align="left"' in snippets_by_text["Section A"]
    assert 'data-aux-align="center"' in snippets_by_text["Title"]
    assert 'data-aux-align="right"' in snippets_by_text["Page 7"]


def test_vlm_segment_aux_three_alignments_share_one_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three same-y aux items collapse into one row, in left→center→right DOM order."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_three_alignments(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    # All three at same y → exactly one .aux-row.
    assert html.count('<div class="aux-row">') == 1
    row_open = html.index('<div class="aux-row">')
    row_block = html[row_open : html.index("</div>", row_open)]
    # Sort within row is by x0 ascending → Section A (50), Title (256), Page 7 (460).
    assert row_block.index("Section A") < row_block.index("Title") < row_block.index("Page 7")


def _fake_middle_json_with_overlap_rows() -> dict:
    """Two header aux at the same VISUAL line but different y0 (different heights).

    Item A: y0=30, y1=70 (40pt tall — e.g. a 2-line title block).
    Item B: y0=55, y1=75 (20pt tall — short tag positioned to its right).

    y0 differs by 25pt — the old y0-band heuristic (≤20pt) would have split
    them into separate rows. But their bboxes vertically overlap, so they
    should share a row.
    """
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 200.0, 400.0, 300.0],
                        "lines": [
                            {
                                "bbox": [50.0, 200.0, 400.0, 300.0],
                                "spans": [{"content": "Body."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 30.0, 200.0, 70.0],  # tall, left
                        "lines": [
                            {
                                "bbox": [50.0, 30.0, 200.0, 70.0],
                                "spans": [{"content": "Tall Title"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [460.0, 55.0, 560.0, 75.0],  # short, right
                        "lines": [
                            {
                                "bbox": [460.0, 55.0, 560.0, 75.0],
                                "spans": [{"content": "Page 7"}],
                            }
                        ],
                    },
                    # A truly stacked second-line aux below — should NOT merge.
                    {
                        "type": "text",
                        "bbox": [50.0, 100.0, 200.0, 120.0],
                        "lines": [
                            {
                                "bbox": [50.0, 100.0, 200.0, 120.0],
                                "spans": [{"content": "Subtitle"}],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def test_vlm_segment_aux_grouping_uses_vertical_bbox_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Items whose y-ranges overlap share a row even with different y0."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_overlap_rows(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    # Two rows: row 1 = Tall Title + Page 7 (overlap), row 2 = Subtitle (stacked below).
    assert html.count('<div class="aux-row">') == 2

    # Tall Title and Page 7 share row 1 (y-ranges 30-70 and 55-75 overlap).
    row1_open = html.index('<div class="aux-row">')
    row1_block = html[row1_open : html.index("</div>", row1_open)]
    assert "Tall Title" in row1_block
    assert "Page 7" in row1_block
    assert "Subtitle" not in row1_block

    # Subtitle is alone in row 2 (y0=100 > Tall Title's y1=70 → no overlap).
    row2_open = html.index('<div class="aux-row">', row1_open + 1)
    row2_block = html[row2_open : html.index("</div>", row2_open)]
    assert "Subtitle" in row2_block
    assert "Tall Title" not in row2_block


def _fake_middle_json_with_user_reported_pair() -> dict:
    """User-reported example: tall aux on left, shorter aux on right, same y0.

    Pixel-space coords from the UI properties panel (raster_dpi=288, scale=4):
      aux 1: x0=268, y0=148, x1=580, y1=192
      aux 2: x0=1888, y0=148, x1=2156, y1=188

    Convert to pts (÷ 4) for the middle_json fixture:
      aux 1: x0=67, y0=37, x1=145, y1=48  (height 11)
      aux 2: x0=472, y0=37, x1=539, y1=47 (height 10)

    Both in the header zone, vertically overlapping → must share one row.
    Wider page (650pts) so aux 2's x_center falls clearly into the right third.
    """
    return {
        "pdf_info": [
            {
                "page_size": [650.0, 800.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 200.0, 600.0, 250.0],
                        "lines": [
                            {
                                "bbox": [50.0, 200.0, 600.0, 250.0],
                                "spans": [{"content": "Body."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    {
                        "type": "text",
                        "bbox": [67.0, 37.0, 145.0, 48.0],
                        "lines": [
                            {
                                "bbox": [67.0, 37.0, 145.0, 48.0],
                                "spans": [{"content": "Left aux"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [472.0, 37.0, 539.0, 47.0],
                        "lines": [
                            {
                                "bbox": [472.0, 37.0, 539.0, 47.0],
                                "spans": [{"content": "Right aux"}],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def test_vlm_segment_aux_user_reported_pair_shares_one_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: same-y aux with mismatched heights must collapse into one row."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_user_reported_pair(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    # Exactly one aux row, containing both items, with proper alignment.
    assert html.count('<div class="aux-row">') == 1
    row_open = html.index('<div class="aux-row">')
    row_block = html[row_open : html.index("</div>", row_open)]
    assert "Left aux" in row_block
    assert "Right aux" in row_block
    assert 'data-aux-align="left"' in row_block
    assert 'data-aux-align="right"' in row_block


def _fake_middle_json_with_two_stacked_pairs() -> dict:
    """Real-world page-7 layout: GNB+Seite7 on top line, TR+Rev.1 below.

    Source y/x in pts (from user-reported HTML data-aux-y values):
      GNB    y0=37, y1=48  x0=67   (top-left)
      TR     y0=49, y1=59  x0=67   (bottom-left)
      Seite7 y0=37, y1=47  x0=472  (top-right)
      Rev.1  y0=48, y1=58  x0=508  (bottom-right)

    GNB(37,48) and Rev.1(48,58) just touch at y=48 — the prior 2pt
    tolerance chained them, so all 4 ended up in one row with two
    left-items colliding in grid-column 1 and two right-items in
    grid-column 3. Genuine-overlap test (tol=0) keeps them in 2 rows.
    """
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [50.0, 200.0, 600.0, 250.0],
                        "lines": [
                            {
                                "bbox": [50.0, 200.0, 600.0, 250.0],
                                "spans": [{"content": "Body."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [
                    {
                        "type": "text",
                        "bbox": [67.0, 37.0, 145.0, 48.0],
                        "lines": [
                            {
                                "bbox": [67.0, 37.0, 145.0, 48.0],
                                "spans": [{"content": "GNB B 148/2001"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [67.0, 49.0, 145.0, 59.0],
                        "lines": [
                            {
                                "bbox": [67.0, 49.0, 145.0, 59.0],
                                "spans": [{"content": "TR K 0161"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [472.0, 37.0, 580.0, 47.0],
                        "lines": [
                            {
                                "bbox": [472.0, 37.0, 580.0, 47.0],
                                "spans": [{"content": "Seite 7 von 42"}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [508.0, 48.0, 580.0, 58.0],
                        "lines": [
                            {
                                "bbox": [508.0, 48.0, 580.0, 58.0],
                                "spans": [{"content": "Rev. 1"}],
                            }
                        ],
                    },
                ],
            }
        ]
    }


def test_vlm_segment_aux_two_stacked_pairs_become_two_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two visually-stacked pairs of aux must render as 2 rows, not 1.

    Regression: items that *touch* but don't overlap (e.g. y1=48 / y0=48)
    must NOT be merged into the same row.
    """
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_two_stacked_pairs(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    # Two rows: top (GNB + Seite7), bottom (TR + Rev.1).
    assert html.count('<div class="aux-row">') == 2

    row1_open = html.index('<div class="aux-row">')
    row1_block = html[row1_open : html.index("</div>", row1_open)]
    assert "GNB B 148/2001" in row1_block
    assert "Seite 7 von 42" in row1_block
    assert "TR K 0161" not in row1_block
    assert "Rev. 1" not in row1_block

    row2_open = html.index('<div class="aux-row">', row1_open + 1)
    row2_block = html[row2_open : html.index("</div>", row2_open)]
    assert "TR K 0161" in row2_block
    assert "Rev. 1" in row2_block
    assert "GNB B 148/2001" not in row2_block


def _fake_middle_json_with_table_and_caption() -> dict:
    """Single table parent block with table_body + table_caption sub-blocks."""
    return {
        "pdf_info": [
            {
                "page_size": [612.0, 792.0],
                "para_blocks": [
                    {
                        "type": "table",
                        "bbox": [50.0, 100.0, 550.0, 400.0],
                        "blocks": [
                            {
                                "type": "table_body",
                                "bbox": [50.0, 100.0, 550.0, 350.0],
                                "lines": [
                                    {
                                        "bbox": [50.0, 100.0, 550.0, 350.0],
                                        "spans": [
                                            {
                                                "type": "table",
                                                "html": (
                                                    "<table><tr><td>A</td><td>B</td></tr></table>"
                                                ),
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "type": "table_caption",
                                "bbox": [50.0, 360.0, 550.0, 380.0],
                                "lines": [
                                    {
                                        "bbox": [50.0, 360.0, 550.0, 380.0],
                                        "spans": [{"content": "Tab. 1 The caption"}],
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "discarded_blocks": [],
            }
        ]
    }


def test_vlm_segment_table_decomposes_body_and_caption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Table parent must produce one box for body + one for caption."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_table_and_caption(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})

    boxes = client.get("/api/admin/docs/doc/segments", headers={"X-Auth-Token": "tok"}).json()[
        "boxes"
    ]
    # 1 table body + 1 caption = 2 boxes
    assert len(boxes) == 2

    by_id = {b["box_id"]: b for b in boxes}
    assert by_id["p1-b0"]["kind"] == "table"
    assert by_id["p1-b1"]["kind"] == "caption"

    # Caption bbox follows the sub-block bbox (scaled 4x): y0=360*4=1440, y1=380*4=1520
    assert by_id["p1-b1"]["bbox"][1] == pytest.approx(1440.0)
    assert by_id["p1-b1"]["bbox"][3] == pytest.approx(1520.0)


def test_vlm_segment_table_caption_rendered_as_separate_paragraph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caption renders as <p class="caption"> with its own data-source-box."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_table_and_caption(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    # Caption is its own <p class="caption"> with its own data-source-box.
    assert "<p " in html
    assert 'data-source-box="p1-b1"' in html
    assert 'class="caption">Tab. 1 The caption</p>' in html
    # Table body is its own <div class="extracted-table"> with own data-source-box.
    assert 'data-source-box="p1-b0"' in html
    assert 'class="extracted-table">' in html
    # Table body comes BEFORE the caption (caption is below table in PDF).
    assert html.index('data-source-box="p1-b0"') < html.index('data-source-box="p1-b1"')


def test_vlm_segment_kind_change_to_discard_hides_box_from_html(
    client_vlm_segment,
) -> None:
    """PUT kind=discard must drop the box from html.html (filter at render)."""
    _run_segment_vlm(client_vlm_segment, "doc")

    # Both p1-b0 (heading) and p1-b1 (paragraph) start visible.
    html_before = client_vlm_segment.get(
        "/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}
    ).json()["html"]
    assert 'data-source-box="p1-b0"' in html_before
    assert 'data-source-box="p1-b1"' in html_before

    # Deactivate p1-b1; reextract=false to skip VLM (no real model in tests).
    r = client_vlm_segment.put(
        "/api/admin/docs/doc/segments/p1-b1?reextract=false",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "discard"},
    )
    assert r.status_code == 200

    # Manually trigger html refresh — production path runs this via
    # update_box's _refresh_active_html branch when reextract=true.
    import local_pdf.api.routers.admin.segments as seg_mod

    cfg = client_vlm_segment.app.state.config
    seg_mod._refresh_active_html(cfg, "doc")

    html_after = client_vlm_segment.get(
        "/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}
    ).json()["html"]
    assert 'data-source-box="p1-b0"' in html_after  # still visible
    assert 'data-source-box="p1-b1"' not in html_after  # hidden


def test_vlm_segment_reactivate_restores_box_in_html_even_if_vlm_fails(
    client_vlm_segment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Going kind=discard → kind=paragraph must bring the box back in html.html.

    Snippet stays in mineru.json on deactivate, so reactivate doesn't need a
    successful VLM re-extract — html.html refresh runs even if VLM throws.
    """
    _run_segment_vlm(client_vlm_segment, "doc")

    # Deactivate p1-b1.
    client_vlm_segment.delete("/api/admin/docs/doc/segments/p1-b1", headers={"X-Auth-Token": "tok"})
    html_off = client_vlm_segment.get(
        "/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}
    ).json()["html"]
    assert 'data-source-box="p1-b1"' not in html_off

    # Force the VLM hook to raise — simulates "VLM down" / model unavailable.
    import local_pdf.api.routers.admin.segments as seg_mod

    def fail_vlm(*_args, **_kwargs):
        raise RuntimeError("vlm unavailable")

    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", fail_vlm)

    # Reactivate by switching kind to paragraph.
    r = client_vlm_segment.put(
        "/api/admin/docs/doc/segments/p1-b1",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "paragraph"},
    )
    assert r.status_code == 200

    # Box must reappear in html.html (cached snippet from mineru.json).
    html_on = client_vlm_segment.get(
        "/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}
    ).json()["html"]
    assert 'data-source-box="p1-b1"' in html_on


def test_vlm_segment_delete_box_hides_from_html(client_vlm_segment) -> None:
    """DELETE /segments/{box_id} marks discard AND refreshes html."""
    _run_segment_vlm(client_vlm_segment, "doc")

    r = client_vlm_segment.delete(
        "/api/admin/docs/doc/segments/p1-b1", headers={"X-Auth-Token": "tok"}
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "discard"

    html_after = client_vlm_segment.get(
        "/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}
    ).json()["html"]
    assert 'data-source-box="p1-b0"' in html_after
    assert 'data-source-box="p1-b1"' not in html_after


def _fake_middle_json_with_side_by_side_paragraphs() -> dict:
    """Two paragraphs at overlapping y but different x — multi-column layout.

    User-reported pixel coords (raster_dpi=288, scale=4):
      p1: x0=280, y0=636, x1=416, y1=668
      p2: x0=1108, y0=632, x1=1308, y1=664

    In pts (÷4):
      p1: x0=70, y0=159, x1=104, y1=167
      p2: x0=277, y0=158, x1=327, y1=166

    Same vertical band → must share one body-row.
    """
    return {
        "pdf_info": [
            {
                "page_size": [650.0, 800.0],
                "para_blocks": [
                    {
                        "type": "text",
                        "bbox": [70.0, 159.0, 104.0, 167.0],
                        "lines": [
                            {
                                "bbox": [70.0, 159.0, 104.0, 167.0],
                                "spans": [{"content": "Left column."}],
                            }
                        ],
                    },
                    {
                        "type": "text",
                        "bbox": [277.0, 158.0, 327.0, 166.0],
                        "lines": [
                            {
                                "bbox": [277.0, 158.0, 327.0, 166.0],
                                "spans": [{"content": "Right column."}],
                            }
                        ],
                    },
                ],
                "discarded_blocks": [],
            }
        ]
    }


def test_vlm_segment_body_paragraphs_same_y_share_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two body paragraphs at overlapping y must render in one body-row."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.delenv("LOCAL_PDF_SEGMENT_BACKEND", raising=False)

    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(
        seg_mod,
        "_VLM_PARSE_DOC_FN",
        lambda _bytes: _fake_middle_json_with_side_by_side_paragraphs(),
    )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    client.post("/api/admin/docs/doc/segment", headers={"X-Auth-Token": "tok"})
    html = client.get("/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}).json()["html"]

    assert html.count('<div class="body-row">') == 1
    row_open = html.index('<div class="body-row">')
    row_block = html[row_open : html.index("</div>", row_open)]
    assert "Left column." in row_block
    assert "Right column." in row_block
    # Sort within row by x0 ascending → left first.
    assert row_block.index("Left column.") < row_block.index("Right column.")


def test_vlm_segment_body_single_column_no_row_wrapper(client_vlm_segment) -> None:
    """Single-column body (one item per y) must NOT get .body-row wrappers."""
    _run_segment_vlm(client_vlm_segment, "doc")
    html = client_vlm_segment.get(
        "/api/admin/docs/doc/html", headers={"X-Auth-Token": "tok"}
    ).json()["html"]
    assert '<div class="body-row">' not in html


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


def test_kind_change_appends_kind_change_diagnostic(tmp_path, monkeypatch) -> None:
    """PUT with kind change must append a kind_change diagnostic to mineru.json."""
    import local_pdf.api.routers.admin.segments as seg_mod

    stub_html = "<h2>re-extracted as heading</h2>"
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
    diags = data.get("diagnostics", [])
    kind_change_diags = [d for d in diags if d.get("kind") == "kind_change"]
    assert len(kind_change_diags) == 1, f"expected 1 kind_change diagnostic, got: {diags}"
    kd = kind_change_diags[0]
    assert kd["box_id"] == "p1-aaa"
    assert kd["old_kind"] == "paragraph"
    assert kd["new_kind"] == "heading"
    assert kd["page"] == 1
    assert "visual_hint_used" in kd


def test_bbox_change_does_not_append_kind_change_diagnostic(tmp_path, monkeypatch) -> None:
    """PUT with only bbox change must NOT append a kind_change diagnostic."""
    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_VLM_EXTRACT_BBOX_FN", _stub_extract("<p>x</p>"))

    client, root = _make_client_with_mineru(tmp_path, monkeypatch)

    client.put(
        "/api/admin/docs/doc/segments/p1-aaa",
        headers={"X-Auth-Token": "tok"},
        json={"bbox": [20.0, 20.0, 210.0, 90.0]},
    )

    from local_pdf.storage.sidecar import read_mineru

    data = read_mineru(root, "doc")
    assert data is not None
    diags = data.get("diagnostics", [])
    kind_change_diags = [d for d in diags if d.get("kind") == "kind_change"]
    assert kind_change_diags == [], f"unexpected kind_change diagnostics: {diags}"
