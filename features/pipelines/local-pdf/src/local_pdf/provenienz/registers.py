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


_REGISTER_KIND_SET: frozenset[BoxKind] = frozenset(
    {
        BoxKind.toc,
        BoxKind.list_of_tables,
        BoxKind.list_of_figures,
        BoxKind.bibliography,
    }
)


def _reset_register_classifications(
    boxes: list[SegmentBox], heading_text_lookup: dict[str, str]
) -> list[SegmentBox]:
    """Self-heal: revert non-manually-activated register-kind boxes
    back to their pre-walk kind so a re-run with updated rules picks
    a fresh classification instead of inheriting stale state.

    A box's pre-walk kind is recovered from its text:
      - matches a Verzeichnis title pattern OR the column-header
        whitelist → ``kind=heading``
      - else → ``kind=paragraph``

    Original list/list_item/table information IS lost on reset — but
    that loss already happens on the FIRST walk (the entry-kind set
    collapses into one register-kind), so reset doesn't make things
    worse. ``manually_activated=True`` boxes are left untouched.
    """
    out: list[SegmentBox] = []
    for b in boxes:
        if b.kind not in _REGISTER_KIND_SET or b.manually_activated:
            out.append(b)
            continue
        text = heading_text_lookup.get(b.box_id, "").strip()
        is_title = any(pat.match(text) for pat, _ in _HEADING_TO_KIND)
        is_col = bool(_VERZEICHNIS_COLUMN_HEADERS.match(text))
        new_kind = BoxKind.heading if (is_title or is_col) else BoxKind.paragraph
        out.append(b.model_copy(update={"kind": new_kind}))
    return out


def detect_registers(
    boxes: list[SegmentBox], heading_text_lookup: dict[str, str]
) -> list[SegmentBox]:
    """Walk *boxes* in (page, reading_order). When a heading matches a
    Verzeichnis pattern, reclassify ALL boxes belonging to that
    Verzeichnis — title heading, ``Seite``/``Page`` column-sub-header,
    plus the entry boxes (paragraph/list_item/table) — into the
    matching register kind. The walk continues until a real
    section-heading break (e.g. ``Einleitung``, ``Diskussion``) ends
    it, or a different Verzeichnis-pattern starts a new walk.

    Reclassifying the title heading (``Inhaltsverzeichnis``) keeps the
    whole block visually grouped under one colour and removes the
    Verzeichnis from the section heading-tree (it's not a section of
    the document — it's an index OF the sections).

    Robustness rules inside the heading branch (priority order):

    1. Column-header sub-headings (``Seite``, ``Page``, …) keep the
       walk active and get reclassified into the register-kind.
    2. Headings whose text ends in a page-number / roman numeral
       (``5.2.3 Berechnungsergebnisse … 24``) keep the walk active
       and get reclassified — typical YOLO mis-class of a TOC entry
       as heading because of large font.
    3. Otherwise, try the Verzeichnis title patterns; matching ones
       start (or switch) the active register kind.
    4. Anything else is a real section break and ends the walk.

    The function runs a self-healing reset before the walk so prior
    register classifications that no longer fit the current rule set
    get cleaned up (see :func:`_reset_register_classifications`).

    Args:
        boxes: SegmentBox list (frozen — input is not mutated).
        heading_text_lookup: ``{box_id: plain_text}`` for at least every
            heading box. Other entries are ignored.

    Returns:
        A NEW list with reclassified boxes (frozen pydantic instances).
        ``manually_activated=True`` boxes are passed through unchanged.
    """
    sorted_boxes = sorted(boxes, key=lambda b: (b.page, b.reading_order))
    sorted_boxes = _reset_register_classifications(sorted_boxes, heading_text_lookup)
    result: list[SegmentBox] = list(sorted_boxes)
    active_register: BoxKind | None = None
    for i, b in enumerate(result):
        if b.kind == BoxKind.heading:
            text = heading_text_lookup.get(b.box_id, "").strip()
            # (1) + (2): inside an active walk, certain headings
            # extend rather than break it. Order matters — these
            # checks come BEFORE _HEADING_TO_KIND so a TOC entry
            # like "Literaturverzeichnis 45" doesn't get mis-read
            # as a bibliography title (the trailing-tokens regex on
            # _BIB_PATTERNS would otherwise match).
            if active_register is not None and (
                _VERZEICHNIS_COLUMN_HEADERS.match(text) or _TRAILING_PAGE_RE.match(text)
            ):
                if not b.manually_activated:
                    result[i] = b.model_copy(update={"kind": active_register})
                continue
            # (3) + (4): does this heading start a Verzeichnis, or
            # is it a real section break?
            new_kind: BoxKind | None = None
            for pattern, kind in _HEADING_TO_KIND:
                if pattern.match(text):
                    new_kind = kind
                    break
            if new_kind is not None:
                active_register = new_kind
                if not b.manually_activated:
                    result[i] = b.model_copy(update={"kind": active_register})
            else:
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


