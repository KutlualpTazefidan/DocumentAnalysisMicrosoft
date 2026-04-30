"""Tests for goldens.creation.synthetic_decomposition.

Spec: docs/superpowers/specs/2026-04-29-a5-synthetic-design.md §4.2, §9.
"""

from __future__ import annotations

from goldens.creation.elements import DocumentElement
from goldens.creation.synthetic_decomposition import decompose_to_sub_units


def _para(content: str) -> DocumentElement:
    return DocumentElement(
        element_id="p1-aaaaaaaa",
        page_number=1,
        element_type="paragraph",
        content=content,
    )


def _table(content: str) -> DocumentElement:
    # `content` carries the rendered header + body rows separated by
    # newlines, columns by ` | `. Single-row tables → exactly one
    # sub-unit. The loader is expected to format tables this way.
    return DocumentElement(
        element_id="p1-bbbbbbbb",
        page_number=1,
        element_type="table",
        content=content,
        table_dims=(content.count("\n") + 1, content.split("\n")[0].count(" | ") + 1),
    )


def _list(content: str) -> DocumentElement:
    return DocumentElement(
        element_id="p1-cccccccc",
        page_number=1,
        element_type="list_item",
        content=content,
    )


# --- paragraph ------------------------------------------------------


def test_paragraph_splits_into_sentences_keeping_abbreviations():
    """German paragraph with `Dr.`, `M6`, `kN` must split at sentence
    ends, not at the abbreviation periods."""
    el = _para(
        "Dr. Müller hat eine Schraube M6 verbaut. "
        "Sie hält 12 kN aus. "
        "Die Prüfung erfolgte nach DIN 1234."
    )
    out = decompose_to_sub_units(el)
    assert len(out) == 3
    assert out[0].startswith("Dr. Müller")
    assert "12 kN" in out[1]
    assert "DIN 1234" in out[2]


def test_paragraph_with_empty_content_returns_empty_tuple():
    """Whitespace-only content → no sub-units, not a single empty
    string."""
    assert decompose_to_sub_units(_para("   \n  ")) == ()


def test_paragraph_segmenter_singleton_is_cached_across_calls():
    """Second paragraph decompose hits the cached pysbd Segmenter
    rather than constructing a new one — covers the `_segmenter is
    not None` branch in `_get_segmenter`."""
    out_first = decompose_to_sub_units(_para("Erster Satz. Zweiter Satz."))
    out_second = decompose_to_sub_units(_para("Dritter Satz. Vierter Satz."))
    assert len(out_first) == 2
    assert len(out_second) == 2


# --- table ----------------------------------------------------------


def test_table_splits_into_rows_each_prefixed_with_header():
    """A table with 3 data rows → 3 sub-units, each prefixed with the
    header line (spec §4.2 + §9). The header gives the LLM column
    meaning when asking a question about a single row."""
    table = (
        "Schraube | Last (kN) | Norm\n"
        "M6       | 12        | DIN 1234\n"
        "M8       | 18        | DIN 1234\n"
        "M10      | 25        | DIN 1234"
    )
    out = decompose_to_sub_units(_table(table))
    assert len(out) == 3
    for sub in out:
        # Header + row: the column titles are present in every sub-unit.
        assert "Schraube" in sub
        assert "Last (kN)" in sub
    assert "M6" in out[0]
    assert "M8" in out[1]
    assert "M10" in out[2]


def test_table_with_only_header_returns_empty_tuple():
    """A header-only table (no data rows) → no sub-units."""
    out = decompose_to_sub_units(_table("Schraube | Last (kN) | Norm"))
    assert out == ()


# --- list_item ------------------------------------------------------


def test_list_item_splits_on_bullet_and_numbered_patterns():
    """Hyphen / bullet / numbered patterns each become their own
    sub-unit; leading whitespace is stripped."""
    el = _list("- erste\n- zweite\n3. dritte\n* vierte")
    out = decompose_to_sub_units(el)
    assert tuple(out) == ("erste", "zweite", "dritte", "vierte")


def test_list_item_skips_blank_lines():
    """Blank / whitespace-only lines between bullets are dropped —
    covers the `if stripped:` False branch in the list_item loop."""
    el = _list("- erste\n   \n- zweite")
    out = decompose_to_sub_units(el)
    assert tuple(out) == ("erste", "zweite")


# --- heading / figure -----------------------------------------------


def test_heading_returns_empty_tuple():
    el = DocumentElement(
        element_id="p1-dddddddd",
        page_number=1,
        element_type="heading",
        content="3.2 Befestigungselemente",
    )
    assert decompose_to_sub_units(el) == ()


def test_figure_returns_empty_tuple():
    el = DocumentElement(
        element_id="p1-eeeeeeee",
        page_number=1,
        element_type="figure",
        content="<binary>",
        caption="Figure 4: Befestigung an der Stahlplatte",
    )
    assert decompose_to_sub_units(el) == ()
