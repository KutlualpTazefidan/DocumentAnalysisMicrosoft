"""Detect Verzeichnisse (TOC / list-of-tables / list-of-figures /
bibliography) in a document's segments + reclassify their entry boxes
to the matching BoxKind. Runs after VLM extraction completes.

A Verzeichnis is a navigation/reference section: the heading text
matches one of the well-known German/English patterns
(``Inhaltsverzeichnis``, ``Tabellenverzeichnis``, ``Literaturverzeichnis``,
``References`` ...) and every subsequent paragraph/list_item/table box
(until the next heading) is reclassified into the matching kind.

The detection is heuristic and intentionally conservative:
- only headings whose text matches a known pattern flip the active
  register; non-matching headings switch it OFF
- ``manually_activated=True`` boxes are NEVER touched — user override
  always wins
- input is treated as immutable; a NEW list is returned

A consolidated reader (:func:`read_register`) walks segments.json +
mineru.json and returns one {kind, title, entries, markdown,
source_box_ids} dict per Verzeichnis kind, suitable for surfacing as a
single reference table to the LLM agent via the ``RegisterLookup``
tool.
"""

from __future__ import annotations

import re
from pathlib import Path  # noqa: TC003

from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
from local_pdf.provenienz.text import strip_html
from local_pdf.storage.sidecar import read_mineru, read_segments, write_segments

# Heading-text patterns (case-insensitive, anchored). Punctuation /
# trailing whitespace is tolerated so ``Inhaltsverzeichnis:`` and
# ``  Literatur  `` still match.
# Optional trailing tokens — page numbers ("Literaturverzeichnis 1"),
# continuation markers ("(Fortsetzung)"), section dashes etc.
# Capped at 40 chars to avoid swallowing a TOC entry like
# "5. Literaturverzeichnis ........... 45".
_TRAILING_TOKENS = r"(\s+.{0,40})?"
_TOC_PATTERNS = re.compile(
    r"^\s*(inhaltsverzeichnis|inhalt|contents|table of contents)"
    + _TRAILING_TOKENS
    + r"\s*[:.]?\s*$",
    re.IGNORECASE,
)
_LOT_PATTERNS = re.compile(
    r"^\s*(tabellenverzeichnis|liste der tabellen|list of tables)"
    + _TRAILING_TOKENS
    + r"\s*[:.]?\s*$",
    re.IGNORECASE,
)
_LOF_PATTERNS = re.compile(
    r"^\s*(abbildungsverzeichnis|liste der abbildungen|list of figures)"
    + _TRAILING_TOKENS
    + r"\s*[:.]?\s*$",
    re.IGNORECASE,
)
_BIB_PATTERNS = re.compile(
    r"^\s*(literaturverzeichnis|literatur|bibliograph(ie|y)|quellen|references|"
    r"weiterführende literatur)" + _TRAILING_TOKENS + r"\s*[:.]?\s*$",
    re.IGNORECASE,
)

_HEADING_TO_KIND: list[tuple[re.Pattern[str], BoxKind]] = [
    (_TOC_PATTERNS, BoxKind.toc),
    (_LOT_PATTERNS, BoxKind.list_of_tables),
    (_LOF_PATTERNS, BoxKind.list_of_figures),
    (_BIB_PATTERNS, BoxKind.bibliography),
]

# Kinds the walk reclassifies into the active register-kind.
# heading + figure + caption + formula + auxiliary are left alone so the
# section structure stays intact (the heading itself, any figures that
# happen to live inside the Verzeichnis page, etc.).
_RECLASSIFIABLE_KINDS = frozenset({BoxKind.paragraph, BoxKind.list_item, BoxKind.table})

# Set of register kinds, exposed for searcher exclusion + downstream
# consumers. Kept as strings so callers don't all need the BoxKind import.
REGISTER_KINDS: frozenset[str] = frozenset(
    {
        BoxKind.toc.value,
        BoxKind.list_of_tables.value,
        BoxKind.list_of_figures.value,
        BoxKind.bibliography.value,
    }
)

