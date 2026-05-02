"""MinerU 3 extraction worker — in-process Python API with batch lifecycle.

`MineruWorker` is a context-managed model worker.

- `__enter__`: instantiate the MinerU pipeline model and load weights.
  Emits `ModelLoadingEvent` then `ModelLoadedEvent` with real `load_seconds`
  and `vram_actual_mb`.  If `extract_fn`, `parse_page_fn`, or `parse_doc_fn`
  is injected (test path) the real model is skipped entirely.
- `__exit__`: del model, gc.collect(), torch.cuda.empty_cache().
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


@dataclass(frozen=True)
class ParsedElement:
    """One element returned by a page parse."""

    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF pts
    html: str
    text: str = ""


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

    If nothing qualifies, fall back to the element with the highest IoU.
    Results are sorted by (top, left) for reading order before return.
    """
    if not page_elements:
        return []

    iou_scores = [(_iou(user_bbox, el.bbox), el) for el in page_elements]

    matches: list[ParsedElement] = []
    for score, el in iou_scores:
        cx = (el.bbox[0] + el.bbox[2]) / 2.0
        cy = (el.bbox[1] + el.bbox[3]) / 2.0
        if score > 0.3 or _center_in((cx, cy), user_bbox):
            matches.append(el)

    if not matches:
        # best-effort fallback: element with highest IoU
        best_el = max(iou_scores, key=lambda t: t[0])[1]
        matches = [best_el]

    # Reading order: top then left
    matches.sort(key=lambda el: (el.bbox[1], el.bbox[0]))
    return matches


# ── Text helpers ──────────────────────────────────────────────────────────────


def _html_to_text(html: str) -> str:
    """Strip HTML tags and decode entities, returning plain text."""
    stripped = re.sub(r"<[^>]+>", "", html)
    return html_lib.unescape(stripped)


# ── Block → HTML/markdown conversion ─────────────────────────────────────────

# Fraction of page height that counts as header/footer zone.
_HEADER_FOOTER_FRACTION = 0.08


def _is_page_number(text: str) -> bool:
    """Return True if *text* is a bare page number (digits only, short)."""
    stripped = text.strip()
    return stripped.isdigit() and len(stripped) <= 5


