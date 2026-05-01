from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003


def test_write_and_read_meta(data_root: Path) -> None:
    from local_pdf.api.schemas import DocMeta, DocStatus
    from local_pdf.storage.sidecar import doc_dir, read_meta, write_meta

    slug = "report"
    doc_dir(data_root, slug).mkdir()
    meta = DocMeta(
        slug=slug,
        filename="Report.pdf",
        pages=10,
        status=DocStatus.raw,
        last_touched_utc="2026-04-30T10:00:00Z",
    )
    write_meta(data_root, slug, meta)
    loaded = read_meta(data_root, slug)
    assert loaded == meta


def test_read_meta_returns_none_when_missing(data_root: Path) -> None:
    from local_pdf.storage.sidecar import read_meta

    assert read_meta(data_root, "missing") is None


def test_write_segments_round_trips(data_root: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import doc_dir, read_segments, write_segments

    slug = "rep"
    doc_dir(data_root, slug).mkdir()
    boxes = [
        SegmentBox(
            box_id="b-1", page=1, bbox=(10, 20, 100, 200), kind=BoxKind.paragraph, confidence=0.9
        )
    ]
    write_segments(data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
    loaded = read_segments(data_root, slug)
    assert loaded is not None
    assert loaded.boxes == boxes


def test_read_segments_returns_none_when_missing(data_root: Path) -> None:
    from local_pdf.storage.sidecar import read_segments

    assert read_segments(data_root, "nope") is None


def test_write_html_and_read_back(data_root: Path) -> None:
    from local_pdf.storage.sidecar import doc_dir, read_html, write_html

    slug = "rep"
    doc_dir(data_root, slug).mkdir()
    write_html(data_root, slug, "<h1>Hello</h1>")
    assert read_html(data_root, slug) == "<h1>Hello</h1>"


def test_write_meta_uses_lock_and_overwrites_atomically(data_root: Path) -> None:
    """Two sequential writes leave only the latest content (no partial JSON)."""
    from local_pdf.api.schemas import DocMeta, DocStatus
    from local_pdf.storage.sidecar import doc_dir, read_meta, write_meta

    slug = "rep"
    doc_dir(data_root, slug).mkdir()
    a = DocMeta(
        slug=slug,
        filename="A.pdf",
        pages=1,
        status=DocStatus.raw,
        last_touched_utc="2026-04-30T10:00:00Z",
    )
    b = DocMeta(
        slug=slug,
        filename="A.pdf",
        pages=1,
        status=DocStatus.segmenting,
        last_touched_utc="2026-04-30T10:01:00Z",
    )
    write_meta(data_root, slug, a)
    write_meta(data_root, slug, b)
    out = read_meta(data_root, slug)
    assert out == b
    raw = json.loads((doc_dir(data_root, slug) / "meta.json").read_text(encoding="utf-8"))
    assert raw["status"] == "segmenting"


def test_doc_dir_path_layout(data_root: Path) -> None:
    from local_pdf.storage.sidecar import doc_dir

    assert doc_dir(data_root, "alpha") == data_root / "alpha"