_REGISTER_TITLES: dict[BoxKind, str] = {
    BoxKind.toc: "Inhaltsverzeichnis",
    BoxKind.list_of_tables: "Tabellenverzeichnis",
    BoxKind.list_of_figures: "Abbildungsverzeichnis",
    BoxKind.bibliography: "Literaturverzeichnis",
}

# Trailing-page-number heuristic for entry parsing. Matches "1", "12",
# "iv", "VII" and anything in between separated from the label by dots,
# spaces or tabs (typical TOC dot-leader rendering).
_TRAILING_PAGE_RE = re.compile(
    r"^(?P<label>.*?)[\s\.·…]+(?P<page>\d+|[ivxlcdm]+)\s*$",
    re.IGNORECASE,
)


# Whitelist of column-header / sub-heading texts within a Verzeichnis
# that should NOT end an active walk. Real Verzeichnisse often have a
# "Seite" / "Page" sub-heading as a column label between the title
# heading and the entries.
_VERZEICHNIS_COLUMN_HEADERS = re.compile(
    r"^\s*(seite|page|eintrag|nr\.?|nummer|number|titel|title|"
    r"reference|fundstelle|quelle)\s*[:.]?\s*$",
    re.IGNORECASE,
)


def detect_registers(
    boxes: list[SegmentBox], heading_text_lookup: dict[str, str]
) -> list[SegmentBox]:
    """Walk *boxes* in (page, reading_order). When a heading matches a
    Verzeichnis pattern, reclassify all subsequent
    paragraph/list_item/table boxes as the matching register kind until
    the walk hits a SECTION-heading break (numbered or "Kapitel N…")
    OR a different Verzeichnis-pattern heading.

    Headings that don't match either pattern (e.g. column-headers like
    "Seite" within a TOC) are ignored — they don't end the walk.

    Args:
        boxes: SegmentBox list (frozen — input is not mutated).
        heading_text_lookup: ``{box_id: plain_text}`` for at least every
            heading box. Other entries are ignored.

    Returns:
        A NEW list with reclassified boxes (frozen pydantic instances).
        ``manually_activated=True`` boxes are passed through unchanged.
    """
    sorted_boxes = sorted(boxes, key=lambda b: (b.page, b.reading_order))
    result: list[SegmentBox] = list(sorted_boxes)
    active_register: BoxKind | None = None
    for i, b in enumerate(result):
        if b.kind == BoxKind.heading:
            text = heading_text_lookup.get(b.box_id, "").strip()
            new_kind: BoxKind | None = None
            for pattern, kind in _HEADING_TO_KIND:
                if pattern.match(text):
                    new_kind = kind
                    break
            if new_kind is not None:
                # Verzeichnis switch — start (or restart) the walk.
                active_register = new_kind
            elif _VERZEICHNIS_COLUMN_HEADERS.match(text):
                # In-Verzeichnis column header ("Seite", "Page",
                # "Titel", etc.) — keep walking, don't end the
                # active register.
                pass
            else:
                # Any other heading is a real section break and ends
                # the walk. The next register heading restarts it.
                active_register = None
            continue
        if active_register is None:
            continue
        if b.manually_activated:
            continue
        if b.kind in _RECLASSIFIABLE_KINDS:
            result[i] = b.model_copy(update={"kind": active_register})
    return result


def _build_heading_text_lookup(mineru_data: dict | None) -> dict[str, str]:
    """Read mineru.json elements and return ``{box_id: stripped_text}``
    for use as the second argument to :func:`detect_registers`.

    Returns ``{}`` when ``mineru_data`` is None.
    """
    if not mineru_data:
        return {}
    out: dict[str, str] = {}
    for el in mineru_data.get("elements", []):
        bid = el.get("box_id")
        if not bid:
            continue
        out[bid] = strip_html(el.get("html_snippet", ""))
    return out


