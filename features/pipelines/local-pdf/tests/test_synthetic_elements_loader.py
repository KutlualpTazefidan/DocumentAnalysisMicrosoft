"""Tests for MineruElementsLoader — the bridge from local-pdf's
``mineru.json`` + ``segments.json`` to the goldens A.5 ElementsLoader
contract."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
from local_pdf.storage.sidecar import write_mineru, write_segments
from local_pdf.synthetic import MineruElementsLoader

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def populated_root(tmp_path: Path) -> Path:
    """data_root with one slug carrying a mix of supported + skipped kinds."""
    boxes = [
        SegmentBox(
            box_id="p1-b0",
            page=1,
            bbox=(0.0, 0.0, 400.0, 50.0),
            kind=BoxKind.heading,
            confidence=1.0,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p1-b1",
            page=1,
            bbox=(0.0, 60.0, 400.0, 200.0),
            kind=BoxKind.paragraph,
            confidence=1.0,
            reading_order=1,
        ),
        SegmentBox(
            box_id="p1-b2",
            page=1,
            bbox=(0.0, 220.0, 400.0, 240.0),
            kind=BoxKind.auxiliary,  # skipped
            confidence=1.0,
            reading_order=2,
        ),
        SegmentBox(
            box_id="p2-b0",
            page=2,
            bbox=(0.0, 0.0, 400.0, 200.0),
            kind=BoxKind.table,
            confidence=1.0,
            reading_order=0,
        ),
        SegmentBox(
            box_id="p2-b1",
            page=2,
            bbox=(0.0, 210.0, 400.0, 260.0),
            kind=BoxKind.discard,  # skipped
            confidence=1.0,
            reading_order=1,
        ),
    ]
    write_segments(tmp_path, "doc", SegmentsFile(slug="doc", boxes=boxes, raster_dpi=288))

    elements = [
        {
            "box_id": "p1-b0",
            "html_snippet": "<h2>Body Title</h2>",
            "html_snippet_raw": "<h2>Body Title</h2>",
        },
        {
            "box_id": "p1-b1",
            "html_snippet": "<p>Paragraph text body.</p>",
            "html_snippet_raw": "<p>Paragraph text body.</p>",
        },
        {
            "box_id": "p1-b2",
            "html_snippet": "<header>Page 1</header>",
            "html_snippet_raw": "<header>Page 1</header>",
        },
        {
            "box_id": "p2-b0",
            "html_snippet": (
                '<div class="extracted-table"><table><tr><td>A</td></tr></table></div>'
            ),
            "html_snippet_raw": (
                '<div class="extracted-table"><table><tr><td>A</td></tr></table></div>'
            ),
        },
        {
            "box_id": "p2-b1",
            "html_snippet": "<p>Discarded</p>",
            "html_snippet_raw": "<p>Discarded</p>",
        },
    ]
    write_mineru(tmp_path, "doc", {"elements": elements, "diagnostics": []})
    return tmp_path


def test_loader_yields_supported_kinds_only(populated_root: Path) -> None:
    loader = MineruElementsLoader(data_root=populated_root, slug="doc")
    elements = loader.elements()
    ids = [e.element_id for e in elements]
    assert ids == ["p1-b0", "p1-b1", "p2-b0"]  # auxiliary + discard skipped


def test_loader_maps_kind_to_element_type(populated_root: Path) -> None:
    by_id = {e.element_id: e for e in MineruElementsLoader(populated_root, "doc").elements()}
    assert by_id["p1-b0"].element_type == "heading"
    assert by_id["p1-b1"].element_type == "paragraph"
    assert by_id["p2-b0"].element_type == "table"


def test_loader_strips_html_to_plain_text(populated_root: Path) -> None:
    by_id = {e.element_id: e for e in MineruElementsLoader(populated_root, "doc").elements()}
    assert by_id["p1-b1"].content == "Paragraph text body."
    assert by_id["p1-b0"].content == "Body Title"


def test_loader_passes_full_table_html_for_tables(populated_root: Path) -> None:
    by_id = {e.element_id: e for e in MineruElementsLoader(populated_root, "doc").elements()}
    table = by_id["p2-b0"]
    assert table.element_type == "table"
    assert table.table_full_content is not None
    assert "<table>" in table.table_full_content


def test_loader_filter_only_box_id(populated_root: Path) -> None:
    loader = MineruElementsLoader(populated_root, "doc", only_box_id="p1-b1")
    elements = loader.elements()
    assert [e.element_id for e in elements] == ["p1-b1"]


def test_loader_filter_only_page(populated_root: Path) -> None:
    loader = MineruElementsLoader(populated_root, "doc", only_page=2)
    elements = loader.elements()
    assert [e.element_id for e in elements] == ["p2-b0"]


def test_loader_returns_empty_for_unknown_slug(tmp_path: Path) -> None:
    loader = MineruElementsLoader(data_root=tmp_path, slug="nope")
    assert loader.elements() == []
