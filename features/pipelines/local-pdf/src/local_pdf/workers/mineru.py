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
import logging
import os
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

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
    # Per-line sub-elements (only for text-like blocks). Used by the
    # assignment helper to split a single MinerU block across multiple
    # user-bboxes when the user segmented one visual paragraph into several
    # sub-bboxes (e.g. each bullet of a bullet list got its own bbox).
    # Empty tuple = no line-level decomposition available.
    lines: tuple[ParsedElement, ...] = ()


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
    diagnostics: list[dict] | None = None,
) -> dict[str, list[ParsedElement]]:
    """Assign each MinerU element to at most ONE user box.

    Geometric score per (element, box) pair = IoU; center-in counts as 0.31
    (just above the 0.3 threshold) so a contained-but-low-IoU element still
    claims its box.  Then geometric score is multiplied by a kind-vs-block-type
    compatibility factor (see ``_kind_compat``) — a 0.0 multiplier hard-rejects
    the pair.  Element goes to the highest-final-score box; elements with no
    qualifying box are dropped (no fallback double-counting).

    Pre-pass: when a single MinerU text-like block has non-trivial overlap
    with multiple text-kind user-bboxes (the user segmented one visual
    paragraph into several sub-bboxes — e.g. one bbox per bullet of a list
    that MinerU emitted as a single block), the block is decomposed into
    its line sub-elements (via the precomputed ``ParsedElement.lines``).
    This lets each user-bbox claim its own line.

    Returns dict mapping box_id -> list of matched ParsedElement, sorted by
    reading order (top, left).
    """
    min_score = 0.3
    text_kinds_set = _TEXT_LIKE_KINDS

    # Pre-pass: split blocks that overlap multiple text-kind user-bboxes.
    # Also: when an element has no precomputed lines but text-kind user-bboxes
    # spread across its area, log a warning so the user sees the situation in
    # dev-script logs (no curl required to diagnose).
    import sys

    refined_elements: list[ParsedElement] = []
    for el in page_elements:
        if el.block_type in _VISUAL_BLOCK_TYPES:
            refined_elements.append(el)
            continue
        # Count text-kind user-bboxes that have non-trivial overlap with this
        # block. Threshold 0.05 catches user-bboxes tight around individual lines.
        overlapping_ids: list[str] = []
        for bid, bbox, kind in boxes_with_kinds:
            if kind not in text_kinds_set:
                continue
            if _iou(bbox, el.bbox) > 0.05 or _center_in(
                ((el.bbox[0] + el.bbox[2]) / 2.0, (el.bbox[1] + el.bbox[3]) / 2.0),
                bbox,
            ):
                overlapping_ids.append(bid)
        if len(overlapping_ids) > 1:
            if el.lines:
                msg = (
                    f"[mineru] block bbox={el.bbox} overlaps {len(overlapping_ids)} "
                    f"user-bboxes ({overlapping_ids[:5]}); splitting into "
                    f"{len(el.lines)} line sub-elements"
                )
                print(msg, file=sys.stderr, flush=True)
                if diagnostics is not None:
                    diagnostics.append(
                        {
                            "kind": "split",
                            "block_bbox": list(el.bbox),
                            "block_type": el.block_type,
                            "user_bboxes": overlapping_ids,
                            "n_sub_elements": len(el.lines),
                            "text_preview": el.text[:120],
                        }
                    )
                refined_elements.extend(el.lines)
            else:
                # No precomputed lines available — element will go to one bbox
                # via best-match, others stay empty. Surface the situation.
                msg = (
                    f"[mineru] block bbox={el.bbox} type={el.block_type} overlaps "
                    f"{len(overlapping_ids)} user-bboxes ({overlapping_ids[:5]}) "
                    f"but has NO line sub-elements — only one user-bbox will get "
                    f"the content. text_preview={el.text[:80]!r}"
                )
                print(msg, file=sys.stderr, flush=True)
                if diagnostics is not None:
                    diagnostics.append(
                        {
                            "kind": "no_decomposition",
                            "block_bbox": list(el.bbox),
                            "block_type": el.block_type,
                            "user_bboxes": overlapping_ids,
                            "n_sub_elements": 0,
                            "text_preview": el.text[:120],
                        }
                    )
                refined_elements.append(el)
        else:
            refined_elements.append(el)

    assignments: dict[str, list[ParsedElement]] = {bid: [] for bid, _, _ in boxes_with_kinds}
    for el in refined_elements:
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


# Common LaTeX symbol → Unicode replacements applied inside `$...$` math spans.
# Ambiguous-Unicode warnings are intentional here — these chars are LaTeX
# command targets, not human-typed text.
_LATEX_SYMBOL_MAP = {
    r"\\circ": "°",
    r"\\degree": "°",
    r"\\pm": "±",
    r"\\times": "×",  # noqa: RUF001
    r"\\div": "÷",
    r"\\mu": "µ",
    r"\\alpha": "α",  # noqa: RUF001
    r"\\beta": "β",
    r"\\gamma": "γ",  # noqa: RUF001
    r"\\delta": "δ",
    r"\\Delta": "Δ",
    r"\\sigma": "σ",  # noqa: RUF001
    r"\\rho": "ρ",  # noqa: RUF001
    r"\\phi": "φ",
    r"\\theta": "θ",
    r"\\lambda": "λ",
    r"\\le(?:q)?": "≤",
    r"\\ge(?:q)?": "≥",
    r"\\ne(?:q)?": "≠",
    r"\\approx": "≈",
    r"\\textregistered": "®",
    r"\\textcopyright": "©",
    r"\\texttrademark": "™",
}


def _convert_inline_latex(s: str) -> str:
    """Convert common inline LaTeX math (``$...$``) to plain HTML / Unicode.

    The VLM emits LaTeX-style math for symbols even when the result is just
    a Unicode char (e.g. ``$^{®}$``).  Without MathJax in the iframe this
    renders as raw ``$^{®}$`` text.  We post-process to lift these into
    ``<sup>...</sup>`` / ``<sub>...</sub>`` and Unicode equivalents.

    Handles:
      - ``$^{X}$`` → ``<sup>X</sup>``
      - ``$_{X}$`` → ``<sub>X</sub>``
      - ``$X$``    → ``X`` (unwrap dollar signs around a simple token)
      - LaTeX command symbols inside math mode are mapped via _LATEX_SYMBOL_MAP.

    Display-mode ``$$...$$`` is left alone (we don't have MathJax loaded).
    """
    if not s:
        return s
    # Cells with bare LaTeX (no $ delimiters) still need the final pass; only
    # short-circuit when neither dollars nor backslashes are present.
    if "$" not in s and "\\" not in s:
        return s

    def _replace_latex_symbols(content: str) -> str:
        for pattern, replacement in _LATEX_SYMBOL_MAP.items():
            content = re.sub(pattern, replacement, content)
        return content

    def _math_replace(m: re.Match[str]) -> str:
        body = m.group(1)
        body_mapped = _replace_latex_symbols(body)
        # Superscript: ^{X} or ^X
        sup = re.fullmatch(r"\^(?:\{([^}]*)\}|(\S))", body_mapped)
        if sup:
            inner = sup.group(1) if sup.group(1) is not None else sup.group(2)
            return f"<sup>{inner}</sup>"
        # Subscript: _{X} or _X
        sub = re.fullmatch(r"_(?:\{([^}]*)\}|(\S))", body_mapped)
        if sub:
            inner = sub.group(1) if sub.group(1) is not None else sub.group(2)
            return f"<sub>{inner}</sub>"
        # Anything more complex (\dot{Q}_{max, BE}, fractions, etc.) — feed
        # to latex2mathml in inline mode so it renders properly inside table
        # cells / paragraphs.  Use the original LaTeX (not symbol-mapped)
        # because latex2mathml understands the LaTeX commands directly.
        if "\\" in body or "{" in body:
            try:
                from latex2mathml.converter import convert as _l2mml

                return str(_l2mml(_normalize_latex_primes(body)))
            except Exception as exc:
                _logger.debug("inline latex2mathml failed for %r: %s", body[:80], exc)
                return html_lib.escape(body)
        # Plain math span — strip the dollar signs.
        return body_mapped

    # Display math first: $$...$$ → MathML via latex2mathml. Replace with a
    # marker before processing inline so the inline regex doesn't see the
    # generated MathML. Fall back to <code class="math-error">…</code> if
    # latex2mathml can't parse the body.
    s = _convert_display_math(s)
    # Match $...$ but not $$...$$ (display mode handled above)
    s = re.sub(r"(?<!\$)\$([^$]+)\$(?!\$)", _math_replace, s)
    # Final pass: catch bare LaTeX expressions (no $..$ delimiters) that
    # MinerU sometimes leaves in table cells, e.g. ``\dot{Q}_{max, BE}``.
    return _convert_bare_latex(s)


