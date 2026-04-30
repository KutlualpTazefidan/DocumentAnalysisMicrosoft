"""Tests for goldens.creation.elements.analyze_json — fixture-driven."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader

FIXTURES = Path(__file__).parent / "fixtures"


def _make_outputs(tmp_path: Path, slug: str, fixture_name: str, ts: str) -> Path:
    analyze_dir = tmp_path / slug / "analyze"
    analyze_dir.mkdir(parents=True)
    shutil.copy(FIXTURES / fixture_name, analyze_dir / f"{ts}.json")
    return tmp_path


def test_filter_noise_roles(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    elements = AnalyzeJsonLoader("doc-a", outputs_root=root).elements()
    contents = [el.content for el in elements]
    assert "Top-of-page noise — should be dropped" not in contents
    assert "Quelle: DIN 18800" not in contents


def test_role_to_type_mapping(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    elements = AnalyzeJsonLoader("doc-a", outputs_root=root).elements()
    by_content = {el.content: el for el in elements}
    assert by_content["Tragkorb-Spezifikation"].element_type == "heading"
    body = by_content["Der Tragkorb wird in zwei Hälften gefertigt und vor Ort verschraubt."]
    assert body.element_type == "paragraph"


def test_section_heading_is_heading(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-b", "analyze_with_two_pages.json", "2026-04-29T10-00-00Z")
    elements = AnalyzeJsonLoader("doc-b", outputs_root=root).elements()
    statik = next(el for el in elements if el.content == "Statik")
    assert statik.element_type == "heading"


def test_element_id_stability(tmp_path: Path) -> None:
    """Same content → same id even if positional rank shifts."""
    root_a = _make_outputs(tmp_path / "a", "doc-a", "analyze_minimal.json", "ts.json")
    root_b = _make_outputs(tmp_path / "b", "doc-a", "analyze_minimal.json", "ts.json")
    a = {
        el.content: el.element_id
        for el in AnalyzeJsonLoader("doc-a", outputs_root=root_a).elements()
    }
    b = {
        el.content: el.element_id
        for el in AnalyzeJsonLoader("doc-a", outputs_root=root_b).elements()
    }
    assert a == b


def test_element_id_format(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    pattern = re.compile(r"^p\d+-[0-9a-f]{8}$")
    for el in AnalyzeJsonLoader("doc-a", outputs_root=root).elements():
        assert pattern.fullmatch(el.element_id), el.element_id


def test_ordering_by_page_then_y(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-b", "analyze_with_two_pages.json", "2026-04-29T10-00-00Z")
    elements = AnalyzeJsonLoader("doc-b", outputs_root=root).elements()
    pages_then_y = [(el.page_number, el.content[:20]) for el in elements]
    assert pages_then_y[0][0] == 1 and "Statik" in pages_then_y[0][1]
    assert pages_then_y[1][0] == 1
    assert pages_then_y[2][0] == 2 and "Erste Zeile" in pages_then_y[2][1]
    assert pages_then_y[3][0] == 2 and "Materialkennwerte" in pages_then_y[3][1]
    assert pages_then_y[4][0] == 2  # the table


def test_table_element_has_dims(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    table = next(
        el
        for el in AnalyzeJsonLoader("doc-a", outputs_root=root).elements()
        if el.element_type == "table"
    )
    assert table.table_dims == (2, 3)


def test_figure_caption_extracted(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    fig = next(
        el
        for el in AnalyzeJsonLoader("doc-a", outputs_root=root).elements()
        if el.element_type == "figure"
    )
    assert fig.caption == "Abbildung 1 — Schnitt durch den Tragkorb"
    assert fig.content == ""


def test_empty_content_dropped(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    contents = [el.content for el in AnalyzeJsonLoader("doc-a", outputs_root=root).elements()]
    assert "   " not in contents
    # Only the figure is allowed empty content.
    non_figure_empty = [c for c in contents if c == ""]
    assert len(non_figure_empty) == 1


def test_picks_latest_analyze_json(tmp_path: Path) -> None:
    analyze_dir = tmp_path / "doc-a" / "analyze"
    analyze_dir.mkdir(parents=True)
    early = analyze_dir / "2026-04-01T10-00-00Z.json"
    late = analyze_dir / "2026-04-29T10-00-00Z.json"
    shutil.copy(FIXTURES / "analyze_with_two_pages.json", early)
    shutil.copy(FIXTURES / "analyze_minimal.json", late)
    elements = AnalyzeJsonLoader("doc-a", outputs_root=tmp_path).elements()
    assert any(el.content == "Tragkorb-Spezifikation" for el in elements)
    assert not any(el.content == "Statik" for el in elements)


def test_missing_outputs_dir_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="analyze"):
        AnalyzeJsonLoader("does-not-exist", outputs_root=tmp_path).elements()


def test_slug_attribute_is_public(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    loader = AnalyzeJsonLoader("doc-a", outputs_root=root)
    assert loader.slug == "doc-a"


def test_to_source_element_maps_correctly(tmp_path: Path) -> None:
    root = _make_outputs(tmp_path, "doc-a", "analyze_minimal.json", "2026-04-29T10-00-00Z")
    loader = AnalyzeJsonLoader("doc-a", outputs_root=root)
    for el in loader.elements():
        src = loader.to_source_element(el)
        assert src.document_id == "doc-a"
        assert src.page_number == el.page_number
        assert src.element_type == el.element_type
        # element_id is the hash portion only, no `p{page}-` prefix.
        assert src.element_id == el.element_id.split("-", 1)[1]
        assert "-" not in src.element_id