# Per-kind number/title splitters. Each pattern carves a leading
# "number" (chapter no, table no, figure no, citation key) off a line
# *after* the trailing page has already been stripped off. Falling
# back to ``number=""`` keeps unnumbered entries (``Vorwort``,
# free-form bibliography) intact instead of dropping them.
_TOC_NUMBER_RE = re.compile(
    # Numeric (1, 1.2, 1.2.3, optional trailing dot) OR uppercase letter
    # + optional sub-numbers (A, A.1) — typical TOC dewey or
    # appendix-letter prefix.
    r"^(?P<num>\d+(?:\.\d+)*\.?|[A-Z](?:\.\d+)*\.?)\s+(?P<title>.+)$"
)
# Trailing-separator class — table/figure entries in real PDFs use a
# colon, period, ASCII hyphen, en-dash or em-dash before the title.
# en-/em-dash are intentional (RUF001 silenced).
_NUM_TITLE_SEP = r"[:.\-–—]?"  # noqa: RUF001
# "Tabelle 5: Konservative Werte" / "Tab. 5 Konservative Werte" /
# "Table 5 - Conservative values".
_LOT_NUMBER_RE = re.compile(
    r"^(?:Tabelle|Tab\.?|Table)\s+(?P<num>\d+(?:[.\-]\d+)*\.?)\s*"
    + _NUM_TITLE_SEP
    + r"\s*(?P<title>.*)$",
    re.IGNORECASE,
)
_LOF_NUMBER_RE = re.compile(
    r"^(?:Abbildung|Abb\.?|Figure|Fig\.?)\s+(?P<num>\d+(?:[.\-]\d+)*\.?)\s*"
    + _NUM_TITLE_SEP
    + r"\s*(?P<title>.*)$",
    re.IGNORECASE,
)
# "[3] Müller, K. (2003). Reaktorsicherheit." / "(Schmidt 2010) …" —
# bracket-prefixed citation keys. Length cap (40 chars inside the
# brackets) avoids accidentally swallowing parens that appear inside
# free-form citation text.
_BIB_NUMBER_RE = re.compile(r"^[\[(](?P<num>[^\])]{1,40})[\])]\s*(?P<title>.*)$")

_NUMBER_RE_BY_KIND: dict[BoxKind, re.Pattern[str]] = {
    BoxKind.toc: _TOC_NUMBER_RE,
    BoxKind.list_of_tables: _LOT_NUMBER_RE,
    BoxKind.list_of_figures: _LOF_NUMBER_RE,
    BoxKind.bibliography: _BIB_NUMBER_RE,
}

# Lookup the title-heading regex by kind — read_register uses this to
# skip the Verzeichnis-title box (which detect_registers reclassified
# into the same kind as the entries).
_TITLE_PATTERN_BY_KIND: dict[BoxKind, re.Pattern[str]] = {k: p for p, k in _HEADING_TO_KIND}


def _parse_entry_line(line: str, kind: BoxKind) -> dict[str, str]:
    """Split one Verzeichnis line into ``{number, title, page}``.

    Two-step parse: trailing page first (``…1. Einleitung … 5`` →
    label=``1. Einleitung``, page=``5``), then per-kind number/title
    split (TOC: ``1. Einleitung`` → number=``1``, title=``Einleitung``).

    Empty fields are returned as ``""`` so the caller never has to
    handle ``None``.
    """
    m_page = _TRAILING_PAGE_RE.match(line)
    if m_page:
        label, page = m_page.group("label").strip(), m_page.group("page")
    else:
        label, page = line, ""
    pattern = _NUMBER_RE_BY_KIND[kind]
    m_num = pattern.match(label)
    if m_num:
        return {
            "number": m_num.group("num").rstrip(".").strip(),
            "title": m_num.group("title").strip(),
            "page": page,
        }
    return {"number": "", "title": label, "page": page}


