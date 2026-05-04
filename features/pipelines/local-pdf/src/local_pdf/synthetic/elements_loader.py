"""Bridge between local-pdf's mineru.json output and the goldens A.5
synthetic generator's ElementsLoader contract.

The synthetic generator (``goldens.creation.synthetic.synthesise_iter``)
takes anything that satisfies the ``ElementsLoader`` Protocol — i.e. a
``.elements()`` method returning ``list[DocumentElement]``. Our
local-pdf pipeline stores per-element data in ``mineru.json`` (one
entry per SegmentBox) plus per-box metadata in ``segments.json``
(kind, page, bbox). This loader joins the two, drops kinds that aren't
suitable for question generation (figure, auxiliary, discard), and
yields ``DocumentElement``s keyed by the SegmentBox ``box_id``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from goldens.creation.elements.adapter import DocumentElement

from local_pdf.api.schemas import BoxKind
from local_pdf.storage.sidecar import read_mineru, read_segments

if TYPE_CHECKING:
    from pathlib import Path

    from goldens.schemas import ElementType


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_TR_RE = re.compile(r"<\s*tr\b[^>]*>(.*?)<\s*/\s*tr\s*>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<\s*(?:t[hd])\b[^>]*>(.*?)<\s*/\s*t[hd]\s*>", re.IGNORECASE | re.DOTALL)

# 4-tuple bbox: x0, y0, x1, y1.
Bbox = tuple[float, float, float, float]


def _strip_html(html: str) -> str:
    """Reduce an html_snippet to plain text for question prompting.

    Tag stripping is safe here because the snippets in mineru.json come
    from our own pipeline (no malicious HTML) and the synthetic
    generator wants narrative text, not markup.
    """
    text = _TAG_RE.sub(" ", html or "")
    return _WS_RE.sub(" ", text).strip()


def _table_html_to_text(html: str) -> str:
    """Render <table> HTML as one row per line, cells joined with " | ".

    The synthetic generator's table decomposer (decompose_to_sub_units)
    splits content on newlines and treats line 0 as the header. Without
    row-preserving newlines every cell collapses into a single line and
    the element gets skipped with reason "no_sub_units".
    """
    rows = _TR_RE.findall(html or "")
    if not rows:
        return _strip_html(html)
    lines: list[str] = []
    for row_html in rows:
        cells = [_strip_html(c) for c in _CELL_RE.findall(row_html)]
        cells = [c for c in cells if c]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


# Map local-pdf BoxKind → goldens ElementType.
# - figure: paired with its nearest caption box and treated as a
#   paragraph for prompting (OCR text from the snippet + caption).
# - auxiliary / discard: silently dropped.
_KIND_TO_ELEMENT_TYPE: dict[str, ElementType] = {
    BoxKind.paragraph.value: "paragraph",
    BoxKind.heading.value: "heading",
    BoxKind.list_item.value: "list_item",
    BoxKind.table.value: "table",
    # Captions read like sentences — generator treats them as paragraph.
    BoxKind.caption.value: "paragraph",
    # Formulas: rare and the generator returns no template for them, but
    # surfacing as paragraph lets a future template handle them.
    BoxKind.formula.value: "paragraph",
    # Figures: caption-paired + OCR text from the figure snippet (axis
    # labels, legends, in-figure titles MinerU's VLM extracted).
    BoxKind.figure.value: "paragraph",
}


def _nearest_caption_id(
    fig_box_id: str,
    fig_page: int,
    fig_bbox: tuple[float, float, float, float],
    caption_ids_on_page: list[tuple[str, tuple[float, float, float, float]]],
) -> str | None:
    """Pick the caption box closest in vertical centre to *fig_bbox*.

    Captions in scientific PDFs sit directly above or below their
    figure, so vertical-distance is a much stronger signal than
    horizontal alignment. Returns None when no caption exists on the
    page.
    """
    if not caption_ids_on_page:
        return None
    fig_yc = (fig_bbox[1] + fig_bbox[3]) / 2.0
    best_id: str | None = None
    best_dist = float("inf")
    for cap_id, cap_bbox in caption_ids_on_page:
        cap_yc = (cap_bbox[1] + cap_bbox[3]) / 2.0
        d = abs(cap_yc - fig_yc)
        if d < best_dist:
            best_dist = d
            best_id = cap_id
    return best_id


@dataclass(frozen=True)
class MineruElementsLoader:
    """Read mineru.json + segments.json for *slug* under *data_root*.

    Implements the ``ElementsLoader`` Protocol from
    ``goldens.creation.elements.adapter``.

    Optional scope filters:
      - ``only_box_id`` — yield only that one element.
      - ``only_page`` — yield only elements on that page.
    Both are applied AFTER kind filtering, so the count matches what
    the synthesis loop will actually iterate.
    """

    data_root: Path
    slug: str
    only_box_id: str | None = None
    only_page: int | None = None

    def elements(self) -> list[DocumentElement]:
        seg = read_segments(self.data_root, self.slug)
        m = read_mineru(self.data_root, self.slug)
        if seg is None or m is None:
            return []

        kind_by_id = {b.box_id: b.kind.value for b in seg.boxes}
        page_by_id = {b.box_id: b.page for b in seg.boxes}
        bbox_by_id: dict[str, Bbox] = {b.box_id: cast("Bbox", tuple(b.bbox)) for b in seg.boxes}
        # Snippet preference: html_snippet_raw if present (pre-LaTeX-conversion
        # form, easier to extract clean text from); fall back to html_snippet.
        snippet_by_id = {
            e["box_id"]: (e.get("html_snippet_raw") or e.get("html_snippet") or "")
            for e in m.get("elements", [])
        }

        # Index captions by page for the figure-pairing step below.
        captions_by_page: dict[int, list[tuple[str, Bbox]]] = {}
        for b in seg.boxes:
            if b.kind == BoxKind.caption:
                captions_by_page.setdefault(b.page, []).append(
                    (b.box_id, cast("Bbox", tuple(b.bbox)))
                )

        out: list[DocumentElement] = []
        for box_id, kind in kind_by_id.items():
            element_type = _KIND_TO_ELEMENT_TYPE.get(kind)
            if element_type is None:
                continue
            html = snippet_by_id.get(box_id, "")
            # Tables need newline-separated rows so decompose_to_sub_units
            # can split them; everything else collapses to a single line.
            text = _table_html_to_text(html) if element_type == "table" else _strip_html(html)

            # Figures: pair with nearest caption on the same page so
            # prompts get both the OCR-extracted in-figure text and the
            # caption sentence. Skip figures with neither.
            if kind == BoxKind.figure.value:
                page = page_by_id.get(box_id, 1)
                fig_bbox = bbox_by_id.get(box_id)
                cap_id = (
                    _nearest_caption_id(box_id, page, fig_bbox, captions_by_page.get(page, []))
                    if fig_bbox is not None
                    else None
                )
                cap_text = _strip_html(snippet_by_id.get(cap_id, "")) if cap_id else ""
                ocr_text = text  # already stripped above
                parts: list[str] = []
                if cap_text:
                    parts.append(f"Bildunterschrift: {cap_text}")
                if ocr_text:
                    parts.append(f"Im Bild erkannter Text: {ocr_text}")
                if not parts:
                    # No caption + no OCR → can't ask anything useful.
                    continue
                text = "\n\n".join(parts)
            elif not text:
                continue

            extra: dict = {}
            if element_type == "table":
                # synthetic.py uses table_full_content for table-row prompting.
                extra["table_full_content"] = html
            page = page_by_id.get(box_id, 1)
            out.append(
                DocumentElement(
                    element_id=box_id,
                    page_number=page,
                    element_type=element_type,
                    content=text,
                    **extra,
                )
            )

        # Stable order by (page, box_id) so streaming progress is monotonic.
        out.sort(key=lambda e: (e.page_number, e.element_id))
        if self.only_box_id is not None:
            out = [e for e in out if e.element_id == self.only_box_id]
        if self.only_page is not None:
            out = [e for e in out if e.page_number == self.only_page]
        return out
