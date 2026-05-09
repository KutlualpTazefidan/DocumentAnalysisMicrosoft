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
    """Heading 'Inhaltsverzeichnis' + paragraphs → all share kind=toc.
    The title heading is reclassified too so the whole block visually
    groups under one colour.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
        _box("p1-b1", page=1, reading_order=2),
    ]
    headings = {"p1-h0": "Inhaltsverzeichnis"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h0"].kind == BoxKind.toc  # title heading reclassified
    assert out_by_id["p1-b0"].kind == BoxKind.toc
    assert out_by_id["p1-b1"].kind == BoxKind.toc


def test_detect_registers_reclassifies_column_header():
    """The 'Seite' / 'Page' column-sub-heading inside a Verzeichnis is
    reclassified into the same register kind as the entries — keeps
    the heading-tree clean and the visual block consistent.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-h1", page=1, reading_order=1, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=2),
    ]
    headings = {"p1-h0": "Inhaltsverzeichnis", "p1-h1": "Seite"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h0"].kind == BoxKind.toc
    assert out_by_id["p1-h1"].kind == BoxKind.toc  # column header
    assert out_by_id["p1-b0"].kind == BoxKind.toc


def test_detect_registers_column_header_outside_verzeichnis_untouched():
    """A 'Seite' heading without an active register-walk stays a heading."""
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
    ]
    headings = {"p1-h0": "Seite"}  # no Verzeichnis preceded it
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h0"].kind == BoxKind.heading
    assert out_by_id["p1-b0"].kind == BoxKind.paragraph


def test_detect_registers_heading_with_trailing_page_continues_walk():
    """A heading-kind box whose text ends in a page number (typical
    YOLO mis-class of a TOC entry on the next page of a multi-page
    Verzeichnis) keeps the walk active and gets reclassified into
    the active register kind — not treated as a section break.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),  # entry "3.1 Foo 5"
        # YOLO mis-class: this is a TOC entry but kind=heading
        _box("p2-h0", page=2, reading_order=0, kind=BoxKind.heading),
        _box("p2-b0", page=2, reading_order=1),  # entry on continued TOC page
    ]
    headings = {
        "p1-h0": "Inhaltsverzeichnis",
        "p2-h0": "6. Temperaturen während der Erhitzungsprüfung 33",
    }
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h0"].kind == BoxKind.toc
    assert out_by_id["p1-b0"].kind == BoxKind.toc
    # The mis-classed heading is reclassified rather than ending walk.
    assert out_by_id["p2-h0"].kind == BoxKind.toc
    assert out_by_id["p2-b0"].kind == BoxKind.toc


def test_detect_registers_trailing_page_beats_bib_pattern():
    """A TOC entry "Literaturverzeichnis 45" (heading-kind, mis-class)
    must NOT switch active_register to bibliography — the trailing-page
    heuristic takes priority so the walk stays in toc.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1),
        # Mis-classed TOC entry — text matches _BIB_PATTERNS via trailing
        # tokens, but trailing-page priority should win.
        _box("p1-h1", page=1, reading_order=2, kind=BoxKind.heading),
    ]
    headings = {
        "p1-h0": "Inhaltsverzeichnis",
        "p1-h1": "Literaturverzeichnis 45",
    }
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h1"].kind == BoxKind.toc  # not bibliography!


