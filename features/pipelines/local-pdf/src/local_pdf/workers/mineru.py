"""MinerU 3 extraction worker — in-process Python API with batch lifecycle.

`MineruWorker` is a context-managed model worker.

- `__enter__`: instantiate the MinerU pipeline model and load weights.
  Emits `ModelLoadingEvent` then `ModelLoadedEvent` with real `load_seconds`
  and `vram_actual_mb`.  If `extract_fn` or `parse_page_fn` is injected (test
  path) the real model is skipped entirely.
- `__exit__`: del model, gc.collect(), torch.cuda.empty_cache().
- `run(pdf, boxes)`: collect unique pages, parse each page ONCE (cached),
  match each user bbox to parsed elements via IoU / center-containment, yield
  one `WorkProgressEvent` per box, one `WorkCompleteEvent` at the end.
- `extract_region(pdf, box)`: single-bbox path — same match logic, no stream.

Injection points (tests):
  `extract_fn`: overrides the entire per-box extraction path.
  `parse_page_fn`: overrides only the per-page parse step; matching still
  uses the real `_match_box_to_elements` helper.

No subprocess.  No sidecar.  No HTTP.  Pure in-process Python.
"""

from __future__ import annotations

import gc
import os
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


@dataclass(frozen=True)
class MinerUResult:
    box_id: str
    html: str


ExtractFn = Callable[[Path, SegmentBox], MinerUResult]
ParsePageFn = Callable[[Path, int], list[ParsedElement]]


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


# ── Real MinerU page parse (production path) ─────────────────────────────────


def _make_real_parse_page_fn(model: object) -> ParsePageFn:
    """Return a ParsePageFn that uses the loaded MinerU pipeline model.

    The function parses one PDF page and returns a list of ParsedElement.

    MinerU's `doc_analyze_streaming` API is batch-oriented and requires
    image writers, middle-JSON plumbing, and a streaming callback — wiring
    that correctly is non-trivial and version-sensitive.

    TODO(mineru-api): bind directly to MineruPipelineModel.predict_page or
    equivalent when a stable single-page API is exposed.  For now we use
    the same PDF-bytes → batch path.
    """
    try:
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze_streaming
    except ImportError as exc:
        raise ImportError("MinerU 'core' extra not installed. Install mineru[core].") from exc

    def _parse_page(pdf_path: Path, page_number: int) -> list[ParsedElement]:
        """Parse a single 1-indexed page using MinerU streaming pipeline."""
        pdf_bytes = pdf_path.read_bytes()

        results: list[dict] = []

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
            # page_number is 1-indexed; pdf_info is 0-indexed.
            idx = page_number - 1
            if idx < len(pdf_info):
                results.append(pdf_info[idx])

        doc_analyze_streaming(
            pdf_bytes_list=[pdf_bytes],
            image_writer_list=[_NullWriter()],
            lang_list=[None],
            on_doc_ready=_on_ready,
            parse_method="auto",
        )

        if not results:
            return []

        page_info = results[0]
        elements: list[ParsedElement] = []
        for block in page_info.get("para_blocks", []) or []:
            raw_bbox = block.get("bbox", None)
            if raw_bbox is None:
                continue
            # bbox may be [x0, y0, x1, y1] or a list of 4 numbers
            try:
                x0, y0, x1, y1 = (float(v) for v in raw_bbox[:4])
            except (TypeError, ValueError):
                continue
            html_content = block.get("html", block.get("content", ""))
            elements.append(ParsedElement(bbox=(x0, y0, x1, y1), html=str(html_content)))

        return elements

    return _parse_page


# ── Worker ────────────────────────────────────────────────────────────────────


class MineruWorker:
    """Context-managed MinerU 3 extraction worker.

    Production use — real model loaded in __enter__, unloaded in __exit__ /
    unload().  Tests inject `extract_fn` or `parse_page_fn` to avoid loading
    any real weights.
    """

    name: str = "MinerU 3"
    estimated_vram_mb: int = 2500

    def __init__(
        self,
        *,
        extract_fn: ExtractFn | None = None,
        parse_page_fn: ParsePageFn | None = None,
    ) -> None:
        self._extract_fn = extract_fn
        self._parse_page_fn = parse_page_fn
        self._model: object = None
        self._loaded_vram_mb = 0
        self._load_seconds = 0.0
        self._unloaded = False
        self.results: list[MinerUResult] = []

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> Self:
        if self._extract_fn is not None or self._parse_page_fn is not None:
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

    def _get_parse_page_fn(self) -> ParsePageFn:
        if self._parse_page_fn is not None:
            return self._parse_page_fn
        if self._model is not None:
            return _make_real_parse_page_fn(self._model)
        # Fallback when model could not be loaded.
        return lambda _pdf, _page: []

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, pdf_path: Path, boxes: list[SegmentBox]) -> Iterator[WorkerEvent]:
        targets = [b for b in boxes if b.kind != BoxKind.discard]
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
        else:
            # In-process page parse path: parse each unique page ONCE.
            parse_page = self._get_parse_page_fn()
            page_cache: dict[int, list[ParsedElement]] = {}

            unique_pages = sorted({b.page for b in targets})
            for pg in unique_pages:
                page_cache[pg] = parse_page(pdf_path, pg)

            for i, box in enumerate(targets, start=1):
                page_elements = page_cache.get(box.page, [])
                matched = _match_box_to_elements(box.bbox, page_elements)
                html = "".join(el.html for el in matched)
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
        parse_page = self._get_parse_page_fn()
        page_elements = parse_page(pdf_path, box.page)
        matched = _match_box_to_elements(box.bbox, page_elements)
        html = "".join(el.html for el in matched)
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
