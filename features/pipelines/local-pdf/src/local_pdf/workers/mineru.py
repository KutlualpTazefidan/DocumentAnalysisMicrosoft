"""MinerU 2.5 VLM extraction worker — in-process Python API with batch lifecycle.

`MineruWorker` is a context-managed model worker.

- `__enter__`: load the MinerU 2.5 VLM model (Qwen2-VL fine-tune) via
  ModelSingleton and the `transformers` backend.  Emits `ModelLoadingEvent`
  then `ModelLoadedEvent` with real `load_seconds` and `vram_actual_mb`.
  If `extract_fn`, `parse_page_fn`, or `parse_doc_fn` is injected (test path)
  the real model is skipped entirely.
- `__exit__`: call shutdown_cached_models(), gc.collect(), torch.cuda.empty_cache().
- `run(pdf, boxes)`: parse the full doc ONCE (cached), match each user bbox
  to parsed elements via IoU / center-containment, yield one
  `WorkProgressEvent` per box, one `WorkCompleteEvent` at the end.
- `extract_region(pdf, box)`: single-bbox path — same match logic, no stream.

Injection points (tests):
  `extract_fn`: overrides the entire per-box extraction path.
  `parse_doc_fn`: overrides the per-doc parse step (preferred new path);
    signature (pdf_path: Path) -> dict[int, PageData].
  `parse_page_fn`: legacy per-page injection; still honoured for back-compat.
    If only `parse_page_fn` is injected, pages are parsed on demand (slower,
    but existing tests don't care about speed).

No subprocess.  No sidecar.  No HTTP.  Pure in-process Python.
"""

from __future__ import annotations

import gc
import html as html_lib
import os
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from local_pdf.api.schemas import BoxKind, SegmentBox
from local_pdf.workers.base import (
    EtaCalculator,
    ModelLoadedEvent,
    ModelLoadingEvent,
    ModelUnloadedEvent,
    ModelUnloadingEvent,
    WorkCompleteEvent,
    WorkerEvent,
    WorkProgressEvent,
    _import_torch,
    _vram_used_mb,
    now_ms,
)

# Default VLM model: ~1.2B-parameter Qwen2-VL fine-tune for document parsing.
# ~3 GB VRAM in fp16.  First run downloads from HuggingFace (~3 GB cache).
_DEFAULT_VLM_MODEL = "opendatalab/MinerU2.5-Pro-2604-1.2B"


@dataclass(frozen=True)
class ParsedElement:
    """One element returned by a page parse."""

    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF pts
    html: str
    text: str = ""
    # MinerU block type ("text", "title", "table", "image", "list", ...).
    # Used to apply kind-vs-block-type compatibility weighting in
    # _assign_elements_to_boxes so a user-bbox with kind=table doesn't
    # claim a text-type element from a kind=heading user-bbox sitting next
    # to it (e.g. a table caption).  Empty string when unknown.
    block_type: str = ""


@dataclass(frozen=True)
class PageData:
    """Per-page parse result: page dimensions plus all parsed elements."""

    page_size: tuple[float, float]  # (width_pt, height_pt)
    elements: list[ParsedElement]


@dataclass(frozen=True)
class MinerUResult:
    box_id: str
    html: str


ExtractFn = Callable[[Path, SegmentBox], MinerUResult]
ParsePageFn = Callable[[Path, int], list[ParsedElement]]
# ParseDocFn may return dict[int, PageData] (preferred) or dict[int, list[ParsedElement]]
# (legacy test format). _get_doc_pages normalises both.
ParseDocFn = Callable[[Path], dict]

# Visual block types that require merge_visual_blocks_to_markdown
_VISUAL_BLOCK_TYPES = {"image", "table", "chart", "code"}

# Text-like user kinds (styling comes from plain text extracted from MinerU)
_TEXT_LIKE_KINDS = {
    BoxKind.heading,
    BoxKind.paragraph,
    BoxKind.caption,
    BoxKind.auxiliary,
    BoxKind.list_item,
    BoxKind.formula,
}

# Visual user kinds (MinerU HTML used as-is)
_VISUAL_KINDS = {BoxKind.table, BoxKind.figure}

# Auxiliary zone thresholds as fraction of page height
_AUXILIARY_HEADER_THRESHOLD = 0.08
_AUXILIARY_FOOTER_THRESHOLD = 0.92


