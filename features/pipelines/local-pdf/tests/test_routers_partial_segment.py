"""Tests for partial / range-based segmentation (?start=N&end=M)."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _fake_predict_four_pages(pdf_path):
    """Return one box per page for pages 1-4."""
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox

    return [
        YOLOPagePrediction(
            page=p,
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
        for p in range(1, 5)
    ]


@pytest.fixture
def client_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Client wired to a fake 4-page predict function."""
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    import local_pdf.api.routers.admin.segments as seg_mod

    monkeypatch.setattr(seg_mod, "_YOLO_PREDICT_FN", _fake_predict_four_pages)

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/admin/docs", headers={"X-Auth-Token": "tok"}, files=files)
    return client


def _run_segment(client, slug: str, start: int | None = None, end: int | None = None):
    """POST to /segment and consume the response stream. Returns 200 or raises."""
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
    return r


def _get_boxes(client, slug: str) -> list[dict]:
    r = client.get(f"/api/admin/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    return r.json()["boxes"]


def test_partial_segment_start2_end3_only_has_pages_2_and_3(client_partial) -> None:
    """Segmenting ?start=2&end=3 should only yield boxes on pages 2 and 3."""
    _run_segment(client_partial, "doc", start=2, end=3)
    boxes = _get_boxes(client_partial, "doc")
    pages = {b["page"] for b in boxes}
    assert pages == {2, 3}


def test_partial_segment_preserves_existing_boxes_outside_range(client_partial) -> None:
    """Re-segmenting pages 2-3 must not touch existing boxes on pages 1 and 4."""
    # First, segment the full doc to populate all 4 pages.
    _run_segment(client_partial, "doc")
    full_boxes = _get_boxes(client_partial, "doc")
    assert {b["page"] for b in full_boxes} == {1, 2, 3, 4}

    page1_id = next(b["box_id"] for b in full_boxes if b["page"] == 1)
    page4_id = next(b["box_id"] for b in full_boxes if b["page"] == 4)

    # Now re-segment only pages 2-3.
    _run_segment(client_partial, "doc", start=2, end=3)
    partial_boxes = _get_boxes(client_partial, "doc")

    partial_ids = {b["box_id"] for b in partial_boxes}
    # Pages 1 and 4 must still be present with their original box IDs.
    assert page1_id in partial_ids
    assert page4_id in partial_ids
    # Pages 2 and 3 must be present (fresh from re-segment).
    assert any(b["page"] == 2 for b in partial_boxes)
    assert any(b["page"] == 3 for b in partial_boxes)


def test_partial_segment_replaces_pages_in_range_cleanly(client_partial) -> None:
    """Re-segmenting the same range replaces only those pages, not duplicating."""
    _run_segment(client_partial, "doc", start=2, end=3)
    # Two boxes expected (one per page).
    boxes_after_first = _get_boxes(client_partial, "doc")
    assert len([b for b in boxes_after_first if b["page"] in (2, 3)]) == 2

    # Segment again with same range — should still be 2 boxes for those pages.
    _run_segment(client_partial, "doc", start=2, end=3)
    boxes_after_second = _get_boxes(client_partial, "doc")
    assert len([b for b in boxes_after_second if b["page"] in (2, 3)]) == 2