def detect_and_persist_registers(data_root: Path, slug: str) -> int:
    """Run :func:`detect_registers` against *slug*'s on-disk segments +
    mineru data, persist the updated segments.json, and return the
    number of boxes that were reclassified.

    No-op (returns 0) when segments.json doesn't exist yet or when no
    boxes change kind. Safe to call repeatedly — the second pass is a
    fixpoint because the matched headings keep matching.
    """
    seg = read_segments(data_root, slug)
    if seg is None:
        return 0
    mineru = read_mineru(data_root, slug)
    heading_text = _build_heading_text_lookup(mineru)
    new_boxes = detect_registers(list(seg.boxes), heading_text)
    realigned = _by_box_id(list(seg.boxes), new_boxes)
    changed = sum(1 for old, new in zip(seg.boxes, realigned, strict=True) if old.kind != new.kind)
    if changed == 0:
        return 0
    # Preserve the original ordering in segments.json — detect_registers
    # sorts internally for the walk but persistence keeps the prior order.
    new_by_id = {b.box_id: b for b in new_boxes}
    reordered = [new_by_id.get(b.box_id, b) for b in seg.boxes]
    write_segments(
        data_root,
        slug,
        SegmentsFile(slug=seg.slug, boxes=reordered, raster_dpi=seg.raster_dpi),
    )
    return changed


def _by_box_id(originals: list[SegmentBox], updated: list[SegmentBox]) -> list[SegmentBox]:
    """Re-align *updated* (sorted by (page, reading_order)) back to the
    order of *originals* so the change-count comparison is positional.
    """
    by_id = {b.box_id: b for b in updated}
    return [by_id.get(b.box_id, b) for b in originals]


def read_register(data_root: Path, slug: str, kind: BoxKind) -> dict | None:
    """Walk segments.json for boxes with ``kind == kind``, sorted by
    (page, reading_order). Concatenate their html_snippet → text. Render
    as one consolidated Markdown table with columns derived from line
    structure (e.g. ``Eintrag | Seite`` for TOC).

    Args:
        data_root: data root directory.
        slug: document slug.
        kind: which register to consolidate. Must be one of
            ``toc | list_of_tables | list_of_figures | bibliography``.

    Returns:
        ``{
            "kind": "toc",
            "title": "Inhaltsverzeichnis",
            "entries": [{"label": "1. Einleitung", "page": "1"}, ...],
            "markdown": "| Eintrag | Seite |\\n| --- | --- |\\n...",
            "source_box_ids": ["p2-b1", "p2-b2", ...],
        }``
        or ``None`` when no boxes of that kind exist.
    """
    if kind not in _REGISTER_TITLES:
        return None
    seg = read_segments(data_root, slug)
    if seg is None:
        return None
    register_boxes = sorted(
        (b for b in seg.boxes if b.kind == kind),
        key=lambda b: (b.page, b.reading_order),
    )
    if not register_boxes:
        return None
    mineru = read_mineru(data_root, slug)
    text_by_id: dict[str, str] = {}
    if mineru is not None:
        for el in mineru.get("elements", []):
            text_by_id[el["box_id"]] = strip_html(el.get("html_snippet", ""))

    entries: list[dict[str, str]] = []
    source_box_ids: list[str] = []
    for b in register_boxes:
        source_box_ids.append(b.box_id)
        text = text_by_id.get(b.box_id, "").strip()
        if not text:
            continue
        for line in (ln.strip() for ln in text.splitlines()):
            if not line:
                continue
            m = _TRAILING_PAGE_RE.match(line)
            if m:
                entries.append({"label": m.group("label").strip(), "page": m.group("page")})
            else:
                entries.append({"label": line, "page": ""})

    title = _REGISTER_TITLES[kind]
    is_bib = kind == BoxKind.bibliography
    if is_bib:
        # Bibliography entries usually don't have a page number — render
        # as a single-column list of the labels, drop the page column.
        header = "| Quelle |"
        sep = "| --- |"
        rows = [f"| {_md_escape(e['label'])} |" for e in entries]
    else:
        header = "| Eintrag | Seite |"
        sep = "| --- | --- |"
        rows = [f"| {_md_escape(e['label'])} | {_md_escape(e['page'])} |" for e in entries]
    markdown = "\n".join([header, sep, *rows])
    return {
        "kind": kind.value,
        "title": title,
        "entries": entries,
        "markdown": markdown,
        "source_box_ids": source_box_ids,
    }


def _md_escape(s: str) -> str:
    """Escape ``|`` so a literal pipe inside a label doesn't break the
    Markdown table. No other escaping needed here."""
    return s.replace("|", "\\|")