# ── IoU + reading-order helpers ───────────────────────────────────────────────


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Intersection over union of two (x0, y0, x1, y1) boxes."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter == 0.0:
        return 0.0
    area_a = max(0.0, ax1 - ax0) * max(0.0, ay1 - ay0)
    area_b = max(0.0, bx1 - bx0) * max(0.0, by1 - by0)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _center_in(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    cx, cy = point
    x0, y0, x1, y1 = box
    return x0 <= cx <= x1 and y0 <= cy <= y1


def _match_box_to_elements(
    user_bbox: tuple[float, float, float, float],
    page_elements: list[ParsedElement],
) -> list[ParsedElement]:
    """Return elements overlapping `user_bbox` by IoU > 0.3 or center containment.

    Returns [] when nothing qualifies (no best-effort fallback).
    Results are sorted by (top, left) for reading order before return.
    """
    if not page_elements:
        return []

    matches: list[ParsedElement] = []
    for el in page_elements:
        score = _iou(user_bbox, el.bbox)
        cx = (el.bbox[0] + el.bbox[2]) / 2.0
        cy = (el.bbox[1] + el.bbox[3]) / 2.0
        if score > 0.3 or _center_in((cx, cy), user_bbox):
            matches.append(el)

    # Reading order: top then left
    matches.sort(key=lambda el: (el.bbox[1], el.bbox[0]))
    return matches


def _kind_compat(user_kind: BoxKind, block_type: str) -> float:
    """Compatibility multiplier between a user-bbox kind and a MinerU block type.

    A user-bbox shouldn't claim a MinerU element whose block type is
    semantically inappropriate.  E.g. a kind=table user-bbox enclosing a
    text-type block (table caption) should NOT outscore a kind=heading
    user-bbox that's meant to capture that caption.  The multiplier scales
    the geometric score (IoU + center-in) before best-match selection.

    Returns:
      - 0.0 hard reject — element won't be assigned to this box even if
        it's the only spatial match.  Used for clear semantic mismatches
        (e.g. table user-bbox vs text MinerU block).
      - 1.0 neutral — kind/type pair is compatible; geometric score wins.
      - >1.0 boost — strong semantic match (e.g. heading user-bbox vs
        title MinerU block).
    """
    # Unknown block type → neutral. The real parser always sets block_type;
    # this fallback keeps test fixtures and legacy callers working.
    if not block_type:
        return 1.0

    visual_blocks = _VISUAL_BLOCK_TYPES  # {"image", "table", "chart", "code"}

    if user_kind == BoxKind.table:
        # Table user-bbox only matches MinerU table/chart blocks.
        return 1.5 if block_type in {"table", "chart"} else 0.0
    if user_kind == BoxKind.figure:
        # Figure user-bbox only matches MinerU image-type blocks.
        return 1.5 if block_type in {"image"} else 0.0
    if user_kind == BoxKind.formula:
        # Formula user-bbox prefers equation/code; reject visual blocks.
        if block_type in {"equation", "interline_equation", "code"}:
            return 1.5
        if block_type in visual_blocks:
            return 0.0
        return 1.0  # fall through to text-ish match
    # Text-like user kinds (heading/paragraph/caption/list_item/auxiliary):
    # give a boost on title-type for headings, otherwise neutral.
    # Hard reject visual block types so a heading user-bbox doesn't grab
    # a table block by accident.
    if user_kind in {
        BoxKind.heading,
        BoxKind.paragraph,
        BoxKind.caption,
        BoxKind.list_item,
        BoxKind.auxiliary,
    }:
        if block_type in visual_blocks:
            return 0.0
        if user_kind == BoxKind.heading and block_type == "title":
            return 1.5
        if user_kind == BoxKind.list_item and block_type == "list":
            return 1.5
        return 1.0
    return 1.0


def _assign_elements_to_boxes(
    boxes_with_kinds: list[tuple[str, tuple[float, float, float, float], BoxKind]],
    page_elements: list[ParsedElement],
) -> dict[str, list[ParsedElement]]:
    """Assign each MinerU element to at most ONE user box.

    Geometric score per (element, box) pair = IoU; center-in counts as 0.31
    (just above the 0.3 threshold) so a contained-but-low-IoU element still
    claims its box.  Then geometric score is multiplied by a kind-vs-block-type
    compatibility factor (see ``_kind_compat``) — a 0.0 multiplier hard-rejects
    the pair.  Element goes to the highest-final-score box; elements with no
    qualifying box are dropped (no fallback double-counting).

    Returns dict mapping box_id -> list of matched ParsedElement, sorted by
    reading order (top, left).
    """
    min_score = 0.3
    assignments: dict[str, list[ParsedElement]] = {bid: [] for bid, _, _ in boxes_with_kinds}
    for el in page_elements:
        cx = (el.bbox[0] + el.bbox[2]) / 2.0
        cy = (el.bbox[1] + el.bbox[3]) / 2.0
        best_id: str | None = None
        best_score = 0.0
        for bid, bbox, kind in boxes_with_kinds:
            geom = _iou(bbox, el.bbox)
            if _center_in((cx, cy), bbox):
                geom = max(geom, 0.31)
            score = geom * _kind_compat(kind, el.block_type)
            if score > best_score:
                best_score = score
                best_id = bid
        if best_id and best_score >= min_score:
            assignments[best_id].append(el)
    for bid in assignments:
        assignments[bid].sort(key=lambda el: (el.bbox[1], el.bbox[0]))
    return assignments


# ── Text helpers ──────────────────────────────────────────────────────────────


def _html_to_text(html: str) -> str:
    """Strip HTML tags and decode entities, returning plain text."""
    stripped = re.sub(r"<[^>]+>", "", html)
    return html_lib.unescape(stripped)


# ── Caption rescue helpers ────────────────────────────────────────────────────

_CAPTION_RE = re.compile(r"<caption[^>]*>(.*?)</caption>", re.DOTALL | re.IGNORECASE)
_LEADING_TEXT_RE = re.compile(r"^(.*?)(?=<(?:table|figure)\b)", re.DOTALL | re.IGNORECASE)


def _try_extract_caption(html: str) -> tuple[str, str] | None:
    """Return (caption_text, html_without_caption) if a caption can be extracted.

    Tries <caption> tag first, then leading text before <table>/<figure>.
    Returns None if no caption text is found.
    """
    if not html:
        return None
    m = _CAPTION_RE.search(html)
    if m:
        cap = m.group(1).strip()
        if cap:
            return cap, _CAPTION_RE.sub("", html, count=1)
    m = _LEADING_TEXT_RE.match(html)
    if m:
        leading = m.group(1).strip()
        # Only treat leading text as caption if it's non-trivial and not just
        # whitespace/html-noise.
        clean = re.sub(r"<[^>]+>", "", leading).strip()
        if len(clean) >= 5:  # avoid grabbing single-char artifacts
            return clean, html[m.end(1) :]  # strip leading text from html
    return None


def _caption_adjacency_score(
    empty_pts: tuple[float, float, float, float],
    visual_pts: tuple[float, float, float, float],
    max_gap: float = 50.0,
) -> float:
    """Score how likely `empty_pts` is the caption for `visual_pts`.

    Captions sit in the same horizontal column as their table/figure, with
    little vertical gap (above or below; sometimes overlapping). Returns
    0.0 if the geometry rules out a caption relationship; higher = more
    likely. ``max_gap`` is in PDF points; gaps beyond it score 0.
    """
    # Require >= 30% horizontal overlap relative to the empty box's width
    # (same-column heuristic).
    x_overlap = max(
        0.0,
        min(empty_pts[2], visual_pts[2]) - max(empty_pts[0], visual_pts[0]),
    )
    empty_width = max(1.0, empty_pts[2] - empty_pts[0])
    if x_overlap / empty_width < 0.3:
        return 0.0

    # Vertical gap: positive when separated, 0 when overlapping.
    if empty_pts[3] <= visual_pts[1]:
        gap = visual_pts[1] - empty_pts[3]  # empty entirely above visual
    elif empty_pts[1] >= visual_pts[3]:
        gap = empty_pts[1] - visual_pts[3]  # empty entirely below visual
    else:
        gap = 0.0  # overlap → treat as adjacent

    if gap > max_gap:
        return 0.0
    return 1.0 / (1.0 + gap)


def _rescue_captions_from_visual_boxes(
    assignments: dict[str, list[ParsedElement]],
    user_boxes: list[SegmentBox],
    raster_dpi: int,
) -> dict[str, list[ParsedElement]]:
    """Post-process page assignments: route captions hidden inside table/figure
    blocks to nearby empty heading/caption/paragraph user-boxes.

    Selection is by spatial adjacency (same column + small vertical gap),
    not containment — caption-above-table is the canonical layout.
    """
    by_id = {b.box_id: b for b in user_boxes}
    text_kinds = {BoxKind.heading, BoxKind.caption, BoxKind.paragraph}
    visual_kinds = {BoxKind.table, BoxKind.figure}

    new_assignments = {bid: list(els) for bid, els in assignments.items()}

    for empty_id, els in assignments.items():
        if els:
            continue
        empty_box = by_id.get(empty_id)
        if not empty_box or empty_box.kind not in text_kinds:
            continue
        empty_pts = _user_bbox_to_pts(empty_box.bbox, raster_dpi)

        # Score every winning visual user-bbox for adjacency
        candidates: list[tuple[float, str]] = []
        for win_id, win_els in assignments.items():
            if win_id == empty_id or not win_els:
                continue
            win_box = by_id.get(win_id)
            if not win_box or win_box.kind not in visual_kinds:
                continue
            win_pts = _user_bbox_to_pts(win_box.bbox, raster_dpi)
            score = _caption_adjacency_score(empty_pts, win_pts)
            if score > 0:
                candidates.append((score, win_id))

        if not candidates:
            continue
        candidates.sort(reverse=True)  # highest score first
        win_id = candidates[0][1]
        win_els = new_assignments[win_id]

        # Try rescue against the best candidate's elements.
        # We keep the caption WHERE MinerU put it (inside the table block) so
        # the table renders naturally with its caption.  The empty user-bbox
        # gets a synthetic copy of the caption text — which `_build_one_box_html`
        # detects via block_type="caption_rescue" and renders in a muted,
        # smaller style (the heading slot becomes a reference, not a duplicate
        # primary heading).
        for el in win_els:
            rescue = _try_extract_caption(el.html)
            if rescue is None:
                continue
            cap_text, _cleaned = rescue  # ignore the stripped variant
            synthetic = ParsedElement(
                bbox=empty_pts,
                html=f"<p>{cap_text}</p>",
                text=cap_text,
                block_type="caption_rescue",
            )
            new_assignments[empty_id].append(synthetic)
            break

    return new_assignments


# ── Block → HTML/markdown conversion ─────────────────────────────────────────

# Fraction of page height that counts as header/footer zone.
_HEADER_FOOTER_FRACTION = 0.08


def _is_page_number(text: str) -> bool:
    """Return True if *text* is a bare page number (digits only, short)."""
    stripped = text.strip()
    return stripped.isdigit() and len(stripped) <= 5


def _walk_block_for_text(block: object) -> str:
    """Best-effort recursive walk of a block dict to collect any text.

    Used as a fallback when MinerU's own ``merge_para_with_text`` raises
    (e.g. VLM blocks that lack the expected ``lines`` key).  Looks at common
    text-bearing fields (``content``, ``text``) and recurses into nested
    structures (``lines``/``spans``/``blocks``) when present.
    """
    if not isinstance(block, dict):
        return ""
    pieces: list[str] = []
    for key in ("content", "text"):
        v = block.get(key)
        if isinstance(v, str) and v.strip():
            pieces.append(v)
    for key in ("lines", "spans", "blocks"):
        children = block.get(key)
        if isinstance(children, list):
            for child in children:
                txt = _walk_block_for_text(child) if isinstance(child, dict) else ""
                if txt:
                    pieces.append(txt)
    return " ".join(pieces).strip()


def _safe_merge_para_text(block: dict) -> str:
    """Call MinerU's ``merge_para_with_text``; fall back to ``_walk_block_for_text``
    if the block schema doesn't match what MinerU expects (e.g. missing ``lines``).
    """
    # Prefer the VLM-backend helper since we run the VLM backend, but fall
    # back to the pipeline helper if VLM helpers aren't available.
    merge = None
    try:
        from mineru.backend.vlm.vlm_middle_json_mkcontent import (
            merge_para_with_text as _vlm_merge,
        )

        merge = _vlm_merge
    except ImportError:
        try:
            from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
                merge_para_with_text as _pipe_merge,
            )

            merge = _pipe_merge
        except ImportError:
            return _walk_block_for_text(block)
    try:
        return (merge(block) or "") or _walk_block_for_text(block)
    except (KeyError, TypeError, AttributeError):
        return _walk_block_for_text(block)


