"""Shared HTML → flat-text converter used by both the search corpus and
the chunk-text persistence path.

Tables are rendered as Markdown (``| col | col |\\n| --- | --- |\\n|
cell | cell |``) so the LLM agent sees row + column structure instead
of space-separated cell text. Everything else is stripped to plain
text. BM25 tokenisation drops punctuation anyway, so the markdown
pipes don't affect search scoring — but the human + LLM facing
hit-text becomes readable.

Single canonical implementation here; both the in-doc searcher and
the provenienz session-creation path call into this module so a
table renders identically wherever the user sees it.
"""

from __future__ import annotations

import re

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TABLE_RE = re.compile(r"<table[^>]*>.*?</table>", re.DOTALL | re.IGNORECASE)
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
_TD_RE = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.DOTALL | re.IGNORECASE)


def render_table_as_markdown(table_html: str) -> str:
    """Convert a single ``<table>...</table>`` block to a Markdown table.
    Returns ``""`` for empty / unparseable input so callers can fall
    back to the flat strip.
    """
    rows: list[list[str]] = []
    for tr_match in _TR_RE.finditer(table_html):
        cells = []
        for td_match in _TD_RE.finditer(tr_match.group(1)):
            cell_html = td_match.group(1)
            cell_text = _WS_RE.sub(" ", _TAG_RE.sub(" ", cell_html)).strip()
            cell_text = cell_text.replace("|", "\\|")
            cells.append(cell_text or " ")
        if cells:
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    for r in rows:
        while len(r) < width:
            r.append(" ")
    header = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * width) + " |"
    body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
    return "\n".join(part for part in (header, sep, body) if part)


def strip_html(html: str) -> str:
    """HTML → flat agent-readable text with Markdown tables preserved.

    Used by:
    - ``provenienz.searcher.InDocSearcher`` for hit text rendering
    - ``provenienz.create_session`` / ``promote_search_result`` for
      chunk text persistence
    - ``provenienz.refresh_chunk`` for source-diff comparison
    """
    if not html:
        return ""
    text = _TABLE_RE.sub(
        lambda m: "\n\n" + render_table_as_markdown(m.group(0)) + "\n\n",
        html,
    )
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