def test_detect_registers_resets_stale_register_classifications():
    """A box currently kind=bibliography but whose context (no active
    bib-walk) doesn't justify it gets reset to paragraph. Self-healing
    for rule changes / loosened patterns leaving stale classifications.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box("p1-b0", page=1, reading_order=1, kind=BoxKind.bibliography),
    ]
    headings = {"p1-h0": "Diskussion"}  # not a Verzeichnis at all
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-h0"].kind == BoxKind.heading
    assert out_by_id["p1-b0"].kind == BoxKind.paragraph  # reset cleared it


def test_detect_registers_reset_preserves_manually_activated():
    """A user-set kind=bibliography survives reset (manually_activated=True)
    even if context wouldn't reproduce it.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.heading),
        _box(
            "p1-b0",
            page=1,
            reading_order=1,
            kind=BoxKind.bibliography,
            manually_activated=True,
        ),
    ]
    headings = {"p1-h0": "Diskussion"}
    out = detect_registers(boxes, headings)
    out_by_id = {b.box_id: b for b in out}
    assert out_by_id["p1-b0"].kind == BoxKind.bibliography  # preserved


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
    # 3 = title heading + 2 entries (title-heading reclassification is part
    # of the new "whole block shares one kind" behaviour).
    assert changed == 3
    seg = read_segments(tmp_path, slug)
    assert seg is not None
    by_id = {b.box_id: b for b in seg.boxes}
    assert by_id["p1-h0"].kind == BoxKind.toc
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
    """Three TOC-kind boxes: a title heading (filtered out by
    read_register), and two entry boxes spanning two pages.
    """
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.toc),
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
    """Boxes from multiple pages roll up into one structured entry
    list. Title heading is filtered out; remaining lines parsed
    into ``{number, title, page}``.
    """
    _seed_toc_doc(tmp_path)
    out = read_register(tmp_path, "doc", BoxKind.toc)
    assert out is not None
    assert out["kind"] == "toc"
    assert out["title"] == "Inhaltsverzeichnis"
    numbers = [e["number"] for e in out["entries"]]
    titles = [e["title"] for e in out["entries"]]
    pages = [e["page"] for e in out["entries"]]
    assert numbers == ["1", "2", "3"]
    assert titles == ["Einleitung", "Methoden", "Ergebnisse"]
    assert pages == ["1", "5", "12"]
    # Title heading box is filtered out — only entry boxes contribute.
    assert out["source_box_ids"] == ["p1-b0", "p2-b0"]
    md = out["markdown"]
    assert "| Nr. | Eintrag | Seite |" in md
    assert "| 1 | Einleitung | 1 |" in md
    assert "| 3 | Ergebnisse | 12 |" in md


def test_read_register_skips_column_header_box(tmp_path: Path):
    """A 'Seite'-only box (column-sub-header reclassified to toc) is
    filtered out — only real entry rows make it into the table.
    """
    slug = "doc"
    boxes = [
        _box("p1-h0", page=1, reading_order=0, kind=BoxKind.toc),  # title
        _box("p1-h1", page=1, reading_order=1, kind=BoxKind.toc),  # column header
        _box("p1-b0", page=1, reading_order=2, kind=BoxKind.toc),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {"box_id": "p1-h0", "html_snippet": "<h2>Inhaltsverzeichnis</h2>"},
                {"box_id": "p1-h1", "html_snippet": "<h3>Seite</h3>"},
                {"box_id": "p1-b0", "html_snippet": "<p>1. Einleitung 5</p>"},
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.toc)
    assert out is not None
    assert out["source_box_ids"] == ["p1-b0"]  # h0/h1 filtered
    assert len(out["entries"]) == 1
    assert out["entries"][0] == {"number": "1", "title": "Einleitung", "page": "5"}


def test_read_register_returns_none_when_no_boxes(tmp_path: Path):
    """No register-kinds → None (caller can treat as "no Verzeichnis")."""
    slug = "doc"
    boxes = [_box("p1-b0", page=1, reading_order=0)]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(tmp_path, slug, {"elements": [], "diagnostics": []})
    assert read_register(tmp_path, slug, BoxKind.toc) is None


def test_read_register_bibliography_renders_two_column_nr_quelle(tmp_path: Path):
    """Bibliography → ``Nr. | Quelle`` (no page column). Citation key
    inside ``[…]`` becomes ``number``; the rest becomes ``title``.
    """
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
    md = out["markdown"]
    assert "| Nr. | Quelle |" in md
    assert "| Nr. | Eintrag | Seite |" not in md
    nums = [e["number"] for e in out["entries"]]
    titles = [e["title"] for e in out["entries"]]
    assert nums == ["1", "2"]
    assert titles[0].startswith("Smith J. (2020)")
    assert titles[1].startswith("Doe A. (2021)")


def test_read_register_bibliography_merges_continuation_lines(tmp_path: Path):
    """A bib entry that wraps onto multiple lines inside ONE box collapses
    into a single entry: continuation lines get appended to the previous
    [N]-prefixed line.
    """
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
                    "html_snippet": (
                        "<p>[9] Advisory Material for the IAEA Regulations\n"
                        "IAEA Safety Standard Series No. TS-G-1.1\n"
                        "IAEA, Vienna (2002)</p>"
                    ),
                }
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.bibliography)
    assert out is not None
    assert len(out["entries"]) == 1
    e = out["entries"][0]
    assert e["number"] == "9"
    assert "Advisory Material" in e["title"]
    assert "IAEA Safety Standard Series" in e["title"]
    assert "Vienna (2002)" in e["title"]