def _safe_merge_visual(block: dict) -> str:
    """Call MinerU's ``merge_visual_blocks_to_markdown`` defensively."""
    merge = None
    try:
        from mineru.backend.vlm.vlm_middle_json_mkcontent import (
            merge_visual_blocks_to_markdown as _vlm_merge,
        )

        merge = _vlm_merge
    except ImportError:
        try:
            from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
                merge_visual_blocks_to_markdown as _pipe_merge,
            )

            merge = _pipe_merge
        except ImportError:
            return _walk_block_for_text(block)
    try:
        return (merge(block) or "") or _walk_block_for_text(block)
    except (KeyError, TypeError, AttributeError):
        return _walk_block_for_text(block)


def _block_to_content(block: dict) -> str:
    """Convert a single MinerU para_block to a content string.

    Uses ``_safe_merge_visual`` for visual/code blocks and ``_safe_merge_para_text``
    for all text-based blocks.  Returns "" when nothing extractable.
    """
    block_type = block.get("type", "")
    if block_type in _VISUAL_BLOCK_TYPES:
        return _safe_merge_visual(block)
    return _safe_merge_para_text(block)


def _block_to_html(
    block: dict,
    page_size: tuple[float, float] | None = None,
) -> str:
    """Convert a MinerU para_block to type-aware HTML.

    Wraps content in semantic elements based on block type.  Detects
    header/footer zones using bbox position relative to page_size and
    wraps them in <header>/<footer>.  Pure-digit short blocks in those
    zones become <span class="page-number">.

    Returns "" when no content can be extracted so callers can skip.

    Args:
        block: A MinerU para_block dict.
        page_size: (width_pts, height_pts) of the page, used for
            header/footer detection.  Pass None to skip zone detection.
    """
    block_type = block.get("type", "")
    raw_bbox = block.get("bbox")

    # Determine zone (header / footer / body) from bbox position.
    in_header = False
    in_footer = False
    if page_size is not None and raw_bbox is not None:
        try:
            _x0, y0, _x1, y1 = (float(v) for v in raw_bbox[:4])
            page_h = page_size[1]
            if page_h > 0:
                threshold = page_h * _HEADER_FOOTER_FRACTION
                if y1 <= threshold:
                    in_header = True
                elif y0 >= page_h - threshold:
                    in_footer = True
        except (TypeError, ValueError):
            pass

    if block_type in _VISUAL_BLOCK_TYPES:
        raw = _safe_merge_visual(block)
        if not raw:
            return ""
        if block_type == "image":
            inner = f"<figure>{raw}</figure>"
        elif block_type in ("table",):
            inner = f'<div class="extracted-table">{raw}</div>'
        else:
            inner = f"<pre><code>{raw}</code></pre>"
    else:
        raw = _safe_merge_para_text(block)
        if not raw:
            return ""
        if in_header or in_footer:
            if _is_page_number(raw):
                return f'<span class="page-number">{raw.strip()}</span>'
            zone = "page-header" if in_header else "page-footer"
            tag = "header" if in_header else "footer"
            return f'<{tag} class="{zone}">{raw}</{tag}>'

        if block_type == "title":
            lvl = block.get("level", 2)
            tag = "h1" if lvl == 1 else "h2"
            inner = f"<{tag}>{raw}</{tag}>"
        elif block_type == "text":
            inner = f"<p>{raw}</p>"
        elif block_type == "list":
            inner = f'<div class="md-list">{raw}</div>'
        elif block_type in ("index",):
            inner = f'<div class="toc">{raw}</div>'
        elif block_type in ("code", "equation", "interline_equation"):
            inner = f"<pre><code>{raw}</code></pre>"
        else:
            # abstract, unknown, etc.
            inner = f"<p>{raw}</p>"

    return inner