# Matches a single bare LaTeX expression: command + optional {arg} + any
# number of trailing ^{...} / _{...} / ^X / _X parts, plus optional trailing
# primes ('+). Constrained to non-nested braces and ASCII names so we don't
# accidentally chew through code blocks or paths like C:\Users\foo (which
# lack the {arg} pattern).
_BARE_LATEX_RE = re.compile(r"\\[a-zA-Z]+\{[^{}]*\}(?:[\^_](?:\{[^{}]*\}|\w))*'*")

# MinerU often emits primes AFTER a subscript: \dot{Q}_{max, X}''. The
# convention is primes-before-subscript on the variable itself. Move them
# so latex2mathml renders Q̇'' as one unit with the subscript attached.
_TRAILING_PRIMES_AFTER_SUBSCRIPT_RE = re.compile(r"(_\{[^{}]*\}|_\w)('+)$")


def _normalize_latex_primes(latex: str) -> str:
    """Move trailing primes from after a subscript to before it.

    ``\\dot{Q}_{max,X}''`` → ``\\dot{Q}''_{max,X}`` so latex2mathml renders
    the prime as part of the variable, not floating after the subscript.
    No-op when no primes are at the tail.
    """
    return _TRAILING_PRIMES_AFTER_SUBSCRIPT_RE.sub(r"\2\1", latex)


def _convert_bare_latex(s: str) -> str:
    """Convert undelimited LaTeX expressions in *s* to inline MathML.

    Looks for ``\\cmd{arg}`` patterns optionally followed by ``_{...}`` /
    ``^{...}`` etc. Each match is converted via latex2mathml. Surrounding
    text is preserved verbatim. No-op when no bare LaTeX is present.
    """
    if "\\" not in s or not _BARE_LATEX_RE.search(s):
        return s
    try:
        from latex2mathml.converter import convert as _l2mml
    except ImportError:
        return s

    def _replace(m: re.Match[str]) -> str:
        body = _normalize_latex_primes(m.group(0))
        try:
            return str(_l2mml(body))
        except Exception as exc:
            _logger.debug("bare latex2mathml failed for %r: %s", body[:80], exc)
            return html_lib.escape(body)

    return _BARE_LATEX_RE.sub(_replace, s)


_DISPLAY_MATH_RE = re.compile(r"\$\$\s*(.*?)\s*\$\$", re.DOTALL)


def _convert_display_math(s: str) -> str:
    """Render ``$$...$$`` blocks as inline MathML so the iframe shows them."""
    if "$$" not in s:
        return s
    try:
        from latex2mathml.converter import convert as _l2mml
    except ImportError:
        return s

    def _replace(m: re.Match[str]) -> str:
        body = m.group(1).strip()
        if not body:
            return ""
        try:
            mathml = _l2mml(body)
        except Exception as exc:  # latex2mathml raises various exception types
            _logger.debug("latex2mathml failed for %r: %s", body[:80], exc)
            escaped = html_lib.escape(body)
            return f'<code class="math-error">{escaped}</code>'
        # latex2mathml emits an inline <math display="inline"> element; flip
        # to display="block" so equations get their own line + center align.
        mathml = (
            mathml.replace('display="inline"', 'display="block"', 1)
            if 'display="inline"' in mathml
            else mathml.replace("<math ", '<math display="block" ', 1)
        )
        return f'<div class="math-display">{mathml}</div>'

    return _DISPLAY_MATH_RE.sub(_replace, s)


# ── Caption rescue helpers ────────────────────────────────────────────────────

_CAPTION_RE = re.compile(r"<caption[^>]*>(.*?)</caption>", re.DOTALL | re.IGNORECASE)
_LEADING_TEXT_RE = re.compile(r"^(.*?)(?=<(?:table|figure)\b)", re.DOTALL | re.IGNORECASE)


_TRAILING_TEXT_RE = re.compile(r"(?:</table>|</figure>)(.*?)$", re.DOTALL | re.IGNORECASE)