def _block_to_content(block: dict) -> str:
    """Convert a single MinerU para_block to a content string.

    Uses merge_visual_blocks_to_markdown for visual/code blocks and
    merge_para_with_text for all text-based blocks.  Returns "" for blocks
    that produce no text so callers can skip them.
    """
    try:
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
            merge_para_with_text,
            merge_visual_blocks_to_markdown,
        )
    except ImportError:
        # MinerU not installed — return empty.
        return ""

    block_type = block.get("type", "")
    if block_type in _VISUAL_BLOCK_TYPES:
        text = merge_visual_blocks_to_markdown(block)
    else:
        text = merge_para_with_text(block)

    return text or ""


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
    try:
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
            merge_para_with_text,
            merge_visual_blocks_to_markdown,
        )
    except ImportError:
        return ""

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
        raw = merge_visual_blocks_to_markdown(block) or ""
        if not raw:
            return ""
        if block_type == "image":
            inner = f"<figure>{raw}</figure>"
        elif block_type in ("table",):
            inner = f'<div class="extracted-table">{raw}</div>'
        else:
            inner = f"<pre><code>{raw}</code></pre>"
    else:
        raw = merge_para_with_text(block) or ""
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
    page_elements: list[ParsedElement],
    page_size: tuple[float, float],
    raster_dpi: int,
    *,
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

    Returns the complete HTML fragment (tag + data-source-box attribute).
    """
    user_bbox_pts = _user_bbox_to_pts(box.bbox, raster_dpi)
    matched = _match_box_to_elements(user_bbox_pts, page_elements)

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


# ── Real MinerU doc parse (production path) ──────────────────────────────────


def _make_real_parse_doc_fn(model: object) -> ParseDocFn:
    """Return a ParseDocFn that uses the loaded MinerU pipeline model.

    Parses the entire PDF once and returns a dict mapping 1-indexed page
    numbers to PageData (page_size + list of ParsedElement).

    MinerU's `doc_analyze_streaming` API processes a whole PDF; we capture
    all pages in one pass to avoid the N-page x full-doc-parse blowup that
    the old per-page approach caused.
    """
    try:
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze_streaming
    except ImportError as exc:
        raise ImportError("MinerU 'core' extra not installed. Install mineru[core].") from exc

    def _parse_doc(pdf_path: Path) -> dict[int, PageData]:
        """Parse all pages of a PDF using MinerU streaming pipeline."""
        pdf_bytes = pdf_path.read_bytes()

        all_page_infos: list[dict] = []

        class _NullWriter:
            def write(self, *_a: object, **_kw: object) -> None:
                pass

        def _on_ready(
            doc_index: int,
            model_list: list,
            middle_json: dict,
            ocr_enable: bool,
        ) -> None:
            pdf_info = middle_json.get("pdf_info", [])
            all_page_infos.extend(pdf_info)

        doc_analyze_streaming(
            pdf_bytes_list=[pdf_bytes],
            image_writer_list=[_NullWriter()],
            lang_list=[None],
            on_doc_ready=_on_ready,
            parse_method="auto",
        )

        pages: dict[int, PageData] = {}
        for page_idx, page_info in enumerate(all_page_infos):
            page_number = page_idx + 1  # 1-indexed
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
            # MinerU 3.1.6 segregates header / footer / page-number content
            # into `discarded_blocks` (separate from `para_blocks`).  Include
            # both pools so user "auxiliary" bboxes can match their content.
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

                # Extract plain text for text-like blocks
                if block_type in _VISUAL_BLOCK_TYPES:
                    text_content = ""
                else:
                    try:
                        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
                            merge_para_with_text,
                        )

                        text_content = merge_para_with_text(block) or ""
                    except ImportError:
                        text_content = ""

                elements.append(
                    ParsedElement(bbox=(x0, y0, x1, y1), html=html_content, text=text_content)
                )
            pages[page_number] = PageData(page_size=page_size, elements=elements)

        return pages

    return _parse_doc


def _make_real_parse_page_fn(model: object) -> ParsePageFn:
    """Return a ParsePageFn wrapping _make_real_parse_doc_fn for single-page calls.

    This is a compatibility shim: it re-parses the full doc on every call.
    Production code should use _get_doc_pages / ParseDocFn instead.

    TODO(mineru-api): bind directly to MineruPipelineModel.predict_page or
    equivalent when a stable single-page API is exposed.
    """
    parse_doc = _make_real_parse_doc_fn(model)

    def _parse_page(pdf_path: Path, page_number: int) -> list[ParsedElement]:
        pages = parse_doc(pdf_path)
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
    """Context-managed MinerU 3 extraction worker.

    Production use — real model loaded in __enter__, unloaded in __exit__ /
    unload().  Tests inject `extract_fn`, `parse_doc_fn`, or `parse_page_fn`
    to avoid loading any real weights.
    """

    name: str = "MinerU 3"
    estimated_vram_mb: int = 2500

    def __init__(
        self,
        *,
        extract_fn: ExtractFn | None = None,
        parse_doc_fn: ParseDocFn | None = None,
        parse_page_fn: ParsePageFn | None = None,
        raster_dpi: int = 144,
    ) -> None:
        self._extract_fn = extract_fn
        self._parse_doc_fn = parse_doc_fn
        self._parse_page_fn = parse_page_fn
        self._raster_dpi = raster_dpi
        self._model: object = None
        self._loaded_vram_mb = 0
        self._load_seconds = 0.0
        self._unloaded = False
        self.results: list[MinerUResult] = []
        # Per-worker doc cache: avoids re-parsing the same PDF across multiple
        # calls to run() / extract_region() within one worker lifetime.
        self._doc_cache: dict[Path, dict[int, PageData]] = {}

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
            from mineru.backend.pipeline.pipeline_analyze import custom_model_init

            self._model = custom_model_init()
        except ImportError:
            # MinerU not installed — graceful degradation.
            self._model = None
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
        if self._model is not None:
            del self._model
            self._model = None
        gc.collect()
        try:
            torch = _import_torch()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def _get_doc_pages(self, pdf_path: Path) -> dict[int, PageData]:
        """Return cached per-page data for `pdf_path`, parsing at most once.

        Returns dict[int, PageData] where PageData holds page_size and elements.

        Preference order:
          1. `parse_doc_fn` injection (new preferred path, parses doc once).
          2. Real model via `_make_real_parse_doc_fn`.
          3. Fallback: empty dict when no model available.

        Note: `parse_page_fn` injection is handled separately in run() /
        extract_region() for legacy back-compat; it does NOT flow through here.
        """
        if pdf_path in self._doc_cache:
            return self._doc_cache[pdf_path]

        if self._parse_doc_fn is not None:
            # Normalise to dict[int, PageData]. Legacy test injections may return
            # dict[int, list[ParsedElement]] — detect and wrap on the fly.
            pages: dict[int, PageData] = {}
            for k, v in self._parse_doc_fn(pdf_path).items():
                if isinstance(v, PageData):
                    pages[k] = v
                else:
                    # Legacy list[ParsedElement] from old test injections
                    pages[k] = PageData(page_size=(612.0, 792.0), elements=list(v))
        elif self._model is not None:
            pages = _make_real_parse_doc_fn(self._model)(pdf_path)
        else:
            pages = {}

        self._doc_cache[pdf_path] = pages
        return pages

    def _get_parse_page_fn(self) -> ParsePageFn:
        """Legacy accessor for the per-page parse function (back-compat)."""
        if self._parse_page_fn is not None:
            return self._parse_page_fn
        if self._model is not None:
            return _make_real_parse_page_fn(self._model)
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

            for i, box in enumerate(targets, start=1):
                page_elements = page_cache.get(box.page, [])
                page_size = (612.0, 792.0)  # default for legacy path
                promote = (
                    box.kind == BoxKind.heading
                    and box.box_id == first_box_id
                    and single_heading_on_first_page
                    and box.page == first_page
                )
                html = _build_one_box_html(
                    box, page_elements, page_size, self._raster_dpi, promote_to_h1=promote
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
            # Main path: parse entire doc ONCE, look up each page from cache.
            doc_pages = self._get_doc_pages(pdf_path)

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

            for i, box in enumerate(targets, start=1):
                page_data = doc_pages.get(box.page)
                page_size = page_data.page_size if page_data is not None else (612.0, 792.0)
                page_elements = page_data.elements if page_data is not None else []
                promote = (
                    box.kind == BoxKind.heading
                    and box.box_id == first_box_id
                    and single_heading_on_first_page
                    and box.page == first_page
                )
                html = _build_one_box_html(
                    box, page_elements, page_size, self._raster_dpi, promote_to_h1=promote
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
            doc_pages = self._get_doc_pages(pdf_path)
            page_data = doc_pages.get(box.page)
            page_elements = page_data.elements if page_data is not None else []
            page_size = page_data.page_size if page_data is not None else (612.0, 792.0)

        html = _build_one_box_html(box, page_elements, page_size, self._raster_dpi)
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