# ── Per-box HTML builder (user-kind driven) ───────────────────────────────────


def _build_one_box_html(
    box: SegmentBox,
    matched: list[ParsedElement],
    page_size: tuple[float, float],
    *,
    raster_dpi: int = 288,
    promote_to_h1: bool = False,
) -> str:
    """Build kind-driven HTML for a single user box.

    Styling is determined entirely by ``box.kind`` (user annotation), NOT by
    MinerU's block type.  MinerU matched elements are used only as a text/HTML
    source.

    - Text-like kinds (heading, paragraph, caption, auxiliary, list_item,
      formula): extract plain text from matched elements, join with space.
    - Visual kinds (table, figure): use matched MinerU element HTML as-is.
    - No match: emit empty marker.

    ``promote_to_h1`` applies only to heading boxes; when True, wraps in
    ``<h1>`` instead of ``<h2>``.

    ``matched`` is the pre-resolved list of ParsedElement objects for this box,
    produced by ``_assign_elements_to_boxes`` at the page level.

    ``raster_dpi`` is used only for auxiliary-zone detection (converting the
    box's pixel y-coordinate to a page-height fraction).

    Returns the complete HTML fragment (tag + data-source-box attribute).
    """
    kind = box.kind
    box_id = box.box_id

    empty_marker = "[Keine Extraktion fur diesen Bereich]"

    # ── visual kinds: use MinerU HTML as-is ───────────────────────────────────
    if kind in _VISUAL_KINDS:
        if matched:
            # Use the first matched element's html for visual content
            mineru_html = matched[0].html
            if mineru_html:
                if kind == BoxKind.table:
                    inner = f'<div class="extracted-table">{mineru_html}</div>'
                else:  # figure
                    inner = f"<figure>{mineru_html}</figure>"
                return f'<div data-source-box="{box_id}">{inner}</div>'
        # No match or empty html: empty marker
        if kind == BoxKind.table:
            return (
                f'<div class="extracted-table" data-source-box="{box_id}"'
                f' class="empty">{empty_marker}</div>'
            )
        return f'<figure data-source-box="{box_id}" class="empty">{empty_marker}</figure>'

    # ── text-like kinds: extract plain text ───────────────────────────────────
    if kind in _TEXT_LIKE_KINDS:
        text = " ".join(_html_to_text(el.html) for el in matched).strip() if matched else ""

        # Caption-rescue marker: the only matched element is a synthetic
        # ParsedElement carrying the caption text from an adjacent table/figure
        # block (which still renders the caption itself).  Render the user's
        # bbox as a visually muted reference so the caption isn't shouted twice.
        if matched and all(el.block_type == "caption_rescue" for el in matched):
            return (
                f"<{'figcaption' if kind == BoxKind.caption else 'p'} "
                f'data-source-box="{box_id}" class="caption-ref">{text}</'
                f"{'figcaption' if kind == BoxKind.caption else 'p'}>"
            )

        if not text:
            # Empty marker per kind
            if kind == BoxKind.heading:
                tag = "h1" if promote_to_h1 else "h2"
                return f'<{tag} data-source-box="{box_id}" class="empty">{empty_marker}</{tag}>'
            if kind == BoxKind.paragraph:
                return f'<p data-source-box="{box_id}" class="empty">{empty_marker}</p>'
            if kind == BoxKind.list_item:
                return f'<li data-source-box="{box_id}" class="empty">{empty_marker}</li>'
            if kind == BoxKind.caption:
                return (
                    f'<figcaption data-source-box="{box_id}" class="empty">'
                    f"{empty_marker}</figcaption>"
                )
            if kind == BoxKind.formula:
                return (
                    f'<pre data-source-box="{box_id}" class="empty">'
                    f"<code>{empty_marker}</code></pre>"
                )
            # auxiliary
            return (
                f'<aside class="auxiliary" data-source-box="{box_id}" class="empty">'
                f"{empty_marker}</aside>"
            )

        if kind == BoxKind.heading:
            tag = "h1" if promote_to_h1 else "h2"
            return f'<{tag} data-source-box="{box_id}">{text}</{tag}>'
        if kind == BoxKind.paragraph:
            return f'<p data-source-box="{box_id}">{text}</p>'
        if kind == BoxKind.list_item:
            return f'<li data-source-box="{box_id}">{text}</li>'
        if kind == BoxKind.caption:
            return f'<figcaption data-source-box="{box_id}">{text}</figcaption>'
        if kind == BoxKind.formula:
            return f'<pre data-source-box="{box_id}"><code>{text}</code></pre>'
        # auxiliary: zone detection
        # box.bbox is (x0, y0, x1, y1) in pixels; convert y_top to pt fraction
        y_top_px = box.bbox[1]
        page_h_pt = page_size[1]
        if page_h_pt > 0:
            y_top_pt = y_top_px * 72.0 / raster_dpi
            frac = y_top_pt / page_h_pt
            if frac < _AUXILIARY_HEADER_THRESHOLD:
                return f'<header class="page-header" data-source-box="{box_id}">{text}</header>'
            if frac > _AUXILIARY_FOOTER_THRESHOLD:
                return f'<footer class="page-footer" data-source-box="{box_id}">{text}</footer>'
        return f'<aside class="auxiliary" data-source-box="{box_id}">{text}</aside>'

    return ""


