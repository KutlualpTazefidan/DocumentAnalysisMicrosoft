"""Deterministic HTML-table parser used by the TableParser tool.

When a search_result has ``box_kind=table``, the LLM otherwise has
to mentally parse the cell layout to bind values to (row, column).
This module turns the HTML snippet into a structured 2D mapping so
the evaluate prompt can show the table with explicit row-label /
column-label / value triples — same idea as Calculator for numbers.

Engineering-principle layer (skill ``tabellen-2d-bindung``) tells the
LLM how to interpret the structured output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any


@dataclass(frozen=True)
class TableRow:
    """A single data row. ``label`` is the first cell (typically the
    quantity / property being measured); ``cells`` maps each column-
    header text to the corresponding cell text.
    """

    label: str
    cells: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class StructuredTable:
    """2D mapping carved out of an HTML table.

    - ``caption``: ``<caption>`` text or fallback caption supplied by
      the caller (typically the attached caption-box's text).
    - ``headers``: full first-row text per cell, INCLUDING the first
      cell which usually labels the row-label column ("Größe",
      "Eigenschaft" or empty).
    - ``rows``: data rows. Each row's ``label`` is its first cell;
      ``cells`` keys onto the column headers excluding the first.
    """

    caption: str
    headers: list[str]
    rows: list[TableRow]


class _TableExtractor(HTMLParser):
    """Single-table extractor. Captures the first <table> in the
    fed HTML; subsequent tables are ignored.
    """

    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_caption = False
        self.in_row = False
        self.in_cell = False
        self._captured = False
        self.caption: list[str] = []
        self.rows: list[list[str]] = []
        self._current_row: list[str] = []
        self._cell_buf: list[str] = []
        # Span tracking for the active <td>/<th>. Read from the
        # 'colspan' / 'rowspan' attributes on the start tag.
        self._current_colspan = 1
        self._current_rowspan = 1
        # Column pointer for the currently-active row. Advances past
        # both HTML cells (with colspan expansion) and rowspan carries
        # consumed from previous rows.
        self._next_free_col = 0
        # Rowspan carries: cells started in a previous row that
        # still need to be repeated in subsequent rows. Each carry:
        # {"col_idx": int, "text": str, "lives_remaining": int}.
        # ``lives_remaining`` is decremented every time the cell is
        # placed; carries hit 0 are pruned at row-end.
        self._row_carries: list[dict] = []

    def _consume_carry_at_col(self, col: int) -> str | None:
        """Pop one carry at the given column if it's still alive.
        Returns the carry text or None. Lives are mutated in place."""
        for carry in self._row_carries:
            if carry["col_idx"] == col and carry["lives_remaining"] > 0:
                carry["lives_remaining"] -= 1
                return str(carry["text"])
        return None

    def _has_live_carry_at_col(self, col: int) -> bool:
        return any(c["col_idx"] == col and c["lives_remaining"] > 0 for c in self._row_carries)

    def _max_live_carry_col(self) -> int:
        live = [c["col_idx"] for c in self._row_carries if c["lives_remaining"] > 0]
        return max(live) if live else -1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._captured:
            return
        if tag == "table":
            self.in_table = True
        elif tag == "caption" and self.in_table:
            self.in_caption = True
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self._current_row = []
            self._next_free_col = 0
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self._cell_buf = []
            colspan = 1
            rowspan = 1
            for k, v in attrs:
                if k == "colspan" and v is not None:
                    try:
                        colspan = max(1, int(v))
                    except ValueError:
                        colspan = 1
                elif k == "rowspan" and v is not None:
                    try:
                        rowspan = max(1, int(v))
                    except ValueError:
                        rowspan = 1
            self._current_colspan = colspan
            self._current_rowspan = rowspan
        # br within a cell becomes whitespace
        elif tag == "br" and self.in_cell:
            self._cell_buf.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "caption":
            self.in_caption = False
        elif tag in ("td", "th") and self.in_cell:
            text = " ".join("".join(self._cell_buf).split()).strip()
            colspan = self._current_colspan
            rowspan = self._current_rowspan
            # Before placing the new cell, advance past any active
            # rowspan carries occupying the upcoming column slots —
            # they were started in a previous row and must appear
            # here before any new HTML cell.
            while self._has_live_carry_at_col(self._next_free_col):
                carry_text = self._consume_carry_at_col(self._next_free_col)
                self._current_row.append(carry_text or "")
                self._next_free_col += 1
            # Place the cell, expanded by colspan, registering rowspan
            # carries when the cell extends past this row.
            for offset in range(colspan):
                self._current_row.append(text)
                if rowspan > 1:
                    self._row_carries.append(
                        {
                            "col_idx": self._next_free_col + offset,
                            "text": text,
                            "lives_remaining": rowspan - 1,
                        }
                    )
            self._next_free_col += colspan
            self._current_colspan = 1
            self._current_rowspan = 1
            self.in_cell = False
        elif tag == "tr":
            # Drain any trailing rowspan carries that extend into this
            # row past its last HTML cell (e.g. a rowspan that started
            # several rows ago and continues at a column position
            # beyond the current row's HTML content).
            max_col = self._max_live_carry_col()
            while self._next_free_col <= max_col:
                if self._has_live_carry_at_col(self._next_free_col):
                    carry_text = self._consume_carry_at_col(self._next_free_col)
                    self._current_row.append(carry_text or "")
                else:
                    # Gap before the next carry — pad with empty
                    # string so column alignment with the header row
                    # stays intact.
                    self._current_row.append("")
                self._next_free_col += 1
                max_col = self._max_live_carry_col()
            if self._current_row:
                self.rows.append(self._current_row)
            # Drop carries whose lives are exhausted.
            self._row_carries = [c for c in self._row_carries if c["lives_remaining"] > 0]
            self.in_row = False
        elif tag == "table":
            # Only capture the first table.
            self._captured = True
            self.in_table = False

    def handle_data(self, data: str) -> None:
        if self._captured:
            return
        if self.in_caption:
            self.caption.append(data)
        elif self.in_cell:
            self._cell_buf.append(data)


def parse_table(html: str, fallback_caption: str = "") -> StructuredTable | None:
    """Parse the first ``<table>`` in *html* into a StructuredTable.

    Returns ``None`` when *html* contains no parseable table or when
    the table has no rows. Caption falls back to *fallback_caption*
    (typically the search_result's ``caption_text`` payload field) if
    the table itself has no ``<caption>``.

    Whitespace in cells is collapsed; ``<br>`` becomes a space; nested
    inline tags (sup, sub, b, i, …) are silently flattened into the
    cell text.
    """
    if not html or "<table" not in html.lower():
        return None
    extractor = _TableExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        return None
    if not extractor.rows:
        return None
    headers = extractor.rows[0]
    data_rows = extractor.rows[1:]
    rows: list[TableRow] = []
    for raw in data_rows:
        if not raw:
            continue
        label = raw[0]
        cells: dict[str, str] = {}
        for i, val in enumerate(raw[1:]):
            col = headers[i + 1] if i + 1 < len(headers) else f"col{i + 1}"
            cells[col] = val
        rows.append(TableRow(label=label, cells=cells))
    caption = " ".join("".join(extractor.caption).split()).strip() or fallback_caption
    if not rows:
        return None
    return StructuredTable(caption=caption, headers=headers, rows=rows)


def lookup(table: StructuredTable, row_label: str, column_label: str) -> str | None:
    """Find the cell at intersection of (*row_label*, *column_label*).

    Matching is case-insensitive substring; first row whose label
    contains the row query AND whose cells contain the column query
    wins. Returns ``None`` when nothing matches.
    """
    rq = row_label.strip().lower()
    cq = column_label.strip().lower()
    if not rq or not cq:
        return None
    for r in table.rows:
        if rq not in r.label.lower():
            continue
        for col, val in r.cells.items():
            if cq in col.lower():
                return val
    return None


def render_markdown(table: StructuredTable) -> str:
    """Format the structured table as a Markdown-ish text block —
    used as the prompt-facing representation for the LLM.
    """
    if not table.rows:
        return ""
    n_cols = max(len(table.headers), 1)
    out: list[str] = []
    if table.caption:
        out.append(f"Caption: {table.caption}")
        out.append("")
    out.append("| " + " | ".join(table.headers) + " |")
    out.append("| " + " | ".join(["---"] * n_cols) + " |")
    for r in table.rows:
        cells_in_order: list[str] = [r.label]
        for h in table.headers[1:]:
            cells_in_order.append(r.cells.get(h, ""))
        out.append("| " + " | ".join(cells_in_order) + " |")
    return "\n".join(out)


def to_dict(table: StructuredTable) -> dict[str, Any]:
    """Plain-dict representation for JSON persistence."""
    return {
        "caption": table.caption,
        "headers": list(table.headers),
        "rows": [{"label": r.label, "cells": dict(r.cells)} for r in table.rows],
        "n_rows": len(table.rows),
        "n_cols": len(table.headers),
    }


# Quick sanity helper — pull (number, unit) pairs out of cell text so a
# downstream Calculator-Tool can compare against a hypothesis. Reuses
# the calculator's regex via a thin wrapper.
_NUMBER_IN_CELL_RE = re.compile(r"-?\d+(?:[.,\s]\d+)*\s*[A-Za-z°µΩ]+", re.UNICODE)


def cells_with_numbers(table: StructuredTable) -> list[dict[str, Any]]:
    """For each cell whose text matches a number+unit pattern, return
    ``{row_label, column, raw}``. Useful as input to the Calculator
    when we want to compare a hypothesis value against table values
    cell-by-cell.
    """
    out: list[dict[str, Any]] = []
    for r in table.rows:
        for col, raw in r.cells.items():
            if _NUMBER_IN_CELL_RE.search(raw):
                out.append({"row_label": r.label, "column": col, "raw": raw})
    return out