def read_register(data_root: Path, slug: str, kind: BoxKind) -> dict | None:
    """Walk segments.json for boxes with ``kind == kind``, sorted by
    (page, reading_order). Concatenate their html_snippet → text. Render
    as one consolidated Markdown table with structured
    ``{number, title, page}`` rows.

    The Verzeichnis-title heading and ``Seite``/``Page`` column-header
    sub-heading were also reclassified into the register-kind by
    :func:`detect_registers`. They get filtered out here by re-applying
    the same patterns to each box's first line — only entries make it
    into the table.

    Args:
        data_root: data root directory.
        slug: document slug.
        kind: which register to consolidate. Must be one of
            ``toc | list_of_tables | list_of_figures | bibliography``.

    Returns:
        ``{
            "kind": "toc",
            "title": "Inhaltsverzeichnis",
            "entries": [{"number": "1", "title": "Einleitung", "page": "5"}, ...],
            "markdown": "| Nr. | Eintrag | Seite |\\n| --- | --- | --- |\\n...",
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

    title_pattern = _TITLE_PATTERN_BY_KIND[kind]
    # Step 1: collect raw lines and the boxes that contributed them.
    # Title-heading and column-header boxes (which share the register
    # kind after detect_registers) are skipped — they carry no entry data.
    lines: list[str] = []
    source_box_ids: list[str] = []
    for b in register_boxes:
        text = text_by_id.get(b.box_id, "").strip()
        if not text:
            continue
        first_line = text.splitlines()[0].strip()
        if title_pattern.match(first_line) or _VERZEICHNIS_COLUMN_HEADERS.match(first_line):
            continue
        source_box_ids.append(b.box_id)
        for line in (ln.strip() for ln in text.splitlines()):
            if not line:
                continue
            lines.append(line)
    # Step 2: convert raw lines to logical entries. For TOC / list_of_*
    # one line ≈ one entry. Bibliography entries routinely span multiple
    # lines (and multiple boxes) — group lines without a bracket-prefix
    # as continuations of the previous entry so "[9] Title\nSubtitle\nVienna"
    # collapses into one row instead of three.
    entries: list[dict[str, str]] = []
    if kind == BoxKind.bibliography:
        entry_texts: list[str] = []
        for line in lines:
            if _BIB_NUMBER_RE.match(line) or not entry_texts:
                entry_texts.append(line)
            else:
                entry_texts[-1] += " " + line
        entries = [_parse_entry_line(t, kind) for t in entry_texts]
    else:
        entries = [_parse_entry_line(line, kind) for line in lines]

    title = _REGISTER_TITLES[kind]
    is_bib = kind == BoxKind.bibliography
    if is_bib:
        # Bibliography entries usually don't have a page number — render
        # as Nr. + Quelle and drop the page column.
        header = "| Nr. | Quelle |"
        sep = "| --- | --- |"
        rows = [f"| {_md_escape(e['number'])} | {_md_escape(e['title'])} |" for e in entries]
    else:
        header = "| Nr. | Eintrag | Seite |"
        sep = "| --- | --- | --- |"
        rows = [
            f"| {_md_escape(e['number'])} | {_md_escape(e['title'])} | {_md_escape(e['page'])} |"
            for e in entries
        ]
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


# ── RegisterLookup tool executor ──────────────────────────────────────
#
# Patterns the agent's claim/query might mention. Each maps to a
# Verzeichnis kind so we know which register to consult. The captured
# group is the entry number/key.

_KIND_DETECT_PATTERNS: list[tuple[re.Pattern[str], BoxKind]] = [
    (
        re.compile(r"\b(?:Tabellen?|Tab\.|Table)\s*(\d+(?:\.\d+)*)", re.IGNORECASE),
        BoxKind.list_of_tables,
    ),
    (
        re.compile(
            r"\b(?:Abbildung(?:en)?|Abb\.|Figure|Fig\.)\s*(\d+(?:\.\d+)*)",
            re.IGNORECASE,
        ),
        BoxKind.list_of_figures,
    ),
    # Square-bracket citations are bib-keys; round-paren cite-keys
    # ("(Schmidt 2010)") are intentionally NOT matched here — too many
    # false positives in nuclear-engineering text where parens are
    # routinely used for unit annotations.
    (re.compile(r"\[(\d{1,3})\]"), BoxKind.bibliography),
    (
        re.compile(
            r"\b(?:Kapitel|Abschnitt|Abs\.|Section|Sec\.)\s*(\d+(?:\.\d+)*)",
            re.IGNORECASE,
        ),
        BoxKind.toc,
    ),
]


def detect_register_target(query: str) -> tuple[BoxKind, str] | None:
    """Heuristically infer ``(kind, number)`` from a free-text claim.

    Walks ``_KIND_DETECT_PATTERNS`` in priority order and returns the
    first match. Returns ``None`` when the text contains no obvious
    Verzeichnis-reference — caller should fall back to a normal search
    instead of forcing a register lookup.

    Examples
    --------
    >>> detect_register_target("siehe Tabelle 5")
    (BoxKind.list_of_tables, "5")
    >>> detect_register_target("nothing here")  # → None
    """
    if not query:
        return None
    for pattern, kind in _KIND_DETECT_PATTERNS:
        m = pattern.search(query)
        if m:
            return kind, m.group(1)
    return None


def lookup_register_entry(
    data_root: Path,
    slug: str,
    kind: BoxKind,
    number: str,
) -> dict | None:
    """Find a single ``{number, title, page}`` entry within a Verzeichnis
    by its number. Number comparison is normalised — trailing dots,
    surrounding whitespace, and case differences are ignored — so
    ``"5"``, ``"5."``, ``"5 "`` all match a TOC entry stored as ``"5"``.

    Returns ``None`` when:
      - the document has no Verzeichnis of *kind*;
      - no entry with that number exists.
    """
    register = read_register(data_root, slug, kind)
    if register is None:
        return None
    target = number.strip().rstrip(".").lower()
    if not target:
        return None
    for e in register["entries"]:
        if e["number"].strip().rstrip(".").lower() == target:
            # Construct a fresh dict so the return type is concrete
            # (read_register is loosely typed dict | None, mypy rightly
            # complains about returning the inferred-Any element).
            return {"number": e["number"], "title": e["title"], "page": e["page"]}
    return None