# ── PDF page slicer ───────────────────────────────────────────────────────────


def _slice_pdf_to_pages(pdf_bytes: bytes, page_nums: list[int]) -> bytes:
    """Return PDF bytes containing only the given 1-indexed pages, in order.

    Used when the worker only needs a subset of pages — passing a sliced PDF
    to MinerU's VLM avoids parsing the entire document.
    """
    import io

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for p in sorted(set(page_nums)):
        writer.add_page(reader.pages[p - 1])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ── Real MinerU doc parse (production path) ──────────────────────────────────


def _make_real_parse_doc_fn(
    predictor: object,
    image_writer_dir: Path | None = None,
) -> Callable[[Path, list[int] | None], dict[int, PageData]]:
    """Return a parse function that uses the loaded MinerU VLM predictor.

    The returned function signature is:
        (pdf_path: Path, page_subset: list[int] | None = None) -> dict[int, PageData]

    When `page_subset` is None, all pages are parsed (previous behaviour).
    When `page_subset` is a non-empty list of 1-indexed page numbers, the PDF
    is sliced to those pages before calling doc_analyze, and the resulting
    pdf_info indices are remapped back to the original page numbers.

    MinerU's `doc_analyze` API processes a whole PDF via a windowed VLM
    inference loop.  Both the pipeline and VLM backends produce the same
    `pdf_info -> para_blocks / discarded_blocks / page_size` schema via
    `init_middle_json()`, so all downstream block parsing is unchanged.

    If `image_writer_dir` is given, MinerU's figure / table cropouts are
    written to that directory (created on demand). With `None` (default),
    cropouts are discarded.
    """
    try:
        from mineru.backend.vlm.vlm_analyze import doc_analyze
    except ImportError as exc:
        raise ImportError("mineru[vlm] missing — install mineru[core] or mineru[vlm].") from exc

    if image_writer_dir is not None:
        from mineru.data.data_reader_writer import FileBasedDataWriter

    def _parse_doc(pdf_path: Path, page_subset: list[int] | None = None) -> dict[int, PageData]:
        """Parse a PDF (or a sliced subset of its pages) using MinerU VLM backend.

        When page_subset is provided, the PDF is sliced to those pages before
        passing to doc_analyze, reducing VLM work to only the needed pages.
        The returned dict is always keyed by original 1-indexed page numbers.
        """
        pdf_bytes = pdf_path.read_bytes()

        # Slice to requested pages when a subset is specified.
        # sorted_subset[i] is the original page number for sliced page i+1.
        if page_subset:
            sorted_subset = sorted(set(page_subset))
            pdf_bytes = _slice_pdf_to_pages(pdf_bytes, sorted_subset)
        else:
            sorted_subset = None

        # Pick the image writer: file-based when caller wants cropouts saved.
        if image_writer_dir is not None:
            image_writer_dir.mkdir(parents=True, exist_ok=True)
            image_writer = FileBasedDataWriter(str(image_writer_dir))
        else:

            class _NullWriter:
                def write(self, *_a: object, **_kw: object) -> None:
                    pass

            image_writer = _NullWriter()

        middle_json, _results = doc_analyze(
            pdf_bytes,
            image_writer,
            predictor=predictor,
            backend="transformers",
        )

        all_page_infos = middle_json.get("pdf_info", []) if middle_json else []

        pages: dict[int, PageData] = {}
        for page_idx, page_info in enumerate(all_page_infos):
            # When a page_subset was used, sliced page i+1 maps back to
            # sorted_subset[i] in the original document.  Without a subset,
            # page_idx + 1 is the canonical 1-indexed page number.
            page_number = sorted_subset[page_idx] if sorted_subset is not None else page_idx + 1
            raw_page_size = page_info.get("page_size")
            try:
                page_size: tuple[float, float] = (
                    (
                        float(raw_page_size[0]),
                        float(raw_page_size[1]),
                    )
                    if raw_page_size and len(raw_page_size) >= 2
                    else (612.0, 792.0)
                )
            except (TypeError, ValueError, IndexError):
                page_size = (612.0, 792.0)

            elements: list[ParsedElement] = []
            # MinerU segregates header / footer / page-number content into
            # `discarded_blocks` (separate from `para_blocks`).  Include both
            # pools so user "auxiliary" bboxes can match their content.
            for block in (page_info.get("para_blocks") or []) + (
                page_info.get("discarded_blocks") or []
            ):
                raw_bbox = block.get("bbox", None)
                if raw_bbox is None:
                    continue
                try:
                    x0, y0, x1, y1 = (float(v) for v in raw_bbox[:4])
                except (TypeError, ValueError):
                    continue

                block_type = block.get("type", "")
                html_content = _block_to_html(block, page_size=page_size)
                if not html_content:
                    continue

                # Extract plain text for text-like blocks (defensive against
                # blocks without the expected 'lines' key — see _safe_merge_para_text).
                if block_type in _VISUAL_BLOCK_TYPES:
                    text_content = ""
                else:
                    text_content = _safe_merge_para_text(block)

                elements.append(
                    ParsedElement(
                        bbox=(x0, y0, x1, y1),
                        html=html_content,
                        text=text_content,
                        block_type=block_type,
                    )
                )
            pages[page_number] = PageData(page_size=page_size, elements=elements)

        return pages

    return _parse_doc


