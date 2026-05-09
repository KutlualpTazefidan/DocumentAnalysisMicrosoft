"""Tests for the Verzeichnis detection + consolidated reader.

Phase 1 covers detect_registers() (the in-memory walk + reclassification).
Phase 2 covers read_register() (the on-disk consolidated lookup used
by the future RegisterLookup tool).
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
from local_pdf.provenienz.registers import (
    detect_and_persist_registers,
    detect_registers,
    read_register,
)
from local_pdf.storage.sidecar import (
    read_segments,
    write_mineru,
    write_segments,
)


def _box(
    box_id: str,
    *,
    page: int,
    reading_order: int,
    kind: BoxKind = BoxKind.paragraph,
    manually_activated: bool = False,
) -> SegmentBox:
    return SegmentBox(
        box_id=box_id,
        page=page,
        bbox=(0, 0, 100, 50),
        kind=kind,
        confidence=1.0,
        reading_order=reading_order,
        manually_activated=manually_activated,
    )


def test_detect_registers_classifies_after_heading():
    """Heading 'Inhaltsverzeichnis' followed by paragraphs → toc."""
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
        _box("p1-b1", page=1, reading_order=2),
    ]
    headings = {"p1-h0": "Inhaltsverzeichnis"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h0"].kind == BoxKind.heading  # heading itself untouched
    assert out_by_id["p1-b0"].kind == BoxKind.toc
    assert out_by_id["p1-b1"].kind == BoxKind.toc


def test_detect_registers_stops_at_next_heading():
    """A non-matching heading must end the active register."""
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),  # → bibliography
        _box("p2-h0", page=2, reading_order=0, kind=BoxKind.heading),
        _box("p2-b0", page=2, reading_order=1),  # NOT bibliography
    ]
    headings = {"p1-h0": "Literaturverzeichnis", "p2-h0": "Einleitung"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-b0"].kind == BoxKind.bibliography
    assert out_by_id["p2-b0"].kind == BoxKind.paragraph


def test_detect_registers_does_not_touch_manually_activated():
    """``manually_activated=True`` boxes are never reclassified."""
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1, manually_activated=True),
        _box("p1-b1", page=1, reading_order=2),
    ]
    headings = {"p1-h0": "Tabellenverzeichnis"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-b0"].kind == BoxKind.paragraph  # user override wins
    assert out_by_id["p1-b1"].kind == BoxKind.list_of_tables


def test_detect_registers_handles_multipage_walk():
    """Reclassification continues across page boundaries until next heading."""
    boxes = [
        _box("p2-h0", page=2, reading_order=0, kind=BoxKind.heading),
        _box("p2-b0", page=2, reading_order=1),
        _box("p3-b0", page=3, reading_order=0),
        _box("p3-b1", page=3, reading_order=1, kind=BoxKind.list_item),
        _box("p4-h0", page=4, reading_order=0, kind=BoxKind.heading),
        _box("p4-b0", page=4, reading_order=1),
    ]
    headings = {"p2-h0": "Abbildungsverzeichnis", "p4-h0": "Diskussion"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p2-b0"].kind == BoxKind.list_of_figures
    assert out_by_id["p3-b0"].kind == BoxKind.list_of_figures
    assert out_by_id["p3-b1"].kind == BoxKind.list_of_figures  # list_item also flips
    assert out_by_id["p4-b0"].kind == BoxKind.paragraph  # next heading ends it


def test_detect_registers_recognises_english_titles():
    """Pattern set covers German + common English variants."""
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
    ]
    headings = {"p1-h0": "References"}
    out = detect_registers(boxes, headings)
    assert {b.box_id: b.kind for b in out}["p1-b0"] == BoxKind.bibliography


def test_detect_registers_returns_input_unchanged_when_no_match():
    """Non-Verzeichnis headings must not flip anything."""
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
    ]
    headings = {"p1-h0": "Kapitel 3 — Vorgehen"}
    out = detect_registers(boxes, headings)
    assert out[0].kind == BoxKind.heading
    assert out[1].kind == BoxKind.paragraph


def test_detect_and_persist_registers_writes_segments(tmp_path: Path):
    """The wrapper persists the reclassified segments + returns the change count."""
    slug = "doc"
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
        _box("p1-b1", page=1, reading_order=2),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {"box_id": "p1-h0", "html_snippet": "<h2>Inhaltsverzeichnis</h2>"},
                {"box_id": "p1-b0", "html_snippet": "<p>1. Einleitung</p>"},
                {"box_id": "p1-b1", "html_snippet": "<p>2. Ergebnisse</p>"},
            ],
            "diagnostics": [],
        },
    )
    changed = detect_and_persist_registers(tmp_path, slug)
    assert changed == 2
    seg = read_segments(tmp_path, slug)
    assert seg is not None
    by_id = {b.box_id: b for b in seg.boxes}
    assert by_id["p1-b0"].kind == BoxKind.toc
    assert by_id["p1-b1"].kind == BoxKind.toc


def test_detect_and_persist_registers_returns_zero_when_no_match(tmp_path: Path):
    """No matching heading → no changes → return 0 + don't rewrite."""
    slug = "doc"
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {"box_id": "p1-h0", "html_snippet": "<h2>Einleitung</h2>"},
                {"box_id": "p1-b0", "html_snippet": "<p>Text</p>"},
            ],
            "diagnostics": [],
        },
    )
    changed = detect_and_persist_registers(tmp_path, slug)
    assert changed == 0