def test_read_register_bibliography_merges_across_boxes(tmp_path: Path):
    """A continuation box (no leading [N]) is appended to the previous
    entry's title — handles cases where YOLO split one logical bib
    citation across multiple boxes.
    """
    slug = "doc"
    boxes = [
        _box("p1-b0", page=1, reading_order=0, kind=BoxKind.bibliography),
        _box("p1-b1", page=1, reading_order=1, kind=BoxKind.bibliography),
        _box("p1-b2", page=1, reading_order=2, kind=BoxKind.bibliography),
    ]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>[9] Advisory Material for IAEA</p>"},
                {"box_id": "p1-b1", "html_snippet": "<p>IAEA Safety Standard Series</p>"},
                {"box_id": "p1-b2", "html_snippet": "<p>[10] GNS B 136/92</p>"},
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.bibliography)
    assert out is not None
    assert len(out["entries"]) == 2  # [9] (with merged b1) + [10]
    assert out["entries"][0]["number"] == "9"
    assert "IAEA Safety Standard" in out["entries"][0]["title"]
    assert out["entries"][1]["number"] == "10"


def test_read_register_bibliography_orphan_line_starts_first_entry(tmp_path: Path):
    """If the very first bib line has no [N] prefix (rare), it becomes
    the first entry on its own rather than getting dropped.
    """
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
                    "html_snippet": "<p>Free-form leading citation\n[1] Müller</p>",
                }
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.bibliography)
    assert out is not None
    assert len(out["entries"]) == 2
    assert out["entries"][0] == {
        "number": "",
        "title": "Free-form leading citation",
        "page": "",
    }
    assert out["entries"][1]["number"] == "1"


def test_read_register_list_of_tables_strips_table_prefix(tmp_path: Path):
    """LOT entries like 'Tabelle 5: Konservative Werte 12' → number=5,
    title=Konservative Werte, page=12.
    """
    slug = "doc"
    boxes = [_box("p1-b0", page=1, reading_order=0, kind=BoxKind.list_of_tables)]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {
                    "box_id": "p1-b0",
                    "html_snippet": (
                        "<p>Tabelle 5: Konservative Werte 12\nTab. 6 - Reaktor­typen 18</p>"
                    ),
                }
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.list_of_tables)
    assert out is not None
    nums = [e["number"] for e in out["entries"]]
    titles = [e["title"] for e in out["entries"]]
    pages = [e["page"] for e in out["entries"]]
    assert nums == ["5", "6"]
    assert "Konservative Werte" in titles[0]
    assert "Reaktor" in titles[1]
    assert pages == ["12", "18"]


def test_read_register_list_of_figures_strips_figure_prefix(tmp_path: Path):
    """LOF entries like 'Abb. 4: Schema der Anlage 8' → number=4."""
    slug = "doc"
    boxes = [_box("p1-b0", page=1, reading_order=0, kind=BoxKind.list_of_figures)]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {
                    "box_id": "p1-b0",
                    "html_snippet": "<p>Abb. 4: Schema der Anlage 8</p>",
                }
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.list_of_figures)
    assert out is not None
    assert out["entries"] == [{"number": "4", "title": "Schema der Anlage", "page": "8"}]


def test_read_register_unnumbered_entry_keeps_title(tmp_path: Path):
    """Entries without a leading number (``Vorwort … iii``) yield
    ``number=""`` rather than dropping the line. Title and page survive.
    """
    slug = "doc"
    boxes = [_box("p1-b0", page=1, reading_order=0, kind=BoxKind.toc)]
    write_segments(tmp_path, slug, SegmentsFile(slug=slug, boxes=boxes, raster_dpi=288))
    write_mineru(
        tmp_path,
        slug,
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>Vorwort iii</p>"},
            ],
            "diagnostics": [],
        },
    )
    out = read_register(tmp_path, slug, BoxKind.toc)
    assert out is not None
    assert out["entries"] == [{"number": "", "title": "Vorwort", "page": "iii"}]