def _make_real_parse_page_fn(predictor: object) -> ParsePageFn:
    """Return a ParsePageFn wrapping _make_real_parse_doc_fn for single-page calls.

    This is a compatibility shim: it re-parses the full doc on every call.
    Production code should use _get_doc_pages / ParseDocFn instead.
    """
    parse_doc = _make_real_parse_doc_fn(predictor)

    def _parse_page(pdf_path: Path, page_number: int) -> list[ParsedElement]:
        pages = parse_doc(pdf_path, None)
        page_data = pages.get(page_number)
        return page_data.elements if page_data is not None else []

    return _parse_page


# ── Coordinate-space conversion ───────────────────────────────────────────────


def _user_bbox_to_pts(
    bbox: tuple[float, float, float, float], raster_dpi: int
) -> tuple[float, float, float, float]:
    """Convert a user bbox from pixel space (at raster_dpi) to PDF point space.

    Segment boxes from the YOLO worker are stored in pixel coordinates at
    raster_dpi (default 144).  MinerU's parsed-element bboxes are in PDF
    points (1 pt = 1/72 inch).  The conversion is: pts = px * 72 / raster_dpi.

    Diagnostic confirmation (gnb-b-148-2001-rev-1, page 8, raster_dpi=144):
      sample user px bbox [100, 200, 500, 300] → pts [50, 100, 250, 150]
      MinerU block bbox     [50, 100, 250, 150]  (PDF pts from para_blocks)
    Without this conversion IoU is always ~0 because the coordinate spaces
    differ by a factor of 144/72 = 2 in each dimension.
    """
    k = 72.0 / raster_dpi
    return (bbox[0] * k, bbox[1] * k, bbox[2] * k, bbox[3] * k)


# ── Worker ────────────────────────────────────────────────────────────────────