def _try_extract_caption(html: str) -> tuple[str, str] | None:
    """Return (caption_text, html_without_caption) if a caption can be extracted.

    Tries, in order:
      1. <caption> tag inside the HTML
      2. Leading text before <table>/<figure>
      3. Trailing text after </table>/</figure> (caption-below-table layout
         the VLM sometimes emits)
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
    # Strategy 3: trailing text after </table>/</figure> (caption-below layout).
    m = _TRAILING_TEXT_RE.search(html)
    if m:
        trailing = m.group(1).strip()
        clean = re.sub(r"<[^>]+>", "", trailing).strip()
        if len(clean) >= 5:
            return clean, html[: m.start(1)]
    return None


def _block_to_line_elements(block: dict, block_type: str) -> tuple[ParsedElement, ...]:
    """Decompose a text-like MinerU block into per-line ParsedElements.

    Used by _assign_elements_to_boxes when a single block overlaps multiple
    user-bboxes — splitting by line lets each user-bbox claim its own line.

    Tries (in order):
      1. block['lines'] — pipeline-style structured lines with bboxes.
      2. block['blocks'] — sub-block-style nested structure (some VLM cases).
      3. text-split fallback: split text on newlines and interpolate per-line
         bboxes by dividing the parent block bbox vertically by N.

    Returns empty tuple if no usable decomposition is found.
    """
    parent_bbox = block.get("bbox")
    parent_pts: tuple[float, float, float, float] | None = None
    if parent_bbox is not None:
        try:
            parent_pts = (
                float(parent_bbox[0]),
                float(parent_bbox[1]),
                float(parent_bbox[2]),
                float(parent_bbox[3]),
            )
        except (TypeError, ValueError):
            parent_pts = None

    # ── Strategy 1: pipeline-style lines with bboxes ─────────────────────────
    raw_lines = block.get("lines") or []
    if len(raw_lines) >= 2:
        out: list[ParsedElement] = []
        for line in raw_lines:
            lbbox = line.get("bbox")
            if lbbox is None:
                continue
            try:
                lx0, ly0, lx1, ly1 = (float(v) for v in lbbox[:4])
            except (TypeError, ValueError):
                continue
            spans = line.get("spans") or []
            text_parts: list[str] = []
            for span in spans:
                content = span.get("content")
                if isinstance(content, str) and content:
                    text_parts.append(content)
            line_text = "".join(text_parts).strip()
            if not line_text:
                continue
            line_text = _convert_inline_latex(line_text)
            out.append(
                ParsedElement(
                    bbox=(lx0, ly0, lx1, ly1),
                    html=f"<p>{line_text}</p>",
                    text=line_text,
                    block_type=block_type,
                )
            )
        if len(out) >= 2:
            return tuple(out)

    # ── Strategy 2: nested sub-blocks (some VLM emissions) ───────────────────
    sub_blocks = block.get("blocks") or []
    if len(sub_blocks) >= 2:
        out2: list[ParsedElement] = []
        for sb in sub_blocks:
            sbbox = sb.get("bbox") if isinstance(sb, dict) else None
            if sbbox is None:
                continue
            try:
                sx0, sy0, sx1, sy1 = (float(v) for v in sbbox[:4])
            except (TypeError, ValueError):
                continue
            sb_text = _walk_block_for_text(sb).strip()
            if not sb_text:
                continue
            sb_text = _convert_inline_latex(sb_text)
            out2.append(
                ParsedElement(
                    bbox=(sx0, sy0, sx1, sy1),
                    html=f"<p>{sb_text}</p>",
                    text=sb_text,
                    block_type=block_type,
                )
            )
        if len(out2) >= 2:
            return tuple(out2)

    # ── Strategy 3: text-split fallback ──────────────────────────────────────
    # Try the merged-text first (handles structured spans), fall back to raw
    # 'content'/'text' field. Split on newlines OR on common bullet markers.
    merged_text = _safe_merge_para_text(block) or _walk_block_for_text(block)
    if not merged_text or parent_pts is None:
        return ()

    # Split on newlines first; if that gives only one line, try bullet markers.
    chunks = [c.strip() for c in re.split(r"\n+", merged_text) if c.strip()]
    if len(chunks) < 2:
        # Try splitting on inline bullet markers (- /  • /  · ) when they
        # start a new "line". Conservative — only at start-of-string boundaries.
        chunks = [
            c.strip() for c in re.split(r"(?:(?<=[.!?])\s+)?(?=[-·•]\s)", merged_text) if c.strip()
        ]
    if len(chunks) < 2:
        return ()

    px0, py0, px1, py1 = parent_pts
    height = py1 - py0
    if height <= 0:
        return ()
    # Interpolate per-line bboxes by dividing the parent vertically.
    n = len(chunks)
    step = height / n
    out3: list[ParsedElement] = []
    for i, chunk in enumerate(chunks):
        ly0 = py0 + i * step
        ly1 = py0 + (i + 1) * step
        chunk = _convert_inline_latex(chunk)
        out3.append(
            ParsedElement(
                bbox=(px0, ly0, px1, ly1),
                html=f"<p>{chunk}</p>",
                text=chunk,
                block_type=block_type,
            )
        )
    return tuple(out3)


def _attach_source_box_to_caption(html: str, source_box_id: str) -> str:
    """Re-tag the caption portion of a table/figure block so clicks map back
    to the user's caption/heading bbox instead of the surrounding visual bbox.

    Tries the ``<caption>`` tag first.  If absent, wraps the leading text
    before the first ``<table>``/``<figure>`` opening tag in a ``<span>``.
    Returns the HTML unchanged when neither pattern is found.
    """
    if not html:
        return html

    if _CAPTION_RE.search(html):
        # Strip any existing data-source-box on the caption tag, then inject ours.
        def _add_attr(m: re.Match[str]) -> str:
            existing = m.group(1) or ""
            cleaned = re.sub(r'\s*data-source-box="[^"]*"', "", existing)
            return f'<caption data-source-box="{source_box_id}"{cleaned}>'

        return re.sub(r"<caption([^>]*)>", _add_attr, html, count=1)

    m = _LEADING_TEXT_RE.match(html)
    if m:
        leading = m.group(1)
        if leading and re.sub(r"<[^>]+>", "", leading).strip():
            rest = html[m.end(1) :]
            return f'<span data-source-box="{source_box_id}">{leading}</span>{rest}'
    return html


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
    diagnostics: list[dict] | None = None,
) -> dict[str, list[ParsedElement]]:
    """Post-process page assignments: route captions hidden inside table/figure
    blocks to nearby empty heading/caption/paragraph user-boxes.

    Selection is by spatial adjacency (same column + small vertical gap),
    not containment — caption-above-table is the canonical layout.

    When ``diagnostics`` is provided, appends one entry per attempted rescue:
      - kind="caption_rescue" on success (caption text routed to the empty bbox
        AND data-source-box rewritten on the <caption>/leading text)
      - kind="caption_rescue_failed" when the visual element's HTML had no
        extractable caption (no <caption> tag and no leading text before <table>).
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
        rescued = False
        for idx, el in enumerate(win_els):
            rescue = _try_extract_caption(el.html)
            if rescue is None:
                continue
            cap_text, cleaned_html = rescue
            # Single source of truth: caption renders ONCE as <p class="caption-ref">
            # at the heading user-bbox's position (reading-order sort places it
            # before/after the table to match the source PDF).  Strip it from the
            # table block so it doesn't appear twice.  Click-mapping always lands
            # on the heading bbox because the caption text is no longer inside the
            # table's data-source-box wrapper.
            synthetic = ParsedElement(
                bbox=empty_pts,
                html=f"<p>{cap_text}</p>",
                text=cap_text,
                block_type="caption_rescue",
            )
            new_assignments[empty_id].append(synthetic)
            if cleaned_html != el.html:
                new_assignments[win_id][idx] = ParsedElement(
                    bbox=el.bbox,
                    html=cleaned_html,
                    text=el.text,
                    block_type=el.block_type,
                )
            if diagnostics is not None:
                diagnostics.append(
                    {
                        "kind": "caption_rescue",
                        "source_bbox": empty_id,
                        "target_visual_bbox": win_id,
                        "caption_text": cap_text[:200],
                        "click_remap": True,
                    }
                )
            rescued = True
            break

        if not rescued and diagnostics is not None:
            # We had a candidate visual neighbor but no extractable caption text.
            # Surface the situation AND a snippet of the visual element's HTML so
            # we can see what shape MinerU produced (helps when the caption is
            # somewhere unusual — e.g. inside <thead>, <tbody> first row, etc.).
            preview = (win_els[0].text or "")[:200] if win_els else ""
            html_preview = (win_els[0].html or "")[:400] if win_els else ""
            diagnostics.append(
                {
                    "kind": "caption_rescue_failed",
                    "source_bbox": empty_id,
                    "target_visual_bbox": win_id,
                    "caption_text": "",
                    "text_preview": preview,
                    "target_html_preview": html_preview,
                }
            )

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

    # ── visual kinds: use MinerU HTML as-is ───────────────────────────────────
    if kind in _VISUAL_KINDS:
        if matched:
            # Use the first matched element's html for visual content
            mineru_html = _convert_inline_latex(matched[0].html or "")
            if mineru_html:
                if kind == BoxKind.table:
                    inner = f'<div class="extracted-table">{mineru_html}</div>'
                else:  # figure
                    inner = f"<figure>{mineru_html}</figure>"
                return f'<div data-source-box="{box_id}">{inner}</div>'
        # No match: emit nothing — user wants empty boxes silent for debugging.
        return ""

    # ── text-like kinds: extract plain text ───────────────────────────────────
    if kind in _TEXT_LIKE_KINDS:
        text = " ".join(_html_to_text(el.html) for el in matched).strip() if matched else ""
        text = _convert_inline_latex(text)

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

        # No match: emit nothing — user wants empty boxes silent for debugging.
        if not text:
            return ""

        if kind == BoxKind.heading:
            tag = "h1" if promote_to_h1 else "h2"
            return f'<{tag} data-source-box="{box_id}">{text}</{tag}>'
        if kind == BoxKind.paragraph:
            # If MinerU returned multiple paragraph elements for one user box,
            # emit each as its own <p> so visual paragraph breaks survive
            # (rather than collapsing N paragraphs into a single inline blob).
            if len(matched) > 1:
                return "".join(
                    f'<p data-source-box="{box_id}">'
                    f"{_convert_inline_latex(_html_to_text(el.html)).strip()}</p>"
                    for el in matched
                    if _html_to_text(el.html).strip()
                )
            return f'<p data-source-box="{box_id}">{text}</p>'
        if kind == BoxKind.list_item:
            # Same treatment for list items — one <li> per matched element.
            if len(matched) > 1:
                return "".join(
                    f'<li data-source-box="{box_id}">'
                    f"{_convert_inline_latex(_html_to_text(el.html)).strip()}</li>"
                    for el in matched
                    if _html_to_text(el.html).strip()
                )
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
                # Convert inline LaTeX math (e.g. $^{®}$) to HTML/Unicode so
                # the editor (no MathJax) renders sensibly.
                html_content = _convert_inline_latex(html_content)

                # Extract plain text for text-like blocks (defensive against
                # blocks without the expected 'lines' key — see _safe_merge_para_text).
                if block_type in _VISUAL_BLOCK_TYPES:
                    text_content = ""
                    line_subs: tuple[ParsedElement, ...] = ()
                else:
                    text_content = _convert_inline_latex(_safe_merge_para_text(block))
                    # Pre-build line-level sub-elements so the assignment
                    # helper can split this block when multiple user-bboxes
                    # spread across its lines (e.g. one user-bbox per bullet
                    # in a bullet list MinerU emitted as one text block).
                    line_subs = _block_to_line_elements(block, block_type)

                elements.append(
                    ParsedElement(
                        bbox=(x0, y0, x1, y1),
                        html=html_content,
                        text=text_content,
                        block_type=block_type,
                        lines=line_subs,
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
        # Per-run diagnostics. Reset on each run() call. Each entry is a dict
        # describing a notable assignment event (split / no_decomposition).
        # Surfaced to the frontend via mineru.json so the user can inspect
        # what the worker decided per-page in the extract sidebar.
        self.diagnostics: list[dict] = []
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

        # Reset per-run diagnostics so each new run() starts clean.
        self.diagnostics = []
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
                pg_diags: list[dict] = []
                page_assignments_legacy[pg] = _rescue_captions_from_visual_boxes(
                    _assign_elements_to_boxes(
                        boxes_with_pts_pg, page_elements_pg, diagnostics=pg_diags
                    ),
                    page_boxes,
                    self._raster_dpi,
                    diagnostics=pg_diags,
                )
                for d in pg_diags:
                    d["page"] = pg
                self.diagnostics.extend(pg_diags)

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
                pg_diags = []
                page_assignments[pg] = _rescue_captions_from_visual_boxes(
                    _assign_elements_to_boxes(boxes_with_pts, page_elements, diagnostics=pg_diags),
                    page_boxes,
                    self._raster_dpi,
                    diagnostics=pg_diags,
                )
                for d in pg_diags:
                    d["page"] = pg
                self.diagnostics.extend(pg_diags)

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


# ── Crop + VLM re-extract (per-bbox edit path) ───────────────────────────────

_logger = logging.getLogger(__name__)

# Per-kind visual hint specification.
# Colours match BoxLegend.tsx so the burned-in rectangle matches the UI overlay.
_KIND_HINT_SPEC: dict[BoxKind, tuple[str, str]] = {
    BoxKind.heading: ("HEADING", "#2563eb"),  # blue
    BoxKind.paragraph: ("PARAGRAPH", "#16a34a"),  # green
    BoxKind.list_item: ("LIST", "#4f46e5"),  # indigo
    BoxKind.table: ("TABLE", "#ea580c"),  # orange  (BoxLegend)
    BoxKind.figure: ("FIGURE", "#0d9488"),  # teal    (BoxLegend)
    BoxKind.caption: ("CAPTION", "#9333ea"),  # purple  (BoxLegend)
    BoxKind.formula: ("FORMULA", "#db2777"),  # pink
    BoxKind.auxiliary: ("AUX", "#06b6d4"),  # cyan    (BoxLegend)
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _crop_pdf_with_visual_hint(
    pdf_bytes: bytes,
    page: int,
    bbox_pts: tuple[float, float, float, float],
    user_kind: BoxKind,
    *,
    padding_pts: float = 8.0,
    raster_dpi: int = 200,
) -> bytes:
    """Render the bbox region as a PNG, draw a rectangle + label hint onto the
    image, then wrap the annotated image in a one-page PDF for the VLM.

    Falls back silently to ``_crop_pdf_to_bbox`` if any required library is
    missing or if the render step fails.
    """
    import io as _io

    try:
        import pdfplumber
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        _logger.warning("visual hint unavailable (missing lib: %s); using plain crop", exc)
        return _crop_pdf_to_bbox(pdf_bytes, page, bbox_pts, padding_pts=padding_pts)

    x0, y0, x1, y1 = bbox_pts

    # pdfplumber uses top-down PDF coordinates for crop() when using a
    # page that has been converted — we expand by padding first.
    import pypdf as _pypdf

    # Get page height in points so we can convert to pdfplumber's coordinate
    # convention (top-down from the page top = same as our storage convention).
    reader = _pypdf.PdfReader(_io.BytesIO(pdf_bytes))
    page_obj = reader.pages[page - 1]
    mb = page_obj.mediabox
    page_h_pt = float(mb.height)
    page_w_pt = float(mb.width)

    # Padded crop box — clamped to page dimensions.
    cx0 = max(0.0, x0 - padding_pts)
    cy0 = max(0.0, y0 - padding_pts)
    cx1 = min(page_w_pt, x1 + padding_pts)
    cy1 = min(page_h_pt, y1 + padding_pts)

    # pdfplumber crop() takes (x0, top, x1, bottom) in top-down coords.
    try:
        with pdfplumber.open(_io.BytesIO(pdf_bytes)) as pdf:
            plumber_page = pdf.pages[page - 1]
            cropped = plumber_page.crop((cx0, cy0, cx1, cy1))
            img_obj = cropped.to_image(resolution=raster_dpi)
            pil_img: Image.Image = img_obj.original.convert("RGB")
    except Exception as exc:
        _logger.warning("pdfplumber crop/render failed (%s); using plain crop", exc)
        return _crop_pdf_to_bbox(pdf_bytes, page, bbox_pts, padding_pts=padding_pts)

    spec = _KIND_HINT_SPEC.get(user_kind)
    if spec is not None:
        _label_text, hex_color = spec
        rgb = _hex_to_rgb(hex_color)

        draw = ImageDraw.Draw(pil_img)
        w, h = pil_img.size

        # Colored border around the crop — the VLM picks up the color cue
        # without OCR'ing any baked-in text. Earlier we drew a "PARAGRAPH" /
        # "HEADING" badge in the corner, but the VLM then transcribed that
        # label as part of the extracted text (e.g. "...ermittelt: PARAGRAPH").
        border = 4
        for i in range(border):
            draw.rectangle([i, i, w - 1 - i, h - 1 - i], outline=rgb)
        # ImageFont import is no longer used here, but kept available in
        # case future visual hints (e.g. an external legend image) need it.
        _ = ImageFont

    # Wrap as a 1-page PDF using PIL's PDF save capability.
    buf = _io.BytesIO()
    pil_img.save(buf, format="PDF")
    return buf.getvalue()


def _crop_pdf_to_bbox(
    pdf_bytes: bytes,
    page: int,  # 1-indexed
    bbox_pts: tuple[float, float, float, float],  # top-down image-coord pts
    padding_pts: float = 8.0,
) -> bytes:
    """Return PDF bytes containing only *page* cropped to *bbox_pts*.

    *bbox_pts* is expressed in PDF points with a **top-down** y-axis (origin at
    the top-left of the page) — the same convention used by our SegmentBox
    storage after ``* 72 / raster_dpi``.

    pypdf's CropBox uses PDF's **bottom-up** y-axis (origin at bottom-left), so
    the conversion is:

        cb_y_lower = page_height - (y1 + padding)   # y1 is bottom in top-down
        cb_y_upper = page_height - (y0 - padding)   # y0 is top in top-down

    Both values are clamped to [0, page_height] / [0, page_width] so negative
    coords or oversized boxes never crash.
    """
    import io as _io

    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(_io.BytesIO(pdf_bytes))
    page_obj = reader.pages[page - 1]

    # pypdf exposes mediabox as a RectangleObject; .width/.height are floats.
    mb = page_obj.mediabox
    page_w = float(mb.width)
    page_h = float(mb.height)

    x0, y0, x1, y1 = bbox_pts

    # Expand by padding, then clamp to [0, page dimension].
    cx0 = max(0.0, x0 - padding_pts)
    cx1 = min(page_w, x1 + padding_pts)
    # Convert top-down y to bottom-up y for CropBox.
    cb_y_lower = max(0.0, page_h - (y1 + padding_pts))
    cb_y_upper = min(page_h, page_h - (y0 - padding_pts))

    writer = PdfWriter()
    writer.add_page(page_obj)
    writer.pages[0].cropbox.lower_left = (cx0, cb_y_lower)
    writer.pages[0].cropbox.upper_right = (cx1, cb_y_upper)

    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def vlm_extract_bbox(
    pdf_bytes: bytes,
    page: int,  # 1-indexed
    bbox_pts: tuple[float, float, float, float],  # top-down image-coord pts
    user_kind: BoxKind,
    *,
    box_id: str,
    parse_doc_fn: Callable[[bytes], dict] | None = None,
    predictor: object | None = None,
    padding_pts: float = 8.0,
    visual_hint: bool = True,
) -> str:
    """Crop the PDF page to *bbox_pts*, run MinerU VLM on the crop, and return
    the rendered HTML fragment for *user_kind*.

    1. Crop the single page to a padded region via ``_crop_pdf_to_bbox`` (or
       ``_crop_pdf_with_visual_hint`` when *visual_hint* is True — default).
    2. Call the VLM (or the injected *parse_doc_fn* in tests) on the one-page
       PDF.
    3. Walk ``para_blocks + discarded_blocks`` of the first (only) page result.
    4. Build kind-driven HTML using the same helpers as the full-doc path.

    Returns the final HTML fragment with ``data-source-box`` attribute.
    Returns "" when no content was found in the crop.
    """
    if visual_hint:
        try:
            crop_bytes = _crop_pdf_with_visual_hint(
                pdf_bytes, page, bbox_pts, user_kind, padding_pts=padding_pts
            )
        except Exception as exc:
            _logger.warning("visual hint failed (%s); falling back to plain crop", exc)
            crop_bytes = _crop_pdf_to_bbox(pdf_bytes, page, bbox_pts, padding_pts=padding_pts)
    else:
        crop_bytes = _crop_pdf_to_bbox(pdf_bytes, page, bbox_pts, padding_pts=padding_pts)

    if parse_doc_fn is not None:
        middle_json = parse_doc_fn(crop_bytes)
        all_page_infos = middle_json.get("pdf_info", []) if middle_json else []
    else:
        try:
            from mineru.backend.vlm.vlm_analyze import doc_analyze

            class _NullWriter:
                def write(self, *_a: object, **_kw: object) -> None:
                    pass

            middle_json, _ = doc_analyze(
                crop_bytes,
                _NullWriter(),
                predictor=predictor,
                backend="transformers",
            )
            all_page_infos = middle_json.get("pdf_info", []) if middle_json else []
        except ImportError:
            return ""

    if not all_page_infos:
        return ""

    page_info = all_page_infos[0]
    raw_page_size = page_info.get("page_size")
    try:
        page_size_pts: tuple[float, float] = (
            (float(raw_page_size[0]), float(raw_page_size[1]))
            if raw_page_size and len(raw_page_size) >= 2
            else (612.0, 792.0)
        )
    except (TypeError, ValueError, IndexError):
        page_size_pts = (612.0, 792.0)

    blocks = (page_info.get("para_blocks") or []) + (page_info.get("discarded_blocks") or [])

    if user_kind in _VISUAL_KINDS:
        # For table/figure: find the first matching block type; fall back to
        # the first block regardless if none match.
        target_types = {"table", "chart"} if user_kind == BoxKind.table else {"image"}
        chosen: dict | None = None
        for blk in blocks:
            if blk.get("type", "") in target_types:
                chosen = blk
                break
        if chosen is None and blocks:
            chosen = blocks[0]
        if chosen is None:
            return ""
        raw_html = _block_to_html(chosen, page_size=page_size_pts)
        raw_html = _convert_inline_latex(raw_html)
        if not raw_html:
            return ""
        if user_kind == BoxKind.table:
            inner = f'<div class="extracted-table">{raw_html}</div>'
        else:
            inner = f"<figure>{raw_html}</figure>"
        return f'<div data-source-box="{box_id}">{inner}</div>'

    # Text-like kinds: concatenate plain text from all blocks.
    text_parts: list[str] = []
    for blk in blocks:
        text = _safe_merge_para_text(blk)
        text = _convert_inline_latex(text)
        if text.strip():
            text_parts.append(text.strip())
    text = " ".join(text_parts)
    if not text:
        return ""

    # Synthesise a minimal SegmentBox so we can delegate to _build_one_box_html.
    # The bbox is expressed in pixel space at raster_dpi=288 (used only for
    # auxiliary-zone detection inside _build_one_box_html).
    _raster_dpi = 288
    scale = _raster_dpi / 72.0
    x0, y0, x1, y1 = bbox_pts
    bbox_px = (x0 * scale, y0 * scale, x1 * scale, y1 * scale)
    synthetic_box = SegmentBox(
        box_id=box_id,
        page=page,
        bbox=bbox_px,
        kind=user_kind,
        confidence=1.0,
        reading_order=0,
    )
    synthetic_el = ParsedElement(
        bbox=bbox_pts,
        html=f"<p>{text}</p>",
        text=text,
        block_type="text",
    )
    return _build_one_box_html(synthetic_box, [synthetic_el], page_size_pts, raster_dpi=_raster_dpi)


# ── VLM segmentation path (MinerU as layout authority) ───────────────────────

# Mapping from MinerU block type to SegmentBox kind.
_VLM_TYPE_TO_KIND: dict[str, BoxKind] = {
    "title": BoxKind.heading,
    "text": BoxKind.paragraph,
    "list": BoxKind.list_item,
    "table": BoxKind.table,
    "chart": BoxKind.table,
    "image": BoxKind.figure,
    "equation": BoxKind.formula,
    "interline_equation": BoxKind.formula,
    "code": BoxKind.formula,
    "index": BoxKind.paragraph,
}


@dataclass(frozen=True)
class VlmSegmentBlock:
    """One segmentation result from the VLM path.

    Yielded by ``vlm_segment_doc`` interleaved with lifecycle events.
    """

    kind: str = "block"
    box: SegmentBox = None  # type: ignore[assignment]
    html_snippet: str = ""
    page_size_pts: tuple[float, float] = (612.0, 792.0)


_OUTER_TAG_RE = re.compile(r"^(<\w+)([\s>])")
_BULLET_PREFIX_RE = re.compile(r"^[\s\-·•*]+")


def _inject_outer_attrs(html: str, attrs: dict[str, str]) -> str:
    """Add the given attributes to the outermost tag in ``html``.

    Skips any attribute already present in the outer tag. No-op if ``html``
    doesn't start with a tag (already-styled fragments pass through unchanged).
    Used for ``data-source-box`` (click-to-highlight), positional attributes
    ``data-x`` / ``data-y`` / ``data-y1`` (used for both aux and body row
    grouping in ``_wrap_html``), and ``data-aux-zone`` / ``data-aux-align``
    (aux-specific layout cues).
    """
    m = _OUTER_TAG_RE.match(html)
    if not m:
        return html
    end_outer = html.find(">", m.end())
    if end_outer < 0:
        return html
    outer_open = html[: end_outer + 1]
    new_attrs = [f'{k}="{v}"' for k, v in attrs.items() if f" {k}=" not in outer_open]
    if not new_attrs:
        return html
    attr_str = " ".join(new_attrs)
    return f"{m.group(1)} {attr_str}{m.group(2)}{html[m.end() :]}"


def _strip_bullet_marker(text: str) -> str:
    """Remove leading bullet markers (``-``, ``•``, ``·``, ``*``) and whitespace."""
    return _BULLET_PREFIX_RE.sub("", text).strip()


def _aux_alignment(x0: float, x1: float, page_width: float) -> str:
    """Classify aux horizontal alignment based on bbox center vs page width.

    Returns "left" (center < 40%), "right" (center > 60%), or "center".
    Used to place same-row aux items in a 3-column grid so left/center/right
    items land where they sat in the original PDF.
    """
    if page_width <= 0:
        return "center"
    ratio = ((x0 + x1) / 2) / page_width
    if ratio < 0.4:
        return "left"
    if ratio > 0.6:
        return "right"
    return "center"


# Visual parent block types whose `blocks` array carries body/caption/footnote.
_VLM_VISUAL_PARENT_TYPES: frozenset[str] = frozenset({"table", "image", "chart", "code"})

# Sub-block type → SegmentBox kind. Charts render as <figure><img> like
# images (MinerU stores them as image_path), so they should also carry
# kind=figure — keeps the SegmentBox kind consistent with the rendered
# HTML element.
_VLM_VISUAL_SUB_KIND: dict[str, BoxKind] = {
    "table_body": BoxKind.table,
    "chart_body": BoxKind.figure,
    "image_body": BoxKind.figure,
    "code_body": BoxKind.formula,
    "table_caption": BoxKind.caption,
    "image_caption": BoxKind.caption,
    "chart_caption": BoxKind.caption,
    "code_caption": BoxKind.caption,
    "table_footnote": BoxKind.auxiliary,
    "image_footnote": BoxKind.auxiliary,
    "chart_footnote": BoxKind.auxiliary,
    "code_footnote": BoxKind.auxiliary,
}


def _render_visual_sub_block_html(sub_block: dict, sub_type: str) -> str:
    """Render one visual sub-block to standalone HTML.

    Body sub-blocks pull their HTML/image from line spans; caption and
    footnote sub-blocks pull merged text via _safe_merge_para_text.
    Returns "" when nothing renderable is found.
    """
    if sub_type.endswith("_caption") or sub_type.endswith("_footnote"):
        text = _safe_merge_para_text(sub_block) or _walk_block_for_text(sub_block)
        if not text.strip():
            return ""
        cls = "caption" if sub_type.endswith("_caption") else "footnote"
        return f'<p class="{cls}">{text.strip()}</p>'

    if sub_type == "table_body":
        for line in sub_block.get("lines", []):
            for span in line.get("spans", []):
                html = span.get("html", "")
                if html:
                    return f'<div class="extracted-table">{html}</div>'
        return ""

    if sub_type in ("image_body", "chart_body"):
        for line in sub_block.get("lines", []):
            for span in line.get("spans", []):
                img_path = span.get("image_path", "")
                if img_path:
                    # Worker emits a relative ``mineru-images/{file}`` path;
                    # frontend rewrites it to the absolute API URL before
                    # passing the html to the iframe srcdoc.
                    raw_desc = (span.get("content") or "").strip()
                    alt_attr = (
                        f' alt="{html_lib.escape(raw_desc, quote=True)}"' if raw_desc else ' alt=""'
                    )
                    # Surface MinerU's VLM description as visible metadata
                    # between the image and the caption (caption is its own
                    # SegmentBox below). Flatten newlines so it reads as
                    # prose, not a column of OCR'd labels.
                    desc_html = ""
                    if raw_desc:
                        flat = " ".join(raw_desc.split())
                        desc_html = (
                            f'<p class="figure-desc">'
                            f"<strong>Beschreibung:</strong> "
                            f"{html_lib.escape(flat)}"
                            f"</p>"
                        )
                    return (
                        f'<figure><img src="mineru-images/{img_path}"{alt_attr}>'
                        f"{desc_html}</figure>"
                    )
        return ""

    if sub_type == "code_body":
        text = _safe_merge_para_text(sub_block) or _walk_block_for_text(sub_block)
        if not text.strip():
            return ""
        return f"<pre><code>{text}</code></pre>"

    return ""


def _aux_line_html(text: str, *, in_top_zone: bool) -> str:
    """Wrap a single aux line in <header>, <footer>, or <span class="page-number">.

    Mirrors the zone-driven branch in ``_block_to_html`` but operates on one
    decomposed line at a time so multi-line discarded blocks render with
    proper per-line semantics.
    """
    text = text.strip()
    if _is_page_number(text):
        return f'<span class="page-number">{text}</span>'
    tag = "header" if in_top_zone else "footer"
    cls = "page-header" if in_top_zone else "page-footer"
    return f'<{tag} class="{cls}">{text}</{tag}>'


def vlm_segment_doc(
    pdf_bytes: bytes,
    *,
    raster_dpi: int = 288,
    page_subset: list[int] | None = None,
    # Test injection: replaces the real doc_analyze call entirely.
    # Signature: (pdf_bytes: bytes) -> dict  (middle_json)
    parse_doc_fn: Callable[[bytes], dict] | None = None,
    # When set, MinerU writes figure / table cropouts here. Required for
    # image_body sub-blocks to render — without it the writer drops them
    # and <img src> points to a file that doesn't exist on disk.
    image_writer_dir: Path | None = None,
) -> Iterator[Any]:
    """Yield segmentation events from the VLM's pdf_info.

    Event stream (in order):
      - ModelLoadingEvent / ModelLoadedEvent
      - WorkProgressEvent (one per block, current=N, total=total_blocks)
      - WorkCompleteEvent
      - ModelUnloadingEvent / ModelUnloadedEvent

    Interleaved with lifecycle events, VlmSegmentBlock items are yielded for
    each para_block and discarded_block in the VLM output.  The router collects
    these to build segments.json and mineru.json without knowing MinerU internals.

    Args:
        pdf_bytes: Raw PDF bytes to analyse.
        raster_dpi: DPI at which segment bboxes are expressed (default 288).
            Bboxes are converted from PDF pts (72 dpi) to pixel space via
            pts * raster_dpi / 72.
        page_subset: 1-indexed page numbers to restrict analysis to.  None = all
            pages.  When provided, only those pages are in the output.
        parse_doc_fn: Test injection; skips the real model entirely.
    """
    scale = raster_dpi / 72.0
    worker_name = MineruWorker.name

    # ── Model load ────────────────────────────────────────────────────────────
    yield ModelLoadingEvent(
        model=worker_name,
        timestamp_ms=now_ms(),
        source=os.environ.get("LOCAL_PDF_MINERU_BIN", "mineru"),
        vram_estimate_mb=MineruWorker.estimated_vram_mb,
    )

    before = _vram_used_mb()
    t0 = time.monotonic()
    predictor = None
    if parse_doc_fn is None:
        try:
            from mineru.backend.vlm.vlm_analyze import ModelSingleton

            model_path = os.environ.get("LOCAL_PDF_MINERU_MODEL_PATH") or None
            predictor = ModelSingleton().get_model(
                backend="transformers",
                model_path=model_path,
                server_url=None,
            )
        except ImportError:
            predictor = None
    load_seconds = time.monotonic() - t0
    loaded_vram_mb = max(0, _vram_used_mb() - before)

    yield ModelLoadedEvent(
        model=worker_name,
        timestamp_ms=now_ms(),
        vram_actual_mb=loaded_vram_mb,
        load_seconds=load_seconds,
    )

    # ── Parse document ────────────────────────────────────────────────────────
    run_t0 = time.monotonic()

    if parse_doc_fn is not None:
        # Test injection: the fn receives pdf_bytes and returns a middle_json dict.
        middle_json = parse_doc_fn(pdf_bytes)
        all_page_infos = middle_json.get("pdf_info", []) if middle_json else []
    else:
        # Production path: slice pages if a subset was requested, then call
        # doc_analyze on the (possibly sliced) PDF bytes.
        if page_subset:
            sorted_subset = sorted(set(page_subset))
            active_bytes = _slice_pdf_to_pages(pdf_bytes, sorted_subset)
        else:
            active_bytes = pdf_bytes
            sorted_subset = None

        try:
            from mineru.backend.vlm.vlm_analyze import doc_analyze

            class _NullWriter:
                def write(self, *_a: object, **_kw: object) -> None:
                    pass

            if image_writer_dir is not None:
                from mineru.data.data_reader_writer import FileBasedDataWriter

                image_writer_dir.mkdir(parents=True, exist_ok=True)
                writer = FileBasedDataWriter(str(image_writer_dir))
            else:
                writer = _NullWriter()

            middle_json, _ = doc_analyze(
                active_bytes,
                writer,
                predictor=predictor,
                backend="transformers",
            )
        except ImportError:
            middle_json = {}
        all_page_infos = middle_json.get("pdf_info", []) if middle_json else []

    # ── Count total blocks for progress reporting ─────────────────────────────
    total_blocks = sum(
        len(pi.get("para_blocks") or []) + len(pi.get("discarded_blocks") or [])
        for pi in all_page_infos
    )

    # ── Iterate pages and emit blocks ─────────────────────────────────────────
    # Pre-compute sorted subset for page-number remapping (avoids re-sorting in loop).
    _sorted_subset: list[int] | None = sorted(set(page_subset)) if page_subset else None

    block_idx = 0
    eta = EtaCalculator()
    for page_idx, page_info in enumerate(all_page_infos):
        # Map sliced-page index back to original page number.
        if _sorted_subset is not None:
            page_number = (
                _sorted_subset[page_idx] if page_idx < len(_sorted_subset) else page_idx + 1
            )
        else:
            page_number = page_idx + 1

        raw_page_size = page_info.get("page_size")
        try:
            page_size_pts: tuple[float, float] = (
                (float(raw_page_size[0]), float(raw_page_size[1]))
                if raw_page_size and len(raw_page_size) >= 2
                else (612.0, 792.0)
            )
        except (TypeError, ValueError, IndexError):
            page_size_pts = (612.0, 792.0)

        para_blocks = page_info.get("para_blocks") or []
        discarded_blocks = page_info.get("discarded_blocks") or []

        # Per-page counter for emitted SegmentBoxes. List blocks decompose into
        # multiple boxes (one per bullet), so this can outrun the source-block
        # index. Box IDs and reading_order both derive from this counter to
        # keep them sequential within a page.
        box_counter = 0

        for block, is_discarded in [(b, False) for b in para_blocks] + [
            (b, True) for b in discarded_blocks
        ]:
            raw_bbox = block.get("bbox")
            if raw_bbox is None:
                block_idx += 1
                continue
            try:
                px0, py0, px1, py1 = (float(v) for v in raw_bbox[:4])
            except (TypeError, ValueError):
                block_idx += 1
                continue

            block_type = block.get("type", "")
            if is_discarded:
                kind = BoxKind.auxiliary
            else:
                kind = _VLM_TYPE_TO_KIND.get(block_type, BoxKind.paragraph)

            # ── Visual blocks: decompose into body + caption + footnote ─────
            # MinerU emits a table/image/chart/code parent with a `blocks`
            # array of typed sub-blocks (table_body, table_caption,
            # table_footnote, etc.), each with its own bbox. Split each into
            # its own SegmentBox so captions are independently editable and
            # the user can click them to highlight just that region.
            if not is_discarded and block_type in _VLM_VISUAL_PARENT_TYPES:
                sub_blocks = block.get("blocks") or []
                emitted_any = False
                for sub in sub_blocks:
                    if not isinstance(sub, dict):
                        continue
                    sub_type = sub.get("type", "")
                    sub_kind = _VLM_VISUAL_SUB_KIND.get(sub_type)
                    if sub_kind is None:
                        continue
                    sub_bbox = sub.get("bbox")
                    if not sub_bbox:
                        continue
                    try:
                        sx0, sy0, sx1, sy1 = (float(v) for v in sub_bbox[:4])
                    except (TypeError, ValueError):
                        continue
                    sub_html = _render_visual_sub_block_html(sub, sub_type)
                    if not sub_html:
                        continue
                    sub_html = _convert_inline_latex(sub_html)
                    sub_box_id = f"p{page_number}-b{box_counter}"
                    sub_html = _inject_outer_attrs(
                        sub_html,
                        {
                            "data-source-box": sub_box_id,
                            "data-x": str(int(sx0)),
                            "data-y": str(int(sy0)),
                            "data-y1": str(int(sy1)),
                        },
                    )
                    sub_bbox_px = (
                        sx0 * scale,
                        sy0 * scale,
                        sx1 * scale,
                        sy1 * scale,
                    )
                    sub_box = SegmentBox(
                        box_id=sub_box_id,
                        page=page_number,
                        bbox=sub_bbox_px,
                        kind=sub_kind,
                        confidence=1.0,
                        reading_order=box_counter,
                        manually_activated=False,
                    )
                    yield VlmSegmentBlock(
                        kind="block",
                        box=sub_box,
                        html_snippet=sub_html,
                        page_size_pts=page_size_pts,
                    )
                    box_counter += 1
                    emitted_any = True

                if emitted_any:
                    block_idx += 1
                    eta.observe(block_idx, time.monotonic())
                    eta_seconds, throughput = eta.estimate(total=max(total_blocks, 1))
                    yield WorkProgressEvent(
                        model=worker_name,
                        timestamp_ms=now_ms(),
                        stage="block",
                        current=block_idx,
                        total=total_blocks,
                        eta_seconds=eta_seconds,
                        throughput_per_sec=throughput,
                        vram_current_mb=_vram_used_mb(),
                    )
                    continue
                # Fall through: visual block with no usable sub-blocks →
                # emit as one box via the default path.

            # ── Multi-line auxiliaries: decompose into per-line boxes ───────
            # Aux blocks (page headers/footers) often cover multiple visual
            # lines; without splitting they render as one <header>/<footer>
            # with all text mashed inline. Split via _block_to_line_elements
            # so each line gets its own bbox + zone + x/y tagging, then the
            # renderer's y-band grouping stacks them visually.
            if is_discarded:
                sub_elements = _block_to_line_elements(block, block_type)
                if len(sub_elements) >= 2:
                    page_h = page_size_pts[1]
                    for sub in sub_elements:
                        sx0, sy0, sx1, sy1 = sub.bbox
                        sub_bbox_px = (
                            sx0 * scale,
                            sy0 * scale,
                            sx1 * scale,
                            sy1 * scale,
                        )
                        sub_box_id = f"p{page_number}-b{box_counter}"
                        sub_y_mid = (sy0 + sy1) / 2
                        in_top = sub_y_mid < page_h / 2
                        sub_html = _aux_line_html(sub.text, in_top_zone=in_top)
                        sub_html = _convert_inline_latex(sub_html)
                        sub_html = _inject_outer_attrs(
                            sub_html,
                            {
                                "data-source-box": sub_box_id,
                                "data-aux-zone": "header" if in_top else "footer",
                                "data-aux-align": _aux_alignment(sx0, sx1, page_size_pts[0]),
                                "data-x": str(int(sx0)),
                                "data-y": str(int(sy0)),
                                "data-y1": str(int(sy1)),
                            },
                        )
                        sub_box = SegmentBox(
                            box_id=sub_box_id,
                            page=page_number,
                            bbox=sub_bbox_px,
                            kind=BoxKind.auxiliary,
                            confidence=1.0,
                            reading_order=box_counter,
                            manually_activated=False,
                        )
                        yield VlmSegmentBlock(
                            kind="block",
                            box=sub_box,
                            html_snippet=sub_html,
                            page_size_pts=page_size_pts,
                        )
                        box_counter += 1

                    block_idx += 1
                    eta.observe(block_idx, time.monotonic())
                    eta_seconds, throughput = eta.estimate(total=max(total_blocks, 1))
                    yield WorkProgressEvent(
                        model=worker_name,
                        timestamp_ms=now_ms(),
                        stage="block",
                        current=block_idx,
                        total=total_blocks,
                        eta_seconds=eta_seconds,
                        throughput_per_sec=throughput,
                        vram_current_mb=_vram_used_mb(),
                    )
                    continue
                # Fall through: single-line aux → emit as one box.

            # ── Lists: decompose into one SegmentBox per bullet ─────────────
            # MinerU emits a list block as a single bbox covering all bullets,
            # so a naive 1:1 mapping renders the whole list as one inline <li>.
            # Splitting via _block_to_line_elements gives each bullet its own
            # bbox + <li>; the router's _group_list_items wraps consecutive
            # <li> siblings in a <ul> for proper bulleted rendering.
            if block_type == "list" and not is_discarded:
                sub_elements = _block_to_line_elements(block, "list")
                if len(sub_elements) >= 2:
                    for sub in sub_elements:
                        sx0, sy0, sx1, sy1 = sub.bbox
                        sub_bbox_px = (
                            sx0 * scale,
                            sy0 * scale,
                            sx1 * scale,
                            sy1 * scale,
                        )
                        sub_box_id = f"p{page_number}-b{box_counter}"
                        sub_text = _strip_bullet_marker(sub.text)
                        sub_html = (
                            f'<li data-source-box="{sub_box_id}" '
                            f'data-x="{int(sx0)}" data-y="{int(sy0)}" '
                            f'data-y1="{int(sy1)}">{sub_text}</li>'
                        )
                        sub_box = SegmentBox(
                            box_id=sub_box_id,
                            page=page_number,
                            bbox=sub_bbox_px,
                            kind=BoxKind.list_item,
                            confidence=1.0,
                            reading_order=box_counter,
                            manually_activated=False,
                        )
                        yield VlmSegmentBlock(
                            kind="block",
                            box=sub_box,
                            html_snippet=sub_html,
                            page_size_pts=page_size_pts,
                        )
                        box_counter += 1

                    block_idx += 1
                    eta.observe(block_idx, time.monotonic())
                    eta_seconds, throughput = eta.estimate(total=max(total_blocks, 1))
                    yield WorkProgressEvent(
                        model=worker_name,
                        timestamp_ms=now_ms(),
                        stage="block",
                        current=block_idx,
                        total=total_blocks,
                        eta_seconds=eta_seconds,
                        throughput_per_sec=throughput,
                        vram_current_mb=_vram_used_mb(),
                    )
                    continue
                # Fall through: list block with no usable decomposition →
                # emit it as one list_item box (existing behaviour).

            # ── Default path: one SegmentBox per source block ───────────────
            bbox_px = (px0 * scale, py0 * scale, px1 * scale, py1 * scale)
            box_id = f"p{page_number}-b{box_counter}"
            box = SegmentBox(
                box_id=box_id,
                page=page_number,
                bbox=bbox_px,
                kind=kind,
                confidence=1.0,
                reading_order=box_counter,
                manually_activated=False,
            )

            html_snippet = _block_to_html(block, page_size=page_size_pts)
            html_snippet = _convert_inline_latex(html_snippet)
            # Positional attrs (data-x/y/y1) go on every snippet so _wrap_html
            # can group same-y items into rows regardless of kind. Aux items
            # also carry zone (header/footer) + align (left/center/right).
            attrs: dict[str, str] = {
                "data-source-box": box_id,
                "data-x": str(int(px0)),
                "data-y": str(int(py0)),
                "data-y1": str(int(py1)),
            }
            if is_discarded:
                page_w, page_h = page_size_pts
                y_mid = (py0 + py1) / 2
                attrs["data-aux-zone"] = "header" if y_mid < page_h / 2 else "footer"
                attrs["data-aux-align"] = _aux_alignment(px0, px1, page_w)
            html_snippet = _inject_outer_attrs(html_snippet, attrs)

            yield VlmSegmentBlock(
                kind="block",
                box=box,
                html_snippet=html_snippet,
                page_size_pts=page_size_pts,
            )

            box_counter += 1
            block_idx += 1
            eta.observe(block_idx, time.monotonic())
            eta_seconds, throughput = eta.estimate(total=max(total_blocks, 1))
            yield WorkProgressEvent(
                model=worker_name,
                timestamp_ms=now_ms(),
                stage="block",
                current=block_idx,
                total=total_blocks,
                eta_seconds=eta_seconds,
                throughput_per_sec=throughput,
                vram_current_mb=_vram_used_mb(),
            )

    yield WorkCompleteEvent(
        model=worker_name,
        timestamp_ms=now_ms(),
        total_seconds=time.monotonic() - run_t0,
        items_processed=block_idx,
        output_summary={"blocks_segmented": block_idx},
    )

    # ── Model unload ──────────────────────────────────────────────────────────
    yield ModelUnloadingEvent(model=worker_name, timestamp_ms=now_ms())
    before_free = _vram_used_mb()
    predictor = None
    if parse_doc_fn is None:
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
    freed = max(0, before_free - _vram_used_mb())
    yield ModelUnloadedEvent(
        model=worker_name,
        timestamp_ms=now_ms(),
        vram_freed_mb=freed,
    )
