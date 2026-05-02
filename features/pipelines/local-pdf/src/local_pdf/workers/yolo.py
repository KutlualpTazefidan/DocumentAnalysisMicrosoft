"""DocLayout-YOLO segmentation worker.

`YoloWorker` is a context-managed model worker. `__enter__` loads weights,
`run(pdf_path)` is a generator yielding `WorkerEvent`s and accumulating
`SegmentBox` results into `self.boxes`, `unload()` yields the
ModelUnloading / ModelUnloaded pair and frees VRAM. Tests inject a fake
`predict_fn` to bypass the real model load.
"""

from __future__ import annotations

import gc
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple, Self

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

YOLO_CLASS_TO_BOX_KIND: dict[str, BoxKind] = {
    "title": BoxKind.heading,
    "plain text": BoxKind.paragraph,
    "figure": BoxKind.figure,
    "figure_caption": BoxKind.caption,
    "table": BoxKind.table,
    "table_caption": BoxKind.caption,
    "table_footnote": BoxKind.caption,
    "list": BoxKind.list_item,
    "formula": BoxKind.formula,
    "formula_caption": BoxKind.caption,
    "abandon": BoxKind.auxiliary,
}


class YOLOPredictedBox(NamedTuple):
    class_name: str
    bbox: tuple[float, float, float, float]
    confidence: float


class YOLOPagePrediction(NamedTuple):
    page: int
    width: int
    height: int
    boxes: list[YOLOPredictedBox]


PredictFn = Callable[[Path], list[YOLOPagePrediction]]


def make_box_id(page: int, index: int) -> str:
    return f"p{page}-b{index}"


def _default_predict(pdf_path: Path) -> list[YOLOPagePrediction]:
    """Real DocLayout-YOLO inference. Lazy-imports the heavy deps."""
    import io
    import os

    import pdfplumber
    from doclayout_yolo import YOLOv10
    from PIL import Image

    weights = os.environ.get("LOCAL_PDF_YOLO_WEIGHTS")
    if not weights:
        raise RuntimeError("LOCAL_PDF_YOLO_WEIGHTS env var not set")

    model = YOLOv10(weights)
    out: list[YOLOPagePrediction] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            im = page.to_image(resolution=288).original
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            img = Image.open(io.BytesIO(buf.getvalue()))
            res = model.predict(img, imgsz=1024, conf=0.2)[0]
            preds: list[YOLOPredictedBox] = []
            for cls_id, box, conf in zip(
                res.boxes.cls.tolist(),
                res.boxes.xyxy.tolist(),
                res.boxes.conf.tolist(),
                strict=True,
            ):
                name = res.names[int(cls_id)]
                preds.append(
                    YOLOPredictedBox(class_name=name, bbox=tuple(box), confidence=float(conf))
                )
            out.append(YOLOPagePrediction(page=i, width=im.width, height=im.height, boxes=preds))
    return out


class YoloWorker:
    """Context-managed DocLayout-YOLO segmentation worker."""

    name: str = "DocLayout-YOLO"
    estimated_vram_mb: int = 700

    def __init__(self, weights: Path, *, predict_fn: PredictFn | None = None) -> None:
        self._weights = weights
        self._predict_fn = predict_fn
        self._loaded_vram_mb = 0
        self._load_seconds = 0.0
        self._unloaded = False
        self.boxes: list[SegmentBox] = []

    def __enter__(self) -> Self:
        # Test mode bypass — no real load.
        if self._predict_fn is not None:
            self._loaded_vram_mb = 0
            self._load_seconds = 0.0
            return self

        before = _vram_used_mb()
        t0 = time.monotonic()
        # Production load path — only the import-side-effect of YOLOv10 here;
        # the actual predict happens inside `_default_predict`. We still emit
        # measured VRAM and load_seconds.
        from doclayout_yolo import YOLOv10  # noqa: F401  (warm-up import)

        self._load_seconds = time.monotonic() - t0
        self._loaded_vram_mb = max(0, _vram_used_mb() - before)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        # Safety net: if user forgot to call unload(), free here without
        # emitting events (events can't be yielded from __exit__).
        if self._unloaded:
            return
        self._free_vram()
        self._unloaded = True

    def _free_vram(self) -> None:
        gc.collect()
        try:
            torch = _import_torch()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def run(
        self,
        pdf_path: Path,
        start_page: int | None = None,
        end_page: int | None = None,
    ) -> Iterator[WorkerEvent]:
        """Segment *pdf_path*, optionally restricting to pages [start_page, end_page].

        Page numbers are 1-based and inclusive.  When both are None the full
        document is processed (original behaviour).
        """
        yield ModelLoadingEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            source=str(self._weights),
            vram_estimate_mb=self.estimated_vram_mb,
        )
        yield ModelLoadedEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            vram_actual_mb=self._loaded_vram_mb,
            load_seconds=self._load_seconds,
        )

        run_t0 = time.monotonic()
        fn = self._predict_fn or _default_predict
        all_pages = fn(pdf_path)
        # Filter to requested range (1-based, inclusive on both ends).
        if start_page is not None or end_page is not None:
            lo = start_page if start_page is not None else 1
            hi = end_page if end_page is not None else len(all_pages)
            pages = [p for p in all_pages if lo <= p.page <= hi]
        else:
            pages = all_pages
        total_pages = len(pages)
        eta = EtaCalculator()
        self.boxes = []
        for page_idx, page_pred in enumerate(pages, start=1):
            for idx, b in enumerate(page_pred.boxes):
                kind = YOLO_CLASS_TO_BOX_KIND.get(b.class_name, BoxKind.paragraph)
                self.boxes.append(
                    SegmentBox(
                        box_id=make_box_id(page_pred.page, idx),
                        page=page_pred.page,
                        bbox=b.bbox,
                        kind=kind,
                        confidence=b.confidence,
                        reading_order=idx,
                    )
                )
            eta.observe(page_idx, time.monotonic())
            eta_seconds, throughput = eta.estimate(total=total_pages)
            yield WorkProgressEvent(
                model=self.name,
                timestamp_ms=now_ms(),
                stage="page",
                current=page_idx,
                total=total_pages,
                eta_seconds=eta_seconds,
                throughput_per_sec=throughput,
                vram_current_mb=_vram_used_mb(),
            )

        yield WorkCompleteEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            total_seconds=time.monotonic() - run_t0,
            items_processed=len(self.boxes),
            output_summary={"pages": total_pages, "boxes": len(self.boxes)},
        )

    def unload(self) -> Iterator[WorkerEvent]:
        if self._unloaded:
            return
        yield ModelUnloadingEvent(model=self.name, timestamp_ms=now_ms())
        before = _vram_used_mb()
        self._free_vram()
        freed = max(0, before - _vram_used_mb())
        self._unloaded = True
        yield ModelUnloadedEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            vram_freed_mb=freed,
        )