# ── read_register (Phase 2) ───────────────────────────────────────────


def _seed_toc_doc(tmp_path: Path, slug: str = "doc") -> None:
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1, kind=BoxKind.toc),
        _box("p2-b0", page=2, reading_order=0, kind=BoxKind.toc),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {"box_id": "p1-h0", "html_snippet": "<h2>Inhaltsverzeichnis</h2>"},
                {
                    "box_id": "p1-b0",
                    "html_snippet": "<p>1. Einleitung 1\n2. Methoden 5</p>",
                },
                {
                    "box_id": "p2-b0",
                    "html_snippet": "<p>3. Ergebnisse 12</p>",
                },
            ],
            "diagnostics": [],
        },
    )


def test_read_register_consolidates_multipage(tmp_path: Path):
    """Boxes from multiple pages roll up into one entry list + Markdown."""
    _seed_toc_doc(tmp_path)
    out = read_register(tmp_path, "doc", BoxKind.toc)
    assert out is not None
    assert out["kind"] == "toc"
    assert out["title"] == "Inhaltsverzeichnis"
    labels = [e["label"] for e in out["entries"]]
    assert "1. Einleitung" in labels
    assert "2. Methoden" in labels
    assert "3. Ergebnisse" in labels
    pages = [e["page"] for e in out["entries"]]
    assert "1" in pages and "5" in pages and "12" in pages
    assert out["source_box_ids"] == ["p1-b0", "p2-b0"]
    md = out["markdown"]
    assert "| Eintrag | Seite |" in md
    assert "| 1. Einleitung | 1 |" in md
    assert "| 3. Ergebnisse | 12 |" in md


def test_read_register_returns_none_when_no_boxes(tmp_path: Path):
    """No register-kinds → None (caller can treat as "no Verzeichnis")."""
    slug = "doc"
    boxes = [_box("p1-b0", page=1, reading_order=0)]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(tmp_path, slug, {"elements": [], "diagnostics": []})
    assert read_register(tmp_path, slug, BoxKind.toc) is None


def test_read_register_bibliography_renders_single_column(tmp_path: Path):
    """Bibliography labels typically lack page numbers — single-column table."""
    slug = "doc"
    boxes = [_box("p1-b0", page=1, reading_order=0, kind=BoxKind.bibliography)]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {
                    "box_id": "p1-b0",
                    "html_snippet": "<p>[1] Smith J. (2020). Title.\n[2] Doe A. (2021). Other.</p>",
                }
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.bibliography)
    assert out is not None
    assert "| Quelle |" in out["markdown"]
    # Markdown table must NOT have a page column
    assert "| Eintrag | Seite |" not in out["markdown"]
    assert any("[1] Smith" in e["label"] for e in out["entries"])