class MineruWorker:
    """Context-managed MinerU 2.5 VLM extraction worker.

    Production use — real model loaded in __enter__, unloaded in __exit__ /
    unload().  Tests inject `extract_fn`, `parse_doc_fn`, or `parse_page_fn`
    to avoid loading any real weights.
    """

    name: str = "MinerU 2.5 VLM"
    estimated_vram_mb: int = 3500

    def __init__(
        self,
        *,
        extract_fn: ExtractFn | None = None,
        parse_doc_fn: ParseDocFn | None = None,
        parse_page_fn: ParsePageFn | None = None,
        raster_dpi: int = 288,
        image_writer_dir: Path | None = None,
    ) -> None:
        self._extract_fn = extract_fn
        self._parse_doc_fn = parse_doc_fn
        self._parse_page_fn = parse_page_fn
        self._raster_dpi = raster_dpi
        # When set, MinerU figure/table cropouts are written here (per-doc).
        self._image_writer_dir = image_writer_dir
        self._predictor: object = None
        self._loaded_vram_mb = 0
        self._load_seconds = 0.0
        self._unloaded = False
        self.results: list[MinerUResult] = []
        # Per-worker doc cache: avoids re-parsing the same PDF across multiple
        # calls to run() / extract_region() within one worker lifetime.
        # Cache key: (pdf_path, frozenset of requested pages | None for full doc).
        # A partial-page run and a full-doc run are different cache entries so
        # "Diese Seite extrahieren" never poisons the full-doc cache.
        self._doc_cache: dict[tuple[Path, frozenset[int] | None], dict[int, PageData]] = {}

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> Self:
        if (
            self._extract_fn is not None
            or self._parse_doc_fn is not None
            or self._parse_page_fn is not None
        ):
            # Injected test path — skip real model load.
            return self

        before = _vram_used_mb()
        t0 = time.monotonic()
        try:
            from mineru.backend.vlm.vlm_analyze import ModelSingleton

            model_path = os.environ.get("LOCAL_PDF_MINERU_MODEL_PATH") or None
            self._predictor = ModelSingleton().get_model(
                backend="transformers",
                model_path=model_path,
                server_url=None,
            )
        except ImportError:
            # MinerU VLM deps not installed — graceful degradation.
            self._predictor = None
        self._load_seconds = time.monotonic() - t0
        self._loaded_vram_mb = max(0, _vram_used_mb() - before)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._unloaded:
            return
        self._free_model()
        self._unloaded = True

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _free_model(self) -> None:
        self._predictor = None
        try:
            from mineru.backend.vlm.vlm_analyze import shutdown_cached_models

            shutdown_cached_models()
        except ImportError:
            pass
        gc.collect()
        try:
            torch = _import_torch()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def _get_doc_pages(
        self,
        pdf_path: Path,
        page_subset: list[int] | None = None,
    ) -> dict[int, PageData]:
        """Return cached per-page data for `pdf_path`, parsing at most once per key.

        Args:
            pdf_path: Path to the PDF file.
            page_subset: 1-indexed page numbers to parse.  None = full document.
                         Results are always keyed by original page numbers.

        Returns dict[int, PageData] where PageData holds page_size and elements.

        Cache key is (pdf_path, frozenset(page_subset) | None), so partial-page
        and full-document runs live in separate cache slots and never interfere.

        Preference order:
          1. `parse_doc_fn` injection (test path) — called without page_subset
             for back-compat, then filtered to the requested subset.
          2. Real model via `_make_real_parse_doc_fn` — receives page_subset so
             the PDF is sliced before VLM inference.
          3. Fallback: empty dict when no model available.

        Note: `parse_page_fn` injection is handled separately in run() /
        extract_region() for legacy back-compat; it does NOT flow through here.
        """
        cache_key: tuple[Path, frozenset[int] | None] = (
            pdf_path,
            frozenset(page_subset) if page_subset else None,
        )
        if cache_key in self._doc_cache:
            return self._doc_cache[cache_key]

        if self._parse_doc_fn is not None:
            # Normalise to dict[int, PageData]. Legacy test injections may return
            # dict[int, list[ParsedElement]] — detect and wrap on the fly.
            # Call without page_subset for back-compat; filter afterwards.
            raw = self._parse_doc_fn(pdf_path)
            pages: dict[int, PageData] = {}
            for k, v in raw.items():
                if page_subset is not None and k not in page_subset:
                    continue
                if isinstance(v, PageData):
                    pages[k] = v
                else:
                    # Legacy list[ParsedElement] from old test injections
                    pages[k] = PageData(page_size=(612.0, 792.0), elements=list(v))
        elif self._predictor is not None:
            pages = _make_real_parse_doc_fn(self._predictor, self._image_writer_dir)(
                pdf_path, page_subset
            )
        else:
            pages = {}

        self._doc_cache[cache_key] = pages
        return pages

    def _get_parse_page_fn(self) -> ParsePageFn:
        """Legacy accessor for the per-page parse function (back-compat)."""
        if self._parse_page_fn is not None:
            return self._parse_page_fn
        if self._predictor is not None:
            return _make_real_parse_page_fn(self._predictor)
        # Fallback when model could not be loaded.
        return lambda _pdf, _page: []

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, pdf_path: Path, boxes: list[SegmentBox]) -> Iterator[WorkerEvent]:
        # Sort by (page, y_top, x_left) so emitted HTML is in reading order —
        # otherwise titles appear wherever YOLO emitted them in seg.boxes,
        # not where they sit on the page.
        targets = sorted(
            (b for b in boxes if b.kind != BoxKind.discard),
            key=lambda b: (b.page, b.bbox[1], b.bbox[0]),
        )
        total = len(targets)

        yield ModelLoadingEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            source=os.environ.get("LOCAL_PDF_MINERU_BIN", "mineru"),
            vram_estimate_mb=self.estimated_vram_mb,
        )

        yield ModelLoadedEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            vram_actual_mb=self._loaded_vram_mb,
            load_seconds=self._load_seconds,
        )

        run_t0 = time.monotonic()
        eta = EtaCalculator()
        self.results = []

        if self._extract_fn is not None:
            # Legacy inject — per-box extraction function (test path).
            for i, box in enumerate(targets, start=1):
                result = self._extract_fn(pdf_path, box)
                self.results.append(result)
                eta.observe(i, time.monotonic())
                eta_seconds, throughput = eta.estimate(total=total)
                yield WorkProgressEvent(
                    model=self.name,
                    timestamp_ms=now_ms(),
                    stage="box",
                    current=i,
                    total=total,
                    eta_seconds=eta_seconds,
                    throughput_per_sec=throughput,
                    vram_current_mb=_vram_used_mb(),
                )
        elif self._parse_page_fn is not None:
            # Legacy parse_page_fn injection: parse each unique page once (back-compat).
            parse_page = self._get_parse_page_fn()
            page_cache: dict[int, list[ParsedElement]] = {}

            unique_pages = sorted({b.page for b in targets})
            for pg in unique_pages:
                page_cache[pg] = parse_page(pdf_path, pg)

            # Determine h1 promotion candidate (first page, first sorted box)
            first_page = min({b.page for b in targets}) if targets else 1
            first_page_boxes = sorted(
                [b for b in targets if b.page == first_page],
                key=lambda b: (b.bbox[1], b.bbox[0]),
            )
            first_box_id = first_page_boxes[0].box_id if first_page_boxes else None
            single_heading_on_first_page = (
                sum(1 for b in first_page_boxes if b.kind == BoxKind.heading) == 1
            )

            # Per-page best-match assignment (legacy path).
            boxes_by_page_legacy: dict[int, list[SegmentBox]] = {}
            for b in targets:
                boxes_by_page_legacy.setdefault(b.page, []).append(b)
            page_assignments_legacy: dict[int, dict[str, list[ParsedElement]]] = {}
            for pg, page_boxes in boxes_by_page_legacy.items():
                page_elements_pg = page_cache.get(pg, [])
                boxes_with_pts_pg = [
                    (b.box_id, _user_bbox_to_pts(b.bbox, self._raster_dpi), b.kind)
                    for b in page_boxes
                ]
                page_assignments_legacy[pg] = _rescue_captions_from_visual_boxes(
                    _assign_elements_to_boxes(boxes_with_pts_pg, page_elements_pg),
                    page_boxes,
                    self._raster_dpi,
                )

            for i, box in enumerate(targets, start=1):
                page_size = (612.0, 792.0)  # default for legacy path
                matched = page_assignments_legacy.get(box.page, {}).get(box.box_id, [])
                promote = (
                    box.kind == BoxKind.heading
                    and box.box_id == first_box_id
                    and single_heading_on_first_page
                    and box.page == first_page
                )
                html = _build_one_box_html(
                    box, matched, page_size, raster_dpi=self._raster_dpi, promote_to_h1=promote
                )
                self.results.append(MinerUResult(box_id=box.box_id, html=html))
                eta.observe(i, time.monotonic())
                eta_seconds, throughput = eta.estimate(total=total)
                yield WorkProgressEvent(
                    model=self.name,
                    timestamp_ms=now_ms(),
                    stage="box",
                    current=i,
                    total=total,
                    eta_seconds=eta_seconds,
                    throughput_per_sec=throughput,
                    vram_current_mb=_vram_used_mb(),
                )
        else:
            # Main path: parse only the pages that targets actually need,
            # then look up each page from the cache.  Slicing the PDF before
            # calling doc_analyze avoids VLM work on irrelevant pages.
            unique_pages = sorted({b.page for b in targets})
            doc_pages = self._get_doc_pages(pdf_path, page_subset=unique_pages or None)

            # Determine h1 promotion candidate
            non_discard = [b for b in targets if b.kind != BoxKind.discard]
            first_page = min((b.page for b in non_discard), default=1)
            first_page_boxes = sorted(
                [b for b in non_discard if b.page == first_page],
                key=lambda b: (b.bbox[1], b.bbox[0]),
            )
            first_box_id = first_page_boxes[0].box_id if first_page_boxes else None
            single_heading_on_first_page = (
                sum(1 for b in first_page_boxes if b.kind == BoxKind.heading) == 1
            )

            # Group user boxes by page for per-page best-match assignment.
            boxes_by_page: dict[int, list[SegmentBox]] = {}
            for b in targets:
                boxes_by_page.setdefault(b.page, []).append(b)

            # Per-page best-match assignment: each MinerU element goes to at most ONE box.
            page_assignments: dict[int, dict[str, list[ParsedElement]]] = {}
            for pg, page_boxes in boxes_by_page.items():
                page_data = doc_pages.get(pg)
                page_elements = page_data.elements if page_data is not None else []
                boxes_with_pts = [
                    (b.box_id, _user_bbox_to_pts(b.bbox, self._raster_dpi), b.kind)
                    for b in page_boxes
                ]
                page_assignments[pg] = _rescue_captions_from_visual_boxes(
                    _assign_elements_to_boxes(boxes_with_pts, page_elements),
                    page_boxes,
                    self._raster_dpi,
                )

            for i, box in enumerate(targets, start=1):
                page_data = doc_pages.get(box.page)
                page_size = page_data.page_size if page_data is not None else (612.0, 792.0)
                matched = page_assignments.get(box.page, {}).get(box.box_id, [])
                promote = (
                    box.kind == BoxKind.heading
                    and box.box_id == first_box_id
                    and single_heading_on_first_page
                    and box.page == first_page
                )
                html = _build_one_box_html(
                    box, matched, page_size, raster_dpi=self._raster_dpi, promote_to_h1=promote
                )
                self.results.append(MinerUResult(box_id=box.box_id, html=html))
                eta.observe(i, time.monotonic())
                eta_seconds, throughput = eta.estimate(total=total)
                yield WorkProgressEvent(
                    model=self.name,
                    timestamp_ms=now_ms(),
                    stage="box",
                    current=i,
                    total=total,
                    eta_seconds=eta_seconds,
                    throughput_per_sec=throughput,
                    vram_current_mb=_vram_used_mb(),
                )

        yield WorkCompleteEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            total_seconds=time.monotonic() - run_t0,
            items_processed=total,
            output_summary={"boxes_extracted": total},
        )

    def extract_region(self, pdf_path: Path, box: SegmentBox) -> MinerUResult:
        """Single-bbox extraction path.  Caller wraps in `with MineruWorker(...) as w:`."""
        if self._extract_fn is not None:
            return self._extract_fn(pdf_path, box)

        if self._parse_page_fn is not None:
            # Legacy back-compat path.
            parse_page = self._get_parse_page_fn()
            page_elements = parse_page(pdf_path, box.page)
            page_size = (612.0, 792.0)
        else:
            doc_pages = self._get_doc_pages(pdf_path, page_subset=[box.page])
            page_data = doc_pages.get(box.page)
            page_elements = page_data.elements if page_data is not None else []
            page_size = page_data.page_size if page_data is not None else (612.0, 792.0)

        # Use the same assignment helper for consistency (single-box: no competition).
        boxes_with_pts = [(box.box_id, _user_bbox_to_pts(box.bbox, self._raster_dpi), box.kind)]
        assignments = _assign_elements_to_boxes(boxes_with_pts, page_elements)
        matched = assignments.get(box.box_id, [])
        html = _build_one_box_html(box, matched, page_size, raster_dpi=self._raster_dpi)
        return MinerUResult(box_id=box.box_id, html=html)

    def unload(self) -> Iterator[WorkerEvent]:
        if self._unloaded:
            return
        yield ModelUnloadingEvent(model=self.name, timestamp_ms=now_ms())
        before = _vram_used_mb()
        self._free_model()
        freed = max(0, before - _vram_used_mb())
        self._unloaded = True
        yield ModelUnloadedEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            vram_freed_mb=freed,
        )
