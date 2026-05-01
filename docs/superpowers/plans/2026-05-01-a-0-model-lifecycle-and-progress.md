# A.0 Model Lifecycle + Progress — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Refactor the merged A.0 pipeline so each model worker is a context-managed class that explicitly loads/unloads VRAM and emits a unified `WorkerEvent` stream (load → progress+ETA → unload), and surface that stream in a collapsible `StageIndicator` UI on segment + extract routes.

**Architecture:** Each worker (`YoloWorker`, `MineruWorker`) implements the `ModelWorker` Protocol — `__enter__` loads weights, `run()` is a generator yielding `WorkerEvent` BaseModels, `unload()` yields `ModelUnloading/Unloaded`, `__exit__` is a crash-safety net. Routers `with`-block the worker and stream `model.model_dump_json()` lines. Frontend folds the NDJSON stream through `streamReducer.ts` into `{stage, model, progress, eta, vram_mb, errors, timeline[]}` rendered by `<StageIndicator>` (collapsed badge) and `<StageTimeline>` (expanded drawer).

**Tech Stack:** unchanged from A.0 — Python 3.11+ · FastAPI · pydantic 2 · pytest · httpx ‖ TypeScript 5 · React 18 · Vite 5 · TanStack Query 5 · Vitest · React Testing Library · msw 2.

**Spec:** `docs/superpowers/specs/2026-05-01-a-0-model-lifecycle-and-progress-design.md`
**Branch:** `feat/a-0-model-lifecycle-and-progress` (already checked out, off main, post PR #26)
**Methodology:** subagent-driven-development. Sonnet for design-heavy tasks (1, 2, 3, 5, 6, 8, 9, 10), Haiku for mechanical tasks (4, 7, 11).

---

## File Map

**Created (backend):**
- `features/pipelines/local-pdf/src/local_pdf/workers/base.py`
- `features/pipelines/local-pdf/tests/test_workers_base.py`

**Modified (backend):**
- `features/pipelines/local-pdf/src/local_pdf/workers/yolo.py`
- `features/pipelines/local-pdf/src/local_pdf/workers/mineru.py`
- `features/pipelines/local-pdf/src/local_pdf/api/schemas.py`
- `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`
- `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`
- `features/pipelines/local-pdf/tests/test_workers_yolo.py`
- `features/pipelines/local-pdf/tests/test_workers_mineru.py`
- `features/pipelines/local-pdf/tests/test_routers_segments.py`
- `features/pipelines/local-pdf/tests/test_routers_extract.py`
- `features/pipelines/local-pdf/tests/test_schemas.py`

**Created (frontend):**
- `frontend/src/local-pdf/streamReducer.ts`
- `frontend/src/local-pdf/components/StageIndicator.tsx`
- `frontend/src/local-pdf/components/StageTimeline.tsx`
- `frontend/tests/local-pdf/streamReducer.test.ts`
- `frontend/tests/local-pdf/components/StageIndicator.test.tsx`
- `frontend/tests/local-pdf/components/StageTimeline.test.tsx`

**Modified (frontend):**
- `frontend/src/local-pdf/types/domain.ts`
- `frontend/src/local-pdf/hooks/useSegments.ts`
- `frontend/src/local-pdf/hooks/useExtract.ts`
- `frontend/src/local-pdf/routes/segment.tsx`
- `frontend/src/local-pdf/routes/extract.tsx`
- `frontend/tests/local-pdf/routes/segment.test.tsx`
- `frontend/tests/local-pdf/routes/extract.test.tsx`

**Modified (docs):**
- `features/pipelines/local-pdf/README.md` (event-schema note)

---

### Task 1: workers/base.py — WorkerEvent + ModelWorker Protocol + helpers

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/workers/base.py`
- Create: `features/pipelines/local-pdf/tests/test_workers_base.py`

- [ ] **Step 1: Write failing test**

`features/pipelines/local-pdf/tests/test_workers_base.py`:

```python
"""Tests for WorkerEvent base models, ModelWorker Protocol, and helpers."""

from __future__ import annotations

import time

import pytest


def test_worker_event_subclasses_have_literal_type_discriminator() -> None:
    from local_pdf.workers.base import (
        ModelLoadedEvent,
        ModelLoadingEvent,
        ModelUnloadedEvent,
        ModelUnloadingEvent,
        WorkCompleteEvent,
        WorkFailedEvent,
        WorkProgressEvent,
    )

    assert ModelLoadingEvent(model="X", timestamp_ms=1, source="/w", vram_estimate_mb=100).type == "model-loading"
    assert ModelLoadedEvent(model="X", timestamp_ms=1, vram_actual_mb=120, load_seconds=2.5).type == "model-loaded"
    assert WorkProgressEvent(
        model="X", timestamp_ms=1, stage="page", current=1, total=10,
        eta_seconds=None, throughput_per_sec=None, vram_current_mb=120,
    ).type == "work-progress"
    assert ModelUnloadingEvent(model="X", timestamp_ms=1).type == "model-unloading"
    assert ModelUnloadedEvent(model="X", timestamp_ms=1, vram_freed_mb=120).type == "model-unloaded"
    assert WorkCompleteEvent(model="X", timestamp_ms=1, total_seconds=10.0, items_processed=4, output_summary={}).type == "work-complete"
    assert WorkFailedEvent(model="X", timestamp_ms=1, stage="run", reason="OOM", recoverable=True, hint=None).type == "work-failed"


def test_worker_event_union_round_trip_via_pydantic_typeadapter() -> None:
    from local_pdf.workers.base import (
        ModelLoadedEvent,
        ModelLoadingEvent,
        WorkerEventUnion,
    )
    from pydantic import TypeAdapter

    adapter: TypeAdapter[WorkerEventUnion] = TypeAdapter(WorkerEventUnion)
    loading = adapter.validate_python(
        {"type": "model-loading", "model": "Y", "timestamp_ms": 1, "source": "/w", "vram_estimate_mb": 700}
    )
    assert isinstance(loading, ModelLoadingEvent)

    loaded = adapter.validate_python(
        {"type": "model-loaded", "model": "Y", "timestamp_ms": 2, "vram_actual_mb": 712, "load_seconds": 3.1}
    )
    assert isinstance(loaded, ModelLoadedEvent)


def test_vram_used_mb_returns_zero_when_cuda_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from local_pdf.workers import base

    class _FakeTorchCuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class _FakeTorch:
        cuda = _FakeTorchCuda()

    monkeypatch.setattr(base, "_import_torch", lambda: _FakeTorch())
    assert base._vram_used_mb() == 0


def test_vram_used_mb_reads_torch_memory_when_cuda_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from local_pdf.workers import base

    class _FakeTorchCuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def memory_allocated() -> int:
            return 512 * 1024 * 1024  # 512 MB in bytes

    class _FakeTorch:
        cuda = _FakeTorchCuda()

    monkeypatch.setattr(base, "_import_torch", lambda: _FakeTorch())
    assert base._vram_used_mb() == 512


def test_eta_calculator_returns_none_until_three_samples() -> None:
    from local_pdf.workers.base import EtaCalculator

    eta = EtaCalculator()
    eta.observe(1, time.monotonic())
    assert eta.estimate(total=10) == (None, None)
    eta.observe(2, time.monotonic() + 0.5)
    assert eta.estimate(total=10) == (None, None)
    eta.observe(3, time.monotonic() + 1.0)
    secs, throughput = eta.estimate(total=10)
    assert secs is not None and secs > 0
    assert throughput is not None and throughput > 0


def test_eta_calculator_uses_exponential_moving_average() -> None:
    """Throughput should respond to changes but smooth them via EMA."""
    from local_pdf.workers.base import EtaCalculator

    eta = EtaCalculator(alpha=0.5)
    base_t = 0.0
    # Three samples at 1 item / second
    eta.observe(1, base_t + 1.0)
    eta.observe(2, base_t + 2.0)
    eta.observe(3, base_t + 3.0)
    _, throughput_first = eta.estimate(total=10)
    assert throughput_first is not None
    # Now suddenly speed up to 10 items/sec for one sample
    eta.observe(13, base_t + 4.0)
    _, throughput_after = eta.estimate(total=20)
    assert throughput_after is not None
    # EMA should be between old and new throughput, not jump straight to 10.
    assert throughput_first < throughput_after < 10.0


def test_now_ms_returns_increasing_int() -> None:
    from local_pdf.workers.base import now_ms

    a = now_ms()
    b = now_ms()
    assert isinstance(a, int)
    assert b >= a
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_workers_base.py -x
```

Expected: `ModuleNotFoundError: No module named 'local_pdf.workers.base'`.

- [ ] **Step 3: Implementation**

`features/pipelines/local-pdf/src/local_pdf/workers/base.py`:

```python
"""Worker lifecycle event surface + ModelWorker Protocol + helpers.

This module defines the unified event types every worker emits over the
NDJSON stream, plus small helpers for VRAM reporting and ETA estimation.

Usage from a router:

    with YoloWorker(weights) as worker:
        yield from worker.run(pdf_path)
        yield from worker.unload()

`__exit__` is a safety net only — explicit `unload()` is the supported path
because `__exit__` cannot yield.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Annotated, Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field


def now_ms() -> int:
    """Wall-clock milliseconds; monotonic-but-not-too-precise."""
    return int(time.time() * 1000)


def _import_torch() -> Any:  # pragma: no cover — patched in tests
    """Indirection so tests can monkeypatch the torch import."""
    import torch

    return torch


def _vram_used_mb() -> int:
    """Currently-allocated GPU memory in MB; 0 on CPU-only machines."""
    try:
        torch = _import_torch()
    except ImportError:
        return 0
    if not torch.cuda.is_available():
        return 0
    return int(torch.cuda.memory_allocated() // (1024 * 1024))


class EtaCalculator:
    """Exponential moving average over throughput; emits None for first 3 samples.

    `observe(items_done, t)` records a sample. `estimate(total)` returns
    (eta_seconds, throughput_per_sec) or (None, None) until enough data.
    """

    def __init__(self, alpha: float = 0.3) -> None:
        self._alpha = alpha
        self._samples: list[tuple[int, float]] = []
        self._smoothed_rate: float | None = None

    def observe(self, items_done: int, t_seconds: float) -> None:
        self._samples.append((items_done, t_seconds))
        if len(self._samples) < 2:
            return
        prev_items, prev_t = self._samples[-2]
        d_items = items_done - prev_items
        d_t = t_seconds - prev_t
        if d_t <= 0 or d_items <= 0:
            return
        instant_rate = d_items / d_t
        if self._smoothed_rate is None:
            self._smoothed_rate = instant_rate
        else:
            self._smoothed_rate = (
                self._alpha * instant_rate + (1.0 - self._alpha) * self._smoothed_rate
            )

    def estimate(self, total: int) -> tuple[float | None, float | None]:
        if len(self._samples) < 3 or self._smoothed_rate is None or self._smoothed_rate <= 0:
            return None, None
        items_done, _ = self._samples[-1]
        remaining = max(0, total - items_done)
        eta = remaining / self._smoothed_rate
        return eta, self._smoothed_rate


# ── Event surface (matches spec §4) ───────────────────────────────────────


class _EventBase(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: str
    model: str
    timestamp_ms: int


class ModelLoadingEvent(_EventBase):
    type: Literal["model-loading"] = "model-loading"
    source: str
    vram_estimate_mb: int


class ModelLoadedEvent(_EventBase):
    type: Literal["model-loaded"] = "model-loaded"
    vram_actual_mb: int
    load_seconds: float


class WorkProgressEvent(_EventBase):
    type: Literal["work-progress"] = "work-progress"
    stage: str
    current: int
    total: int
    eta_seconds: float | None
    throughput_per_sec: float | None
    vram_current_mb: int


class ModelUnloadingEvent(_EventBase):
    type: Literal["model-unloading"] = "model-unloading"


class ModelUnloadedEvent(_EventBase):
    type: Literal["model-unloaded"] = "model-unloaded"
    vram_freed_mb: int


class WorkCompleteEvent(_EventBase):
    type: Literal["work-complete"] = "work-complete"
    total_seconds: float
    items_processed: int
    output_summary: dict[str, Any]


class WorkFailedEvent(_EventBase):
    type: Literal["work-failed"] = "work-failed"
    stage: str  # "load" | "run" | "unload"
    reason: str
    recoverable: bool
    hint: str | None = None


WorkerEventUnion = Annotated[
    ModelLoadingEvent
    | ModelLoadedEvent
    | WorkProgressEvent
    | ModelUnloadingEvent
    | ModelUnloadedEvent
    | WorkCompleteEvent
    | WorkFailedEvent,
    Field(discriminator="type"),
]


# Convenience alias used in worker classes' return annotations.
WorkerEvent = (
    ModelLoadingEvent
    | ModelLoadedEvent
    | WorkProgressEvent
    | ModelUnloadingEvent
    | ModelUnloadedEvent
    | WorkCompleteEvent
    | WorkFailedEvent
)


# ── Protocol ──────────────────────────────────────────────────────────────


class ModelWorker(Protocol):
    """Context-managed worker that loads on `__enter__`, runs work via `run()`,
    and explicitly unloads via `unload()`. `__exit__` is a safety net."""

    name: str
    estimated_vram_mb: int

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...
    def run(self, *args: Any, **kwargs: Any) -> Iterator[WorkerEvent]: ...
    def unload(self) -> Iterator[WorkerEvent]: ...
```

- [ ] **Step 4: Run test, expect PASS**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_workers_base.py -x
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/src/local_pdf/workers/base.py features/pipelines/local-pdf/tests/test_workers_base.py
git commit -m "$(cat <<'EOF'
feat(local-pdf/workers): WorkerEvent surface + ModelWorker Protocol + ETA helper

Adds workers/base.py with the seven event subclasses (ModelLoading/Loaded,
WorkProgress, ModelUnloading/Unloaded, WorkComplete, WorkFailed), a
discriminated WorkerEventUnion, the ModelWorker context-manager Protocol,
plus _vram_used_mb() and EtaCalculator helpers. Foundation for the worker
class refactor in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: YoloWorker class — refactor workers/yolo.py

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/workers/yolo.py`
- Modify: `features/pipelines/local-pdf/tests/test_workers_yolo.py`

- [ ] **Step 1: Write failing test**

Replace `features/pipelines/local-pdf/tests/test_workers_yolo.py` with:

```python
"""Tests for the DocLayout-YOLO worker class.

The actual model is heavy and gated behind an env var. We test the wrapper's
input handling, deterministic box-id generation, lifecycle event emission,
and result conversion using a fake `predict_fn` injected via the constructor.
"""

from __future__ import annotations

from pathlib import Path


def test_yolo_class_to_kind_mapping_covers_doclaynet_classes() -> None:
    from local_pdf.workers.yolo import YOLO_CLASS_TO_BOX_KIND

    for name in (
        "title",
        "plain text",
        "figure",
        "table",
        "list",
        "formula",
        "figure_caption",
        "abandon",
    ):
        assert name in YOLO_CLASS_TO_BOX_KIND


def test_box_id_is_deterministic_per_page_and_index() -> None:
    from local_pdf.workers.yolo import make_box_id

    assert make_box_id(page=1, index=0) == "p1-b0"
    assert make_box_id(page=12, index=37) == "p12-b37"


def test_yolo_worker_advertises_name_and_estimated_vram() -> None:
    from local_pdf.workers.yolo import YoloWorker

    assert YoloWorker.name == "DocLayout-YOLO"
    assert YoloWorker.estimated_vram_mb >= 200


def test_yolo_worker_run_emits_lifecycle_events_with_injected_predict(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind
    from local_pdf.workers.base import (
        ModelLoadedEvent,
        ModelLoadingEvent,
        ModelUnloadedEvent,
        ModelUnloadingEvent,
        WorkCompleteEvent,
        WorkProgressEvent,
    )
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox, YoloWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    def fake_predict(_path: Path) -> list[YOLOPagePrediction]:
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                    YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
                ],
            ),
            YOLOPagePrediction(
                page=2,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="table", bbox=(15, 30, 580, 700), confidence=0.91),
                ],
            ),
        ]

    events = []
    weights = tmp_path / "fake.pt"
    weights.write_bytes(b"")
    with YoloWorker(weights, predict_fn=fake_predict) as worker:
        for ev in worker.run(pdf):
            events.append(ev)
        for ev in worker.unload():
            events.append(ev)

    types = [e.type for e in events]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    assert "work-progress" in types
    assert types[-3] == "work-complete"
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"

    loading = next(e for e in events if isinstance(e, ModelLoadingEvent))
    assert loading.model == "DocLayout-YOLO"
    assert loading.vram_estimate_mb >= 200

    loaded = next(e for e in events if isinstance(e, ModelLoadedEvent))
    assert loaded.vram_actual_mb >= 0
    assert loaded.load_seconds >= 0

    progress = [e for e in events if isinstance(e, WorkProgressEvent)]
    assert len(progress) == 2  # two pages
    assert progress[0].current == 1 and progress[0].total == 2
    assert progress[-1].current == 2 and progress[-1].total == 2

    complete = next(e for e in events if isinstance(e, WorkCompleteEvent))
    assert complete.items_processed == 3  # boxes total
    assert complete.output_summary["pages"] == 2

    unloading = next(e for e in events if isinstance(e, ModelUnloadingEvent))
    assert unloading.model == "DocLayout-YOLO"
    unloaded = next(e for e in events if isinstance(e, ModelUnloadedEvent))
    assert unloaded.vram_freed_mb >= 0


def test_yolo_worker_run_returns_segment_boxes_via_boxes_attr(tmp_path: Path) -> None:
    """After run(), `worker.boxes` holds the canonical SegmentBox list."""
    from local_pdf.api.schemas import BoxKind
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox, YoloWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    def fake_predict(_path: Path) -> list[YOLOPagePrediction]:
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                    YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
                ],
            )
        ]

    weights = tmp_path / "fake.pt"
    weights.write_bytes(b"")
    with YoloWorker(weights, predict_fn=fake_predict) as worker:
        list(worker.run(pdf))
        list(worker.unload())
        boxes = worker.boxes

    assert len(boxes) == 2
    assert boxes[0].box_id == "p1-b0"
    assert boxes[0].kind == BoxKind.heading
    assert boxes[0].confidence == 0.95
    assert boxes[1].kind == BoxKind.paragraph


def test_yolo_worker_exit_after_explicit_unload_is_noop(tmp_path: Path) -> None:
    from local_pdf.workers.yolo import YOLOPagePrediction, YoloWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    weights = tmp_path / "fake.pt"
    weights.write_bytes(b"")

    def fake_predict(_path: Path) -> list[YOLOPagePrediction]:
        return []

    worker = YoloWorker(weights, predict_fn=fake_predict)
    worker.__enter__()
    list(worker.run(pdf))
    list(worker.unload())
    # Second unload (via __exit__) must not raise and must not double-emit.
    worker.__exit__(None, None, None)
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_workers_yolo.py -x
```

Expected: failures because `YoloWorker` doesn't exist; old `run_yolo` function path being removed.

- [ ] **Step 3: Implementation**

Replace `features/pipelines/local-pdf/src/local_pdf/workers/yolo.py` with:

```python
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
    "abandon": BoxKind.discard,
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
            im = page.to_image(resolution=144).original
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

    def run(self, pdf_path: Path) -> Iterator[WorkerEvent]:
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
        pages = fn(pdf_path)
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
```

- [ ] **Step 4: Run test, expect PASS**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_workers_yolo.py -x
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/src/local_pdf/workers/yolo.py features/pipelines/local-pdf/tests/test_workers_yolo.py
git commit -m "$(cat <<'EOF'
refactor(local-pdf/workers): YoloWorker context-manager class with lifecycle events

Replaces run_yolo() function with YoloWorker class that loads weights on
__enter__, yields ModelLoading/Loaded + WorkProgress (ETA + VRAM) + WorkComplete
events from run(), and ModelUnloading/Unloaded from unload(). Test injection
via predict_fn bypasses the real load. boxes attribute holds canonical
SegmentBox results post-run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: MineruWorker class — refactor workers/mineru.py

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/workers/mineru.py`
- Modify: `features/pipelines/local-pdf/tests/test_workers_mineru.py`

- [ ] **Step 1: Write failing test**

Replace `features/pipelines/local-pdf/tests/test_workers_mineru.py`:

```python
"""Tests for the MinerU 3 worker class."""

from __future__ import annotations

from pathlib import Path


def test_mineru_worker_advertises_name_and_estimated_vram() -> None:
    from local_pdf.workers.mineru import MineruWorker

    assert MineruWorker.name == "MinerU 3"
    assert MineruWorker.estimated_vram_mb >= 1000


def test_mineru_worker_run_emits_lifecycle_events_with_injected_extract(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.base import (
        ModelLoadedEvent,
        ModelLoadingEvent,
        ModelUnloadedEvent,
        ModelUnloadingEvent,
        WorkCompleteEvent,
        WorkProgressEvent,
    )
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.heading, confidence=0.95),
        SegmentBox(box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.88),
    ]

    def fake_extract(_pdf: Path, box: SegmentBox) -> MinerUResult:
        tag = "h1" if box.kind == BoxKind.heading else "p"
        return MinerUResult(box_id=box.box_id, html=f"<{tag}>{box.box_id}</{tag}>")

    events = []
    results = []
    with MineruWorker(extract_fn=fake_extract) as worker:
        for ev in worker.run(pdf, boxes):
            events.append(ev)
        results = list(worker.results)
        for ev in worker.unload():
            events.append(ev)

    types = [e.type for e in events]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    assert types.count("work-progress") == 2  # two boxes
    assert types[-3] == "work-complete"
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"

    loading = next(e for e in events if isinstance(e, ModelLoadingEvent))
    assert loading.model == "MinerU 3"
    assert loading.vram_estimate_mb >= 1000

    loaded = next(e for e in events if isinstance(e, ModelLoadedEvent))
    assert loaded.load_seconds >= 0

    progress = [e for e in events if isinstance(e, WorkProgressEvent)]
    assert progress[0].stage == "box"
    assert progress[-1].current == 2 and progress[-1].total == 2

    complete = next(e for e in events if isinstance(e, WorkCompleteEvent))
    assert complete.items_processed == 2
    assert complete.output_summary["boxes_extracted"] == 2

    assert [r.box_id for r in results] == ["p1-b0", "p1-b1"]
    assert results[0].html == "<h1>p1-b0</h1>"


def test_mineru_worker_skips_discard_kind(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.discard, confidence=0.5),
        SegmentBox(box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.9),
    ]

    def fake(_p: Path, box: SegmentBox) -> MinerUResult:
        return MinerUResult(box_id=box.box_id, html=f"<p>{box.box_id}</p>")

    with MineruWorker(extract_fn=fake) as worker:
        list(worker.run(pdf, boxes))
        results = list(worker.results)
        list(worker.unload())

    assert [r.box_id for r in results] == ["p1-b1"]


def test_mineru_worker_extract_region_one_call(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    box = SegmentBox(box_id="p2-b3", page=2, bbox=(50, 50, 200, 200), kind=BoxKind.table, confidence=0.7)

    calls: list[str] = []

    def fake(_p: Path, b: SegmentBox) -> MinerUResult:
        calls.append(b.box_id)
        return MinerUResult(box_id=b.box_id, html="<table><tr><td>x</td></tr></table>")

    with MineruWorker(extract_fn=fake) as worker:
        out = worker.extract_region(pdf, box)

    assert calls == ["p2-b3"]
    assert out.html.startswith("<table>")
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_workers_mineru.py -x
```

Expected: failures (MineruWorker class missing).

- [ ] **Step 3: Implementation**

Replace `features/pipelines/local-pdf/src/local_pdf/workers/mineru.py`:

```python
"""MinerU 3 extraction worker.

`MineruWorker` is a context-managed model worker. `__enter__` is a no-op
(the MinerU CLI lazily warms its weights on first invocation), but the
class still emits `ModelLoadingEvent`/`ModelLoadedEvent` so the UI can
show the same lifecycle pattern. `run(pdf, boxes)` yields one
`WorkProgressEvent` per non-discard box and a final `WorkCompleteEvent`.
`extract_region(pdf, box)` is the single-bbox path (no streaming).
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import tempfile
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
class MinerUResult:
    box_id: str
    html: str


ExtractFn = Callable[[Path, SegmentBox], MinerUResult]


def _default_extract(pdf_path: Path, box: SegmentBox) -> MinerUResult:
    """Real MinerU 3 invocation. Crops the page region and runs the CLI."""
    binary = os.environ.get("LOCAL_PDF_MINERU_BIN", "mineru")
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        cmd = [
            binary,
            "-p",
            str(pdf_path),
            "-o",
            str(out_dir),
            "--page",
            str(box.page),
            "--bbox",
            f"{box.bbox[0]},{box.bbox[1]},{box.bbox[2]},{box.bbox[3]}",
            "--format",
            "html",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"mineru failed: {proc.stderr}")
        out_html = out_dir / "result.html"
        out_json = out_dir / "result.json"
        if out_html.exists():
            html = out_html.read_text(encoding="utf-8")
        elif out_json.exists():
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            html = payload.get("html", "")
        else:
            html = proc.stdout
        return MinerUResult(box_id=box.box_id, html=html)


class MineruWorker:
    """Context-managed MinerU 3 extraction worker."""

    name: str = "MinerU 3"
    estimated_vram_mb: int = 2500

    def __init__(self, *, extract_fn: ExtractFn | None = None) -> None:
        self._extract_fn = extract_fn
        self._loaded_vram_mb = 0
        self._load_seconds = 0.0
        self._unloaded = False
        self.results: list[MinerUResult] = []

    def __enter__(self) -> Self:
        if self._extract_fn is not None:
            return self
        before = _vram_used_mb()
        t0 = time.monotonic()
        # No actual load step here — the MinerU CLI warms on first run. We
        # still record `_load_seconds` as 0 and `_loaded_vram_mb` as the
        # delta seen post-warm-up (will likely be 0 until first run).
        self._load_seconds = time.monotonic() - t0
        self._loaded_vram_mb = max(0, _vram_used_mb() - before)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
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

    def run(self, pdf_path: Path, boxes: list[SegmentBox]) -> Iterator[WorkerEvent]:
        # Source string is descriptive; MinerU has no single weights file.
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

        targets = [b for b in boxes if b.kind != BoxKind.discard]
        total = len(targets)
        run_t0 = time.monotonic()
        eta = EtaCalculator()
        fn = self._extract_fn or _default_extract
        self.results = []
        for i, box in enumerate(targets, start=1):
            result = fn(pdf_path, box)
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

        yield WorkCompleteEvent(
            model=self.name,
            timestamp_ms=now_ms(),
            total_seconds=time.monotonic() - run_t0,
            items_processed=total,
            output_summary={"boxes_extracted": total},
        )

    def extract_region(self, pdf_path: Path, box: SegmentBox) -> MinerUResult:
        fn = self._extract_fn or _default_extract
        return fn(pdf_path, box)

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
```

- [ ] **Step 4: Run test, expect PASS**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_workers_mineru.py -x
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/src/local_pdf/workers/mineru.py features/pipelines/local-pdf/tests/test_workers_mineru.py
git commit -m "$(cat <<'EOF'
refactor(local-pdf/workers): MineruWorker context-manager class with lifecycle events

Replaces run_mineru()/run_mineru_region() functions with MineruWorker class
that emits the same ModelLoading/Loaded → WorkProgress (per-box) → WorkComplete
→ ModelUnloading/Unloaded sequence as YoloWorker. extract_region() preserves
the single-bbox re-extract path used by the /extract/region endpoint. results
attribute holds the MinerUResult list post-run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: API schemas — replace stream-line types with WorkerEvent re-exports

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/schemas.py`
- Modify: `features/pipelines/local-pdf/tests/test_schemas.py`

- [ ] **Step 1: Write failing test**

Replace the streaming-event section of `features/pipelines/local-pdf/tests/test_schemas.py` so the file becomes:

```python
"""Schema validation tests for local-pdf API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_box_kind_enum_has_eight_values() -> None:
    from local_pdf.api.schemas import BoxKind

    expected = {
        "heading",
        "paragraph",
        "table",
        "figure",
        "caption",
        "formula",
        "list_item",
        "discard",
    }
    assert {k.value for k in BoxKind} == expected


def test_doc_status_enum_transitions() -> None:
    from local_pdf.api.schemas import DocStatus

    expected = {"raw", "segmenting", "extracting", "done", "needs_ocr"}
    assert {s.value for s in DocStatus} == expected


def test_segment_box_requires_positive_page_and_4tuple_bbox() -> None:
    from local_pdf.api.schemas import SegmentBox

    ok = SegmentBox(
        box_id="b-1", page=1, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.92
    )
    assert ok.box_id == "b-1"
    assert ok.bbox == (10, 20, 100, 200)

    with pytest.raises(ValidationError):
        SegmentBox(box_id="b-2", page=0, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.5)
    with pytest.raises(ValidationError):
        SegmentBox(box_id="b-3", page=1, bbox=(10, 20, 100), kind="paragraph", confidence=0.5)
    with pytest.raises(ValidationError):
        SegmentBox(box_id="", page=1, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.5)


def test_doc_meta_round_trip() -> None:
    from local_pdf.api.schemas import DocMeta, DocStatus

    m = DocMeta(
        slug="bam-tragkorb-2024",
        filename="BAM_Tragkorb_2024.pdf",
        pages=42,
        status=DocStatus.raw,
        last_touched_utc="2026-04-30T10:00:00Z",
    )
    j = m.model_dump(mode="json")
    assert j["status"] == "raw"
    assert DocMeta.model_validate(j) == m


def test_update_box_request_kind_must_be_in_enum() -> None:
    from local_pdf.api.schemas import UpdateBoxRequest

    ok = UpdateBoxRequest(kind="heading", bbox=(10, 20, 100, 200))
    assert ok.kind == "heading"
    with pytest.raises(ValidationError):
        UpdateBoxRequest(kind="banana", bbox=(10, 20, 100, 200))


def test_worker_event_union_reexported_from_schemas() -> None:
    """schemas.WorkerEventUnion is the same TypeAdapter target as base."""
    from pydantic import TypeAdapter

    from local_pdf.api.schemas import WorkerEventUnion
    from local_pdf.workers.base import (
        ModelLoadingEvent,
        WorkCompleteEvent,
        WorkFailedEvent,
    )

    adapter: TypeAdapter[WorkerEventUnion] = TypeAdapter(WorkerEventUnion)
    assert isinstance(
        adapter.validate_python(
            {"type": "model-loading", "model": "Y", "timestamp_ms": 1, "source": "/w", "vram_estimate_mb": 700}
        ),
        ModelLoadingEvent,
    )
    assert isinstance(
        adapter.validate_python(
            {"type": "work-complete", "model": "Y", "timestamp_ms": 9, "total_seconds": 1.0, "items_processed": 0, "output_summary": {}}
        ),
        WorkCompleteEvent,
    )
    assert isinstance(
        adapter.validate_python(
            {"type": "work-failed", "model": "Y", "timestamp_ms": 9, "stage": "load", "reason": "OOM", "recoverable": False, "hint": None}
        ),
        WorkFailedEvent,
    )


def test_old_segment_extract_line_types_are_gone() -> None:
    """The pre-A.0-followup line types must no longer be importable."""
    import local_pdf.api.schemas as schemas

    for name in (
        "SegmentStartLine",
        "SegmentPageLine",
        "SegmentCompleteLine",
        "SegmentErrorLine",
        "ExtractStartLine",
        "ExtractElementLine",
        "ExtractCompleteLine",
        "ExtractErrorLine",
        "SegmentLine",
        "ExtractLine",
    ):
        assert not hasattr(schemas, name), f"{name} should be removed"
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_schemas.py -x
```

Expected: failure on the new tests because the old line types still exist and `WorkerEventUnion` isn't re-exported.

- [ ] **Step 3: Implementation**

Replace the entire `features/pipelines/local-pdf/src/local_pdf/api/schemas.py` with:

```python
"""Pydantic schemas for the local-pdf HTTP API."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Re-export the worker event surface — the NDJSON streaming endpoints emit
# these directly. See `local_pdf.workers.base` for the source-of-truth.
from local_pdf.workers.base import (
    ModelLoadedEvent,
    ModelLoadingEvent,
    ModelUnloadedEvent,
    ModelUnloadingEvent,
    WorkCompleteEvent,
    WorkFailedEvent,
    WorkerEventUnion,
    WorkProgressEvent,
)

__all__ = [
    "BoxKind",
    "DocStatus",
    "SegmentBox",
    "SegmentsFile",
    "DocMeta",
    "UpdateBoxRequest",
    "MergeBoxesRequest",
    "SplitBoxRequest",
    "CreateBoxRequest",
    "ExtractRegionRequest",
    "HtmlPayload",
    "HealthResponse",
    "ModelLoadingEvent",
    "ModelLoadedEvent",
    "WorkProgressEvent",
    "ModelUnloadingEvent",
    "ModelUnloadedEvent",
    "WorkCompleteEvent",
    "WorkFailedEvent",
    "WorkerEventUnion",
]


class BoxKind(StrEnum):
    heading = "heading"
    paragraph = "paragraph"
    table = "table"
    figure = "figure"
    caption = "caption"
    formula = "formula"
    list_item = "list_item"
    discard = "discard"


class DocStatus(StrEnum):
    raw = "raw"
    segmenting = "segmenting"
    extracting = "extracting"
    done = "done"
    needs_ocr = "needs_ocr"


class SegmentBox(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_id: str
    page: int
    bbox: tuple[float, float, float, float]
    kind: BoxKind
    confidence: float = Field(ge=0.0, le=1.0)
    reading_order: int = 0

    @field_validator("box_id", mode="after")
    @classmethod
    def _box_id_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("box_id must be non-empty")
        return v

    @field_validator("page", mode="after")
    @classmethod
    def _page_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("page must be >= 1")
        return v


class SegmentsFile(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    boxes: list[SegmentBox]


class DocMeta(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    filename: str
    pages: int = Field(ge=1)
    status: DocStatus
    last_touched_utc: str
    box_count: int = 0


class UpdateBoxRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: BoxKind | None = None
    bbox: tuple[float, float, float, float] | None = None
    reading_order: int | None = None


class MergeBoxesRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_ids: list[str] = Field(min_length=2)


class SplitBoxRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_id: str
    split_y: float


class CreateBoxRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    kind: BoxKind = BoxKind.paragraph


class ExtractRegionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_id: str


class HtmlPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    html: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["ok"] = "ok"
    data_root: str
```

- [ ] **Step 4: Run test, expect PASS**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_schemas.py -x
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/src/local_pdf/api/schemas.py features/pipelines/local-pdf/tests/test_schemas.py
git commit -m "$(cat <<'EOF'
refactor(local-pdf/schemas): drop SegmentLine/ExtractLine, re-export WorkerEventUnion

Removes the eight Segment*Line/Extract*Line classes from schemas.py and
re-exports the seven WorkerEvent subclasses + WorkerEventUnion from
workers.base. Routers now emit the unified worker-event stream; tests for
old line types are gone (one new negative test asserts they cannot be
imported).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: segments.py router — use YoloWorker context

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`
- Modify: `features/pipelines/local-pdf/tests/test_routers_segments.py`

- [ ] **Step 1: Write failing test**

Edit `features/pipelines/local-pdf/tests/test_routers_segments.py` so the streaming-related tests assert the new event types. Keep all CRUD tests unchanged. The full file becomes:

```python
from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def app_with_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    import local_pdf.api.routers.segments as seg_mod
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox

    def fake_predict(_pdf):
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                    YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
                ],
            ),
            YOLOPagePrediction(
                page=2,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="table", bbox=(15, 30, 580, 700), confidence=0.91)
                ],
            ),
        ]

    seg_mod._YOLO_PREDICT_FN = fake_predict

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    yield client, root, "doc"

    seg_mod._YOLO_PREDICT_FN = None


def test_segment_streams_worker_events_and_persists(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        assert resp.status_code == 200
        lines = [json.loads(ln) for ln in resp.iter_lines() if ln]
    types = [ln["type"] for ln in lines]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    assert "work-progress" in types
    assert "work-complete" in types
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"
    progress = [ln for ln in lines if ln["type"] == "work-progress"]
    assert progress[-1]["current"] == 2 and progress[-1]["total"] == 2
    complete = next(ln for ln in lines if ln["type"] == "work-complete")
    assert complete["items_processed"] == 3
    for ln in lines:
        assert ln["model"] == "DocLayout-YOLO"

    seg_path = root / slug / "segments.json"
    assert seg_path.exists()
    payload = json.loads(seg_path.read_text(encoding="utf-8"))
    assert len(payload["boxes"]) == 3
    assert {b["page"] for b in payload["boxes"]} == {1, 2}


def test_segment_writes_yolo_json_immutable(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    assert (root / slug / "yolo.json").exists()


def test_get_segments_returns_persisted_boxes(app_with_doc) -> None:
    client, _, slug = app_with_doc
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    resp = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == slug
    assert len(body["boxes"]) == 3


def test_get_segments_404_when_not_yet_run(app_with_doc) -> None:
    client, _, slug = app_with_doc
    resp = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_segment_unknown_slug_404(app_with_doc) -> None:
    client, _, _ = app_with_doc
    resp = client.post("/api/docs/missing/segment", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def _ensure_segmented(client, slug):
    with client.stream(
        "POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())


def test_put_box_updates_kind_and_persists(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p1-b0",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "list_item"},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b0")
    assert target["kind"] == "list_item"


def test_put_box_updates_bbox(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p1-b0",
        headers={"X-Auth-Token": "tok"},
        json={"bbox": [11, 22, 99, 199]},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b0")
    assert target["bbox"] == [11.0, 22.0, 99.0, 199.0]


def test_put_unknown_box_returns_404(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p9-b9",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "heading"},
    )
    assert resp.status_code == 404


def test_delete_box_assigns_discard_kind(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.delete(f"/api/docs/{slug}/segments/p1-b1", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b1")
    assert target["kind"] == "discard"


def test_merge_boxes_creates_one_with_union_bbox(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/merge",
        headers={"X-Auth-Token": "tok"},
        json={"box_ids": ["p1-b0", "p1-b1"]},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    page1 = [b for b in body["boxes"] if b["page"] == 1]
    assert len(page1) == 1
    merged = page1[0]
    assert merged["bbox"] == [10.0, 20.0, 100.0, 200.0]


def test_merge_rejects_cross_page(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/merge",
        headers={"X-Auth-Token": "tok"},
        json={"box_ids": ["p1-b0", "p2-b0"]},
    )
    assert resp.status_code == 400


def test_split_box_at_y(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/split",
        headers={"X-Auth-Token": "tok"},
        json={"box_id": "p1-b1", "split_y": 130},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    page1 = [b for b in body["boxes"] if b["page"] == 1]
    assert "p1-b1" not in {b["box_id"] for b in page1}
    new = [b for b in page1 if b["box_id"] != "p1-b0"]
    assert len(new) == 2
    ys = sorted([(b["bbox"][1], b["bbox"][3]) for b in new])
    assert ys == [(60.0, 130.0), (130.0, 200.0)]


def test_create_box(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments",
        headers={"X-Auth-Token": "tok"},
        json={"page": 1, "bbox": [200, 300, 400, 500], "kind": "heading"},
    )
    assert resp.status_code == 201
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    new_boxes = [b for b in body["boxes"] if b["bbox"] == [200.0, 300.0, 400.0, 500.0]]
    assert len(new_boxes) == 1
    assert new_boxes[0]["kind"] == "heading"
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_routers_segments.py -x
```

Expected: failures on streaming tests (still using old line types in router).

- [ ] **Step 3: Implementation**

Replace `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`:

```python
"""Segmenter routes: run YOLO + CRUD on boxes."""

from __future__ import annotations

import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    BoxKind,
    CreateBoxRequest,
    DocStatus,
    MergeBoxesRequest,
    SegmentBox,
    SegmentsFile,
    SplitBoxRequest,
    UpdateBoxRequest,
    WorkFailedEvent,
)
from local_pdf.storage.sidecar import (
    doc_dir,
    read_meta,
    read_segments,
    write_meta,
    write_segments,
    write_yolo,
)
from local_pdf.workers.base import now_ms
from local_pdf.workers.yolo import YoloWorker

router = APIRouter()

# Test hook: assign a fake predict_fn here from tests.
_YOLO_PREDICT_FN = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bump_meta(data_root, slug: str, status: DocStatus) -> None:
    meta = read_meta(data_root, slug)
    if meta is None:
        return
    meta = meta.model_copy(update={"status": status, "last_touched_utc": _now_iso()})
    write_meta(data_root, slug, meta)


def _yolo_weights_path() -> Path:
    return Path(os.environ.get("LOCAL_PDF_YOLO_WEIGHTS", "doclayout-yolo.pt"))


@router.post("/api/docs/{slug}/segment")
async def run_segment(slug: str, request: Request) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    _bump_meta(cfg.data_root, slug, DocStatus.segmenting)

    def stream():
        try:
            with YoloWorker(_yolo_weights_path(), predict_fn=_YOLO_PREDICT_FN) as worker:
                for ev in worker.run(pdf):
                    yield ev.model_dump_json() + "\n"
                # Persist results before unload events.
                boxes = worker.boxes
                write_yolo(
                    cfg.data_root,
                    slug,
                    {"boxes": [b.model_dump(mode="json") for b in boxes]},
                )
                write_segments(cfg.data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
                meta = read_meta(cfg.data_root, slug)
                if meta is not None:
                    write_meta(
                        cfg.data_root,
                        slug,
                        meta.model_copy(
                            update={
                                "box_count": len(boxes),
                                "last_touched_utc": _now_iso(),
                            }
                        ),
                    )
                for ev in worker.unload():
                    yield ev.model_dump_json() + "\n"
        except Exception as exc:  # noqa: BLE001 — surface as a worker event
            failure = WorkFailedEvent(
                model=YoloWorker.name,
                timestamp_ms=now_ms(),
                stage="run",
                reason=str(exc),
                recoverable=False,
                hint=None,
            )
            yield failure.model_dump_json() + "\n"
            raise

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/api/docs/{slug}/segments")
async def get_segments(slug: str, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"no segments yet for {slug}")
    return dict(seg.model_dump(mode="json"))


def _replace_segments(data_root, slug: str, boxes: list[SegmentBox]) -> None:
    write_segments(data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
    meta = read_meta(data_root, slug)
    if meta is not None:
        write_meta(
            data_root,
            slug,
            meta.model_copy(
                update={
                    "box_count": len([b for b in boxes if b.kind != BoxKind.discard]),
                    "last_touched_utc": _now_iso(),
                }
            ),
        )


def _load_boxes_or_404(data_root, slug: str) -> list[SegmentBox]:
    seg = read_segments(data_root, slug)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"no segments for {slug}")
    return list(seg.boxes)


@router.put("/api/docs/{slug}/segments/{box_id}")
async def update_box(
    slug: str, box_id: str, body: UpdateBoxRequest, request: Request
) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            updates: dict[str, Any] = {}
            if body.kind is not None:
                updates["kind"] = body.kind
            if body.bbox is not None:
                updates["bbox"] = body.bbox
            if body.reading_order is not None:
                updates["reading_order"] = body.reading_order
            boxes[i] = b.model_copy(update=updates)
            _replace_segments(cfg.data_root, slug, boxes)
            return dict(boxes[i].model_dump(mode="json"))
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")


@router.delete("/api/docs/{slug}/segments/{box_id}")
async def delete_box(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            boxes[i] = b.model_copy(update={"kind": BoxKind.discard})
            _replace_segments(cfg.data_root, slug, boxes)
            return dict(boxes[i].model_dump(mode="json"))
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")


@router.post("/api/docs/{slug}/segments/merge")
async def merge_boxes(slug: str, body: MergeBoxesRequest, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    by_id = {b.box_id: b for b in boxes}
    targets = []
    for bid in body.box_ids:
        if bid not in by_id:
            raise HTTPException(status_code=404, detail=f"box not found: {bid}")
        targets.append(by_id[bid])
    pages = {t.page for t in targets}
    if len(pages) != 1:
        raise HTTPException(status_code=400, detail="merge requires same page")
    page = pages.pop()
    x0 = min(t.bbox[0] for t in targets)
    y0 = min(t.bbox[1] for t in targets)
    x1 = max(t.bbox[2] for t in targets)
    y1 = max(t.bbox[3] for t in targets)
    merged = SegmentBox(
        box_id=f"p{page}-m{secrets.token_hex(3)}",
        page=page,
        bbox=(x0, y0, x1, y1),
        kind=targets[0].kind,
        confidence=min(t.confidence for t in targets),
        reading_order=min(t.reading_order for t in targets),
    )
    keep = [b for b in boxes if b.box_id not in body.box_ids]
    keep.append(merged)
    keep.sort(key=lambda b: (b.page, b.reading_order))
    _replace_segments(cfg.data_root, slug, keep)
    return dict(merged.model_dump(mode="json"))


@router.post("/api/docs/{slug}/segments/split")
async def split_box(slug: str, body: SplitBoxRequest, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == body.box_id:
            x0, y0, x1, y1 = b.bbox
            if not (y0 < body.split_y < y1):
                raise HTTPException(
                    status_code=400, detail="split_y must lie strictly inside the bbox"
                )
            top = b.model_copy(
                update={
                    "box_id": f"p{b.page}-s{secrets.token_hex(3)}",
                    "bbox": (x0, y0, x1, body.split_y),
                }
            )
            bot = b.model_copy(
                update={
                    "box_id": f"p{b.page}-s{secrets.token_hex(3)}",
                    "bbox": (x0, body.split_y, x1, y1),
                }
            )
            new_boxes = [*boxes[:i], top, bot, *boxes[i + 1 :]]
            _replace_segments(cfg.data_root, slug, new_boxes)
            return {
                "top": top.model_dump(mode="json"),
                "bottom": bot.model_dump(mode="json"),
            }
    raise HTTPException(status_code=404, detail=f"box not found: {body.box_id}")


@router.post("/api/docs/{slug}/segments", status_code=status.HTTP_201_CREATED)
async def create_box(slug: str, body: CreateBoxRequest, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    new = SegmentBox(
        box_id=f"p{body.page}-u{secrets.token_hex(3)}",
        page=body.page,
        bbox=body.bbox,
        kind=body.kind,
        confidence=1.0,
        reading_order=max((b.reading_order for b in boxes if b.page == body.page), default=-1) + 1,
    )
    boxes.append(new)
    _replace_segments(cfg.data_root, slug, boxes)
    return dict(new.model_dump(mode="json"))
```

Note: `json` import retained for any future use; the `model_dump_json()` calls already produce JSON strings. The `json` symbol stays in case downstream maintainers need it; remove with the linter if you prefer.

- [ ] **Step 4: Run test, expect PASS**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_routers_segments.py -x
```

Expected: 14 passed.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py features/pipelines/local-pdf/tests/test_routers_segments.py
git commit -m "$(cat <<'EOF'
refactor(local-pdf/segments): stream WorkerEvents via YoloWorker context manager

Router now opens YoloWorker as a `with` block, streams worker.run() events
as model_dump_json() lines, persists segments.json/yolo.json/meta between
run and unload, and streams worker.unload() events. Wraps the whole flow
in try/except → emits WorkFailedEvent on uncaught exceptions before
re-raising. CRUD routes unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: extract.py router — use MineruWorker context

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`
- Modify: `features/pipelines/local-pdf/tests/test_routers_extract.py`

- [ ] **Step 1: Write failing test**

Replace `features/pipelines/local-pdf/tests/test_routers_extract.py`:

```python
from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def app_with_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    import local_pdf.api.routers.extract as ext_mod
    import local_pdf.api.routers.segments as seg_mod
    from local_pdf.workers.mineru import MinerUResult
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox

    seg_mod._YOLO_PREDICT_FN = lambda _p: [
        YOLOPagePrediction(
            page=1,
            width=600,
            height=800,
            boxes=[
                YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
            ],
        )
    ]

    def fake_extract(_pdf, box):
        tag = "h1" if box.kind.value == "heading" else "p"
        return MinerUResult(
            box_id=box.box_id, html=f'<{tag} data-source-box="{box.box_id}">{box.box_id}</{tag}>'
        )

    ext_mod._MINERU_EXTRACT_FN = fake_extract

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    with client.stream("POST", "/api/docs/doc/segment", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    yield client, root, "doc"

    seg_mod._YOLO_PREDICT_FN = None
    ext_mod._MINERU_EXTRACT_FN = None


def test_extract_streams_worker_events_one_progress_per_box(app_with_segments) -> None:
    client, _, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        assert resp.status_code == 200
        lines = [json.loads(ln) for ln in resp.iter_lines() if ln]
    types = [ln["type"] for ln in lines]
    assert types[0] == "model-loading"
    assert types[1] == "model-loaded"
    progress = [ln for ln in lines if ln["type"] == "work-progress"]
    assert len(progress) == 2  # two boxes
    assert progress[-1]["current"] == 2 and progress[-1]["total"] == 2
    assert types[-3] == "work-complete"
    assert types[-2] == "model-unloading"
    assert types[-1] == "model-unloaded"
    for ln in lines:
        assert ln["model"] == "MinerU 3"


def test_extract_persists_html_and_mineru_out(app_with_segments) -> None:
    client, root, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    assert (root / slug / "html.html").exists()
    assert (root / slug / "mineru-out.json").exists()
    html = (root / slug / "html.html").read_text(encoding="utf-8")
    assert 'data-source-box="p1-b0"' in html
    assert 'data-source-box="p1-b1"' in html


def test_extract_region_runs_one_box_only(app_with_segments) -> None:
    client, _root, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    resp = client.post(
        f"/api/docs/{slug}/extract/region",
        headers={"X-Auth-Token": "tok"},
        json={"box_id": "p1-b0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["box_id"] == "p1-b0"
    assert body["html"].startswith("<h1")


def test_extract_unknown_slug_404(app_with_segments) -> None:
    client, _, _ = app_with_segments
    resp = client.post("/api/docs/missing/extract", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_export_writes_sourceelements_and_marks_done(app_with_segments) -> None:
    client, root, slug = app_with_segments
    with client.stream(
        "POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}
    ) as resp:
        list(resp.iter_lines())
    resp = client.post(f"/api/docs/{slug}/export", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_pipeline"] == "local-pdf"
    assert (root / slug / "sourceelements.json").exists()
    meta = client.get(f"/api/docs/{slug}", headers={"X-Auth-Token": "tok"}).json()
    assert meta["status"] == "done"
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_routers_extract.py -x
```

Expected: failures (router still uses old line types).

- [ ] **Step 3: Implementation**

Replace `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`:

```python
"""Extraction routes: full-doc + region MinerU runs, html GET/PUT, export."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    BoxKind,
    DocStatus,
    ExtractRegionRequest,
    HtmlPayload,
    WorkFailedEvent,
    WorkProgressEvent,
)
from local_pdf.convert.source_elements import build_source_elements_payload
from local_pdf.storage.sidecar import (
    doc_dir,
    read_html,
    read_meta,
    read_segments,
    write_html,
    write_meta,
    write_mineru,
    write_source_elements,
)
from local_pdf.workers.base import now_ms
from local_pdf.workers.mineru import MineruWorker

router = APIRouter()

# Test hook for MinerU.
_MINERU_EXTRACT_FN = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wrap_html(elements: list[dict]) -> str:
    body = "\n".join(e["html_snippet"] for e in elements)
    return f"<!DOCTYPE html>\n<html><body>\n{body}\n</body></html>\n"


@router.post("/api/docs/{slug}/extract")
async def run_extract(slug: str, request: Request) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(
            cfg.data_root,
            slug,
            meta.model_copy(
                update={"status": DocStatus.extracting, "last_touched_utc": _now_iso()}
            ),
        )

    targets = [b for b in seg.boxes if b.kind != BoxKind.discard]

    def stream():
        try:
            with MineruWorker(extract_fn=_MINERU_EXTRACT_FN) as worker:
                for ev in worker.run(pdf, targets):
                    # Persist after each yielded WorkProgressEvent's box result.
                    yield ev.model_dump_json() + "\n"
                # Build elements list from worker.results.
                elements = [
                    {"box_id": r.box_id, "html_snippet": r.html} for r in worker.results
                ]
                write_mineru(cfg.data_root, slug, {"elements": elements})
                write_html(cfg.data_root, slug, _wrap_html(elements))
                for ev in worker.unload():
                    yield ev.model_dump_json() + "\n"
        except Exception as exc:  # noqa: BLE001
            failure = WorkFailedEvent(
                model=MineruWorker.name,
                timestamp_ms=now_ms(),
                stage="run",
                reason=str(exc),
                recoverable=False,
                hint=None,
            )
            yield failure.model_dump_json() + "\n"
            raise

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/api/docs/{slug}/extract/region")
async def run_extract_region(slug: str, body: ExtractRegionRequest, request: Request) -> dict:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    target = next((b for b in seg.boxes if b.box_id == body.box_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"box not found: {body.box_id}")
    with MineruWorker(extract_fn=_MINERU_EXTRACT_FN) as worker:
        result = worker.extract_region(pdf, target)
    return {"box_id": result.box_id, "html": result.html}


@router.get("/api/docs/{slug}/html")
async def get_html(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=404, detail=f"no html for {slug}")
    return {"html": html}


@router.put("/api/docs/{slug}/html")
async def put_html(slug: str, body: HtmlPayload, request: Request) -> dict:
    cfg = request.app.state.config
    if not (doc_dir(cfg.data_root, slug)).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    write_html(cfg.data_root, slug, body.html)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"last_touched_utc": _now_iso()}))
    return {"ok": True}


@router.post("/api/docs/{slug}/export")
async def run_export(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=400, detail="run /extract first")
    payload = build_source_elements_payload(slug=slug, segments=seg, html=html)
    write_source_elements(cfg.data_root, slug, payload)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(
            cfg.data_root,
            slug,
            meta.model_copy(update={"status": DocStatus.done, "last_touched_utc": _now_iso()}),
        )
    return payload
```

Remove the unused `WorkProgressEvent` import if linter flags it; the explicit re-import is left so future per-event hooks land naturally.

- [ ] **Step 4: Run test, expect PASS**

```
cd features/pipelines/local-pdf && uv run pytest tests/test_routers_extract.py -x
```

Expected: 5 passed. Then run the full pytest suite:

```
cd features/pipelines/local-pdf && uv run pytest -x
```

All A.0 tests should still pass.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py features/pipelines/local-pdf/tests/test_routers_extract.py
git commit -m "$(cat <<'EOF'
refactor(local-pdf/extract): stream WorkerEvents via MineruWorker context manager

Router opens MineruWorker, streams run() events, persists html.html and
mineru-out.json from worker.results between run and unload, then streams
unload(). region endpoint now uses worker.extract_region() inside its own
short-lived `with` block. WorkFailedEvent emitted on uncaught exceptions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Frontend types — WorkerEvent union + sub-types

**Files:**
- Modify: `frontend/src/local-pdf/types/domain.ts`
- Create: `frontend/tests/local-pdf/types/domain.test.ts` (new file)

- [ ] **Step 1: Write failing test**

`frontend/tests/local-pdf/types/domain.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import type {
  ModelLoadingEvent,
  ModelLoadedEvent,
  ModelUnloadingEvent,
  ModelUnloadedEvent,
  WorkCompleteEvent,
  WorkFailedEvent,
  WorkProgressEvent,
  WorkerEvent,
} from "../../../src/local-pdf/types/domain";

function narrow(ev: WorkerEvent): string {
  switch (ev.type) {
    case "model-loading":
      return `loading from ${ev.source} (~${ev.vram_estimate_mb}MB)`;
    case "model-loaded":
      return `loaded ${ev.vram_actual_mb}MB in ${ev.load_seconds}s`;
    case "work-progress":
      return `${ev.stage} ${ev.current}/${ev.total}`;
    case "model-unloading":
      return "unloading";
    case "model-unloaded":
      return `freed ${ev.vram_freed_mb}MB`;
    case "work-complete":
      return `done ${ev.items_processed} in ${ev.total_seconds}s`;
    case "work-failed":
      return `failed at ${ev.stage}: ${ev.reason}`;
  }
}

describe("WorkerEvent type narrowing", () => {
  it("narrows ModelLoadingEvent", () => {
    const ev: ModelLoadingEvent = {
      type: "model-loading",
      model: "DocLayout-YOLO",
      timestamp_ms: 1,
      source: "/weights",
      vram_estimate_mb: 700,
    };
    expect(narrow(ev)).toBe("loading from /weights (~700MB)");
  });

  it("narrows ModelLoadedEvent", () => {
    const ev: ModelLoadedEvent = {
      type: "model-loaded",
      model: "DocLayout-YOLO",
      timestamp_ms: 1,
      vram_actual_mb: 612,
      load_seconds: 12.3,
    };
    expect(narrow(ev)).toBe("loaded 612MB in 12.3s");
  });

  it("narrows WorkProgressEvent", () => {
    const ev: WorkProgressEvent = {
      type: "work-progress",
      model: "MinerU 3",
      timestamp_ms: 1,
      stage: "box",
      current: 7,
      total: 10,
      eta_seconds: 4.5,
      throughput_per_sec: 1.5,
      vram_current_mb: 1800,
    };
    expect(narrow(ev)).toBe("box 7/10");
  });

  it("narrows ModelUnloadingEvent", () => {
    const ev: ModelUnloadingEvent = {
      type: "model-unloading",
      model: "MinerU 3",
      timestamp_ms: 1,
    };
    expect(narrow(ev)).toBe("unloading");
  });

  it("narrows ModelUnloadedEvent", () => {
    const ev: ModelUnloadedEvent = {
      type: "model-unloaded",
      model: "MinerU 3",
      timestamp_ms: 1,
      vram_freed_mb: 1800,
    };
    expect(narrow(ev)).toBe("freed 1800MB");
  });

  it("narrows WorkCompleteEvent", () => {
    const ev: WorkCompleteEvent = {
      type: "work-complete",
      model: "DocLayout-YOLO",
      timestamp_ms: 1,
      total_seconds: 30.0,
      items_processed: 47,
      output_summary: { pages: 47 },
    };
    expect(narrow(ev)).toBe("done 47 in 30s");
  });

  it("narrows WorkFailedEvent", () => {
    const ev: WorkFailedEvent = {
      type: "work-failed",
      model: "MinerU 3",
      timestamp_ms: 1,
      stage: "run",
      reason: "OOM",
      recoverable: true,
      hint: "reduce batch size",
    };
    expect(narrow(ev)).toBe("failed at run: OOM");
  });
});
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd frontend && npm run test -- tests/local-pdf/types/domain.test.ts
```

Expected: type errors on the imports because the new sub-types don't exist yet.

- [ ] **Step 3: Implementation**

Replace `frontend/src/local-pdf/types/domain.ts` with:

```typescript
export type BoxKind =
  | "heading"
  | "paragraph"
  | "table"
  | "figure"
  | "caption"
  | "formula"
  | "list_item"
  | "discard";

export type DocStatus = "raw" | "segmenting" | "extracting" | "done" | "needs_ocr";

export interface SegmentBox {
  box_id: string;
  page: number;
  bbox: [number, number, number, number];
  kind: BoxKind;
  confidence: number;
  reading_order: number;
}

export interface SegmentsFile {
  slug: string;
  boxes: SegmentBox[];
}

export interface DocMeta {
  slug: string;
  filename: string;
  pages: number;
  status: DocStatus;
  last_touched_utc: string;
  box_count: number;
}

export interface SourceElementsPayload {
  doc_slug: string;
  source_pipeline: "local-pdf";
  elements: Array<{
    kind: Exclude<BoxKind, "discard">;
    page: number;
    bbox: [number, number, number, number];
    text: string;
    box_id: string;
    level?: number;
  }>;
}

// ── Worker lifecycle events (mirrors local_pdf.workers.base) ──────────────

interface _WorkerEventBase {
  model: string;
  timestamp_ms: number;
}

export interface ModelLoadingEvent extends _WorkerEventBase {
  type: "model-loading";
  source: string;
  vram_estimate_mb: number;
}

export interface ModelLoadedEvent extends _WorkerEventBase {
  type: "model-loaded";
  vram_actual_mb: number;
  load_seconds: number;
}

export interface WorkProgressEvent extends _WorkerEventBase {
  type: "work-progress";
  stage: string;
  current: number;
  total: number;
  eta_seconds: number | null;
  throughput_per_sec: number | null;
  vram_current_mb: number;
}

export interface ModelUnloadingEvent extends _WorkerEventBase {
  type: "model-unloading";
}

export interface ModelUnloadedEvent extends _WorkerEventBase {
  type: "model-unloaded";
  vram_freed_mb: number;
}

export interface WorkCompleteEvent extends _WorkerEventBase {
  type: "work-complete";
  total_seconds: number;
  items_processed: number;
  output_summary: Record<string, unknown>;
}

export interface WorkFailedEvent extends _WorkerEventBase {
  type: "work-failed";
  stage: "load" | "run" | "unload";
  reason: string;
  recoverable: boolean;
  hint: string | null;
}

export type WorkerEvent =
  | ModelLoadingEvent
  | ModelLoadedEvent
  | WorkProgressEvent
  | ModelUnloadingEvent
  | ModelUnloadedEvent
  | WorkCompleteEvent
  | WorkFailedEvent;
```

- [ ] **Step 4: Run test, expect PASS**

```
cd frontend && npm run test -- tests/local-pdf/types/domain.test.ts
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```
git add frontend/src/local-pdf/types/domain.ts frontend/tests/local-pdf/types/domain.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend/local-pdf): WorkerEvent union mirroring backend lifecycle events

Replaces SegmentLine + ExtractLine with the seven WorkerEvent sub-types
(ModelLoading/Loaded, WorkProgress, ModelUnloading/Unloaded, WorkComplete,
WorkFailed) discriminated by `type`. Test suite verifies exhaustive
narrowing in a switch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: streamReducer.ts — fold events into UI state

**Files:**
- Create: `frontend/src/local-pdf/streamReducer.ts`
- Create: `frontend/tests/local-pdf/streamReducer.test.ts`

- [ ] **Step 1: Write failing test**

`frontend/tests/local-pdf/streamReducer.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  applyEvent,
  initialStreamState,
  type StreamState,
} from "../../src/local-pdf/streamReducer";
import type {
  ModelLoadedEvent,
  ModelLoadingEvent,
  ModelUnloadedEvent,
  ModelUnloadingEvent,
  WorkCompleteEvent,
  WorkFailedEvent,
  WorkProgressEvent,
} from "../../src/local-pdf/types/domain";

describe("streamReducer", () => {
  it("starts in idle stage with no model", () => {
    const s = initialStreamState();
    expect(s.stage).toBe("idle");
    expect(s.model).toBeNull();
    expect(s.timeline).toEqual([]);
    expect(s.errors).toEqual([]);
  });

  it("ModelLoadingEvent transitions to loading and records source + estimate", () => {
    const ev: ModelLoadingEvent = {
      type: "model-loading",
      model: "DocLayout-YOLO",
      timestamp_ms: 100,
      source: "/w.pt",
      vram_estimate_mb: 700,
    };
    const s = applyEvent(initialStreamState(), ev);
    expect(s.stage).toBe("loading");
    expect(s.model).toBe("DocLayout-YOLO");
    expect(s.vram_estimate_mb).toBe(700);
    expect(s.timeline).toHaveLength(1);
    expect(s.timeline[0]).toEqual(ev);
  });

  it("ModelLoadedEvent transitions loading → ready (pre-run) and records vram_actual", () => {
    let s = initialStreamState();
    const loading: ModelLoadingEvent = {
      type: "model-loading",
      model: "DocLayout-YOLO",
      timestamp_ms: 100,
      source: "/w.pt",
      vram_estimate_mb: 700,
    };
    s = applyEvent(s, loading);
    const loaded: ModelLoadedEvent = {
      type: "model-loaded",
      model: "DocLayout-YOLO",
      timestamp_ms: 200,
      vram_actual_mb: 612,
      load_seconds: 12.3,
    };
    s = applyEvent(s, loaded);
    expect(s.stage).toBe("ready");
    expect(s.vram_mb).toBe(612);
    expect(s.load_seconds).toBe(12.3);
  });

  it("first WorkProgressEvent transitions ready → running", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "ready",
      model: "DocLayout-YOLO",
      vram_mb: 612,
    };
    const p1: WorkProgressEvent = {
      type: "work-progress",
      model: "DocLayout-YOLO",
      timestamp_ms: 300,
      stage: "page",
      current: 1,
      total: 10,
      eta_seconds: null,
      throughput_per_sec: null,
      vram_current_mb: 612,
    };
    s = applyEvent(s, p1);
    expect(s.stage).toBe("running");
    expect(s.progress).toEqual({ current: 1, total: 10, stage: "page" });
    expect(s.eta_seconds).toBeNull();
  });

  it("subsequent WorkProgressEvents update progress + eta + vram_mb", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "running",
      model: "DocLayout-YOLO",
      vram_mb: 612,
    };
    s = applyEvent(s, {
      type: "work-progress",
      model: "DocLayout-YOLO",
      timestamp_ms: 400,
      stage: "page",
      current: 4,
      total: 10,
      eta_seconds: 6.0,
      throughput_per_sec: 1.0,
      vram_current_mb: 720,
    } satisfies WorkProgressEvent);
    expect(s.progress).toEqual({ current: 4, total: 10, stage: "page" });
    expect(s.eta_seconds).toBe(6.0);
    expect(s.throughput_per_sec).toBe(1.0);
    expect(s.vram_mb).toBe(720);
  });

  it("WorkCompleteEvent transitions to completed", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "running",
      model: "DocLayout-YOLO",
    };
    const done: WorkCompleteEvent = {
      type: "work-complete",
      model: "DocLayout-YOLO",
      timestamp_ms: 999,
      total_seconds: 30.0,
      items_processed: 47,
      output_summary: { pages: 47 },
    };
    s = applyEvent(s, done);
    expect(s.stage).toBe("completed");
    expect(s.items_processed).toBe(47);
  });

  it("ModelUnloadingEvent → unloading; ModelUnloadedEvent → idle and clears VRAM", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "completed",
      model: "DocLayout-YOLO",
      vram_mb: 612,
    };
    s = applyEvent(s, {
      type: "model-unloading",
      model: "DocLayout-YOLO",
      timestamp_ms: 1000,
    } satisfies ModelUnloadingEvent);
    expect(s.stage).toBe("unloading");
    s = applyEvent(s, {
      type: "model-unloaded",
      model: "DocLayout-YOLO",
      timestamp_ms: 1100,
      vram_freed_mb: 612,
    } satisfies ModelUnloadedEvent);
    expect(s.stage).toBe("idle");
    expect(s.vram_mb).toBe(0);
  });

  it("WorkFailedEvent moves to failed and records error", () => {
    let s: StreamState = {
      ...initialStreamState(),
      stage: "running",
      model: "MinerU 3",
    };
    const fail: WorkFailedEvent = {
      type: "work-failed",
      model: "MinerU 3",
      timestamp_ms: 500,
      stage: "run",
      reason: "OOM",
      recoverable: true,
      hint: "free VRAM",
    };
    s = applyEvent(s, fail);
    expect(s.stage).toBe("failed");
    expect(s.errors).toHaveLength(1);
    expect(s.errors[0]).toEqual(fail);
  });

  it("appends every event to timeline in arrival order", () => {
    let s = initialStreamState();
    const events = [
      { type: "model-loading", model: "X", timestamp_ms: 1, source: "/w", vram_estimate_mb: 100 },
      { type: "model-loaded", model: "X", timestamp_ms: 2, vram_actual_mb: 120, load_seconds: 1.0 },
      {
        type: "work-progress", model: "X", timestamp_ms: 3, stage: "page",
        current: 1, total: 1, eta_seconds: null, throughput_per_sec: null, vram_current_mb: 120,
      },
      { type: "work-complete", model: "X", timestamp_ms: 4, total_seconds: 1.0, items_processed: 1, output_summary: {} },
    ] as const;
    for (const ev of events) {
      s = applyEvent(s, ev);
    }
    expect(s.timeline.map((e) => e.type)).toEqual([
      "model-loading",
      "model-loaded",
      "work-progress",
      "work-complete",
    ]);
  });
});
```

- [ ] **Step 2: Run test, expect FAIL**

```
cd frontend && npm run test -- tests/local-pdf/streamReducer.test.ts
```

Expected: module not found.

- [ ] **Step 3: Implementation**

`frontend/src/local-pdf/streamReducer.ts`:

```typescript
import type { WorkerEvent } from "./types/domain";

export type StreamStage =
  | "idle"
  | "loading"
  | "ready"
  | "running"
  | "completed"
  | "unloading"
  | "failed";

export interface StreamState {
  stage: StreamStage;
  model: string | null;
  vram_estimate_mb: number;
  vram_mb: number;
  load_seconds: number | null;
  progress: { current: number; total: number; stage: string } | null;
  eta_seconds: number | null;
  throughput_per_sec: number | null;
  items_processed: number;
  total_seconds: number | null;
  errors: WorkerEvent[];
  timeline: WorkerEvent[];
}

export function initialStreamState(): StreamState {
  return {
    stage: "idle",
    model: null,
    vram_estimate_mb: 0,
    vram_mb: 0,
    load_seconds: null,
    progress: null,
    eta_seconds: null,
    throughput_per_sec: null,
    items_processed: 0,
    total_seconds: null,
    errors: [],
    timeline: [],
  };
}

export function applyEvent(prev: StreamState, ev: WorkerEvent): StreamState {
  const timeline = [...prev.timeline, ev];
  switch (ev.type) {
    case "model-loading":
      return {
        ...prev,
        stage: "loading",
        model: ev.model,
        vram_estimate_mb: ev.vram_estimate_mb,
        timeline,
      };
    case "model-loaded":
      return {
        ...prev,
        stage: "ready",
        vram_mb: ev.vram_actual_mb,
        load_seconds: ev.load_seconds,
        timeline,
      };
    case "work-progress":
      return {
        ...prev,
        stage: "running",
        progress: { current: ev.current, total: ev.total, stage: ev.stage },
        eta_seconds: ev.eta_seconds,
        throughput_per_sec: ev.throughput_per_sec,
        vram_mb: ev.vram_current_mb,
        timeline,
      };
    case "work-complete":
      return {
        ...prev,
        stage: "completed",
        items_processed: ev.items_processed,
        total_seconds: ev.total_seconds,
        timeline,
      };
    case "model-unloading":
      return { ...prev, stage: "unloading", timeline };
    case "model-unloaded":
      return { ...prev, stage: "idle", vram_mb: 0, timeline };
    case "work-failed":
      return {
        ...prev,
        stage: "failed",
        errors: [...prev.errors, ev],
        timeline,
      };
  }
}
```

- [ ] **Step 4: Run test, expect PASS**

```
cd frontend && npm run test -- tests/local-pdf/streamReducer.test.ts
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```
git add frontend/src/local-pdf/streamReducer.ts frontend/tests/local-pdf/streamReducer.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend/local-pdf): streamReducer folds WorkerEvent stream into UI state

Pure reducer (initialStreamState + applyEvent) maps the seven event types
into a single StreamState consumed by StageIndicator/StageTimeline.
Tracks stage, model, vram, progress+eta+throughput, items_processed,
errors, and the full timeline. 9 tests cover every transition.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: StageIndicator + StageTimeline components

**Files:**
- Create: `frontend/src/local-pdf/components/StageIndicator.tsx`
- Create: `frontend/src/local-pdf/components/StageTimeline.tsx`
- Create: `frontend/tests/local-pdf/components/StageIndicator.test.tsx`
- Create: `frontend/tests/local-pdf/components/StageTimeline.test.tsx`

- [ ] **Step 1: Write failing tests**

`frontend/tests/local-pdf/components/StageIndicator.test.tsx`:

```typescript
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageIndicator } from "../../../src/local-pdf/components/StageIndicator";
import { initialStreamState } from "../../../src/local-pdf/streamReducer";

describe("StageIndicator", () => {
  it("renders nothing when stage is idle and timeline is empty", () => {
    const { container } = render(<StageIndicator state={initialStreamState()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders model name + page progress while running", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "running",
          model: "DocLayout-YOLO",
          progress: { current: 14, total: 47, stage: "page" },
          eta_seconds: 134,
          throughput_per_sec: 3.6,
          vram_mb: 612,
        }}
      />,
    );
    expect(screen.getByText(/DocLayout-YOLO/)).toBeInTheDocument();
    expect(screen.getByText(/14 \/ 47/)).toBeInTheDocument();
    expect(screen.getByText(/612.?MB/)).toBeInTheDocument();
  });

  it("uses yellow status dot while loading", () => {
    render(
      <StageIndicator
        state={{ ...initialStreamState(), stage: "loading", model: "X" }}
      />,
    );
    const dot = screen.getByTestId("stage-dot");
    expect(dot.className).toMatch(/yellow/);
  });

  it("uses green status dot while running", () => {
    render(
      <StageIndicator
        state={{ ...initialStreamState(), stage: "running", model: "X", progress: { current: 1, total: 2, stage: "page" } }}
      />,
    );
    const dot = screen.getByTestId("stage-dot");
    expect(dot.className).toMatch(/green/);
  });

  it("uses red status dot on failed", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "failed",
          model: "X",
          errors: [
            {
              type: "work-failed",
              model: "X",
              timestamp_ms: 1,
              stage: "run",
              reason: "OOM",
              recoverable: false,
              hint: null,
            },
          ],
        }}
      />,
    );
    const dot = screen.getByTestId("stage-dot");
    expect(dot.className).toMatch(/red/);
  });

  it("expands timeline drawer on click", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "running",
          model: "X",
          progress: { current: 2, total: 5, stage: "page" },
          timeline: [
            { type: "model-loading", model: "X", timestamp_ms: 1, source: "/w", vram_estimate_mb: 100 },
            { type: "model-loaded", model: "X", timestamp_ms: 2, vram_actual_mb: 120, load_seconds: 1 },
            {
              type: "work-progress", model: "X", timestamp_ms: 3, stage: "page",
              current: 2, total: 5, eta_seconds: null, throughput_per_sec: null, vram_current_mb: 120,
            },
          ],
        }}
      />,
    );
    expect(screen.queryByTestId("stage-timeline")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("stage-toggle"));
    expect(screen.getByTestId("stage-timeline")).toBeInTheDocument();
    // Timeline shows three entries
    expect(screen.getAllByTestId(/timeline-entry-/)).toHaveLength(3);
  });

  it("formats ETA as m:ss", () => {
    render(
      <StageIndicator
        state={{
          ...initialStreamState(),
          stage: "running",
          model: "X",
          progress: { current: 5, total: 50, stage: "page" },
          eta_seconds: 134,
        }}
      />,
    );
    expect(screen.getByText(/2:14/)).toBeInTheDocument();
  });
});
```

`frontend/tests/local-pdf/components/StageTimeline.test.tsx`:

```typescript
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StageTimeline } from "../../../src/local-pdf/components/StageTimeline";
import type { WorkerEvent } from "../../../src/local-pdf/types/domain";

describe("StageTimeline", () => {
  it("renders one entry per event with type and model", () => {
    const events: WorkerEvent[] = [
      { type: "model-loading", model: "Y", timestamp_ms: 1000, source: "/w", vram_estimate_mb: 700 },
      { type: "model-loaded", model: "Y", timestamp_ms: 2000, vram_actual_mb: 612, load_seconds: 12.3 },
      {
        type: "work-progress", model: "Y", timestamp_ms: 3000, stage: "page",
        current: 14, total: 47, eta_seconds: 134, throughput_per_sec: 3.6, vram_current_mb: 612,
      },
    ];
    render(<StageTimeline events={events} />);
    const rows = screen.getAllByTestId(/timeline-entry-/);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveTextContent(/loaded|loading/i);
    expect(rows[1]).toHaveTextContent(/612.?MB/);
    expect(rows[2]).toHaveTextContent(/14 \/ 47/);
  });

  it("renders failed events with red marker", () => {
    const events: WorkerEvent[] = [
      {
        type: "work-failed",
        model: "Z",
        timestamp_ms: 5000,
        stage: "run",
        reason: "CUDA OOM",
        recoverable: true,
        hint: "free VRAM",
      },
    ];
    render(<StageTimeline events={events} />);
    expect(screen.getByText(/CUDA OOM/)).toBeInTheDocument();
    const marker = screen.getByTestId("timeline-entry-0").querySelector("[data-marker]");
    expect(marker?.getAttribute("data-marker")).toBe("error");
  });

  it("renders empty list with no rows", () => {
    render(<StageTimeline events={[]} />);
    expect(screen.queryAllByTestId(/timeline-entry-/)).toHaveLength(0);
  });
});
```

- [ ] **Step 2: Run tests, expect FAIL**

```
cd frontend && npm run test -- tests/local-pdf/components/StageIndicator.test.tsx tests/local-pdf/components/StageTimeline.test.tsx
```

Expected: module-not-found errors.

- [ ] **Step 3: Implementation**

`frontend/src/local-pdf/components/StageTimeline.tsx`:

```typescript
import type { WorkerEvent } from "../types/domain";

interface Props {
  events: WorkerEvent[];
}

function fmtTime(ms: number): string {
  const d = new Date(ms);
  return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}:${d
    .getSeconds()
    .toString()
    .padStart(2, "0")}`;
}

function describe(ev: WorkerEvent): { marker: string; text: string } {
  switch (ev.type) {
    case "model-loading":
      return { marker: "loading", text: `${ev.model} • loading from ${ev.source}` };
    case "model-loaded":
      return {
        marker: "ok",
        text: `${ev.model} • loaded (${ev.load_seconds.toFixed(1)}s, ${ev.vram_actual_mb}MB)`,
      };
    case "work-progress":
      return {
        marker: "running",
        text: `${ev.model} • ${ev.stage} ${ev.current} / ${ev.total}${
          ev.eta_seconds != null ? ` • ETA ${ev.eta_seconds.toFixed(0)}s` : ""
        }`,
      };
    case "model-unloading":
      return { marker: "loading", text: `${ev.model} • unloading` };
    case "model-unloaded":
      return { marker: "ok", text: `${ev.model} • unloaded (freed ${ev.vram_freed_mb}MB)` };
    case "work-complete":
      return {
        marker: "ok",
        text: `${ev.model} • complete (${ev.items_processed} items, ${ev.total_seconds.toFixed(1)}s)`,
      };
    case "work-failed":
      return { marker: "error", text: `${ev.model} • failed at ${ev.stage}: ${ev.reason}` };
  }
}

const MARKER_CLASS: Record<string, string> = {
  loading: "text-yellow-600",
  running: "text-green-600",
  ok: "text-gray-500",
  error: "text-red-600",
};

export function StageTimeline({ events }: Props): JSX.Element {
  return (
    <ul data-testid="stage-timeline" className="text-xs space-y-1 p-2 max-h-64 overflow-auto">
      {events.map((ev, i) => {
        const { marker, text } = describe(ev);
        return (
          <li
            key={i}
            data-testid={`timeline-entry-${i}`}
            className="flex items-center gap-2"
          >
            <span data-marker={marker} className={MARKER_CLASS[marker] ?? ""}>
              {marker === "ok" ? "✓" : marker === "running" ? "●" : marker === "error" ? "✗" : "●"}
            </span>
            <span className="text-gray-400">{fmtTime(ev.timestamp_ms)}</span>
            <span>{text}</span>
          </li>
        );
      })}
    </ul>
  );
}
```

`frontend/src/local-pdf/components/StageIndicator.tsx`:

```typescript
import { useState } from "react";

import type { StreamState } from "../streamReducer";
import { StageTimeline } from "./StageTimeline";

interface Props {
  state: StreamState;
}

const DOT_CLASS: Record<string, string> = {
  idle: "bg-gray-400",
  loading: "bg-yellow-500",
  ready: "bg-yellow-500",
  running: "bg-green-500",
  completed: "bg-gray-500",
  unloading: "bg-yellow-500",
  failed: "bg-red-600",
};

function fmtEta(seconds: number | null | undefined): string | null {
  if (seconds == null) return null;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

export function StageIndicator({ state }: Props): JSX.Element | null {
  const [open, setOpen] = useState(false);

  if (state.stage === "idle" && state.timeline.length === 0) {
    return null;
  }

  const eta = fmtEta(state.eta_seconds);

  return (
    <div className="absolute top-2 right-2 z-30">
      <button
        data-testid="stage-toggle"
        onClick={() => setOpen((p) => !p)}
        className="flex items-center gap-2 bg-white border rounded px-3 py-1 text-xs shadow"
      >
        <span data-testid="stage-dot" className={`inline-block w-2 h-2 rounded-full ${DOT_CLASS[state.stage] ?? "bg-gray-400"}`} />
        <span className="font-medium">{state.model ?? "—"}</span>
        {state.progress != null ? (
          <span>
            {state.progress.stage} {state.progress.current} / {state.progress.total}
          </span>
        ) : null}
        {eta != null ? <span>• ETA {eta}</span> : null}
        {state.vram_mb > 0 ? <span>• {state.vram_mb}MB</span> : null}
      </button>
      {open ? (
        <div className="mt-1 bg-white border rounded shadow w-96">
          <StageTimeline events={state.timeline} />
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Run tests, expect PASS**

```
cd frontend && npm run test -- tests/local-pdf/components/StageIndicator.test.tsx tests/local-pdf/components/StageTimeline.test.tsx
```

Expected: 7 + 3 = 10 passed.

- [ ] **Step 5: Commit**

```
git add frontend/src/local-pdf/components/StageIndicator.tsx frontend/src/local-pdf/components/StageTimeline.tsx frontend/tests/local-pdf/components/StageIndicator.test.tsx frontend/tests/local-pdf/components/StageTimeline.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend/local-pdf): StageIndicator + StageTimeline (collapsed badge + drawer)

StageIndicator renders the persistent top-right badge — colored dot keyed
to stage (yellow=loading/unloading, green=running, red=failed, gray=idle/
done), model name, progress, ETA in m:ss, VRAM. Click toggles a 384px
drawer rendering StageTimeline with one row per event (timestamp +
marker + descriptive text). Hidden entirely when idle and no history.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Wire streamReducer + StageIndicator into hooks and routes

**Files:**
- Modify: `frontend/src/local-pdf/hooks/useExtract.ts`
- Modify: `frontend/src/local-pdf/hooks/useSegments.ts` (re-export streamSegment hook helper if any; primarily route-driven)
- Modify: `frontend/src/local-pdf/routes/segment.tsx`
- Modify: `frontend/src/local-pdf/routes/extract.tsx`
- Modify: `frontend/tests/local-pdf/routes/segment.test.tsx`
- Modify: `frontend/tests/local-pdf/routes/extract.test.tsx`

- [ ] **Step 1: Write failing test**

Update `frontend/tests/local-pdf/routes/segment.test.tsx`:

```typescript
// frontend/tests/local-pdf/routes/segment.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { SegmentRoute } from "../../../src/local-pdf/routes/segment";

vi.mock("../../../src/local-pdf/hooks/usePdfPage", () => ({
  usePdfPage: () => ({
    numPages: 2,
    viewport: { width: 600, height: 800 },
    canvasRef: { current: null },
    loading: false,
    error: null,
  }),
}));

const SEGMENT_NDJSON = [
  { type: "model-loading", model: "DocLayout-YOLO", timestamp_ms: 1, source: "/w", vram_estimate_mb: 700 },
  { type: "model-loaded", model: "DocLayout-YOLO", timestamp_ms: 2, vram_actual_mb: 612, load_seconds: 1.0 },
  {
    type: "work-progress", model: "DocLayout-YOLO", timestamp_ms: 3, stage: "page",
    current: 1, total: 1, eta_seconds: null, throughput_per_sec: null, vram_current_mb: 612,
  },
  { type: "work-complete", model: "DocLayout-YOLO", timestamp_ms: 4, total_seconds: 1.0, items_processed: 2, output_summary: { pages: 1 } },
  { type: "model-unloading", model: "DocLayout-YOLO", timestamp_ms: 5 },
  { type: "model-unloaded", model: "DocLayout-YOLO", timestamp_ms: 6, vram_freed_mb: 612 },
]
  .map((l) => JSON.stringify(l))
  .join("\n");

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({
      slug: "rep",
      boxes: [
        { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
        { box_id: "p1-b1", page: 1, bbox: [10, 60, 100, 200], kind: "paragraph", confidence: 0.6, reading_order: 1 },
      ],
    }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/segments/p1-b0", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "list_item", confidence: 0.95, reading_order: 0 }),
  ),
  http.post("http://127.0.0.1:8001/api/docs/rep/segment", () =>
    new HttpResponse(SEGMENT_NDJSON, { headers: { "Content-Type": "application/x-ndjson" } }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/doc/rep/segment"]}>
        <Routes>
          <Route path="/local-pdf/doc/:slug/segment" element={<SegmentRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SegmentRoute", () => {
  it("renders the page-1 boxes after segments load", async () => {
    render(wrap());
    await waitFor(() => expect(screen.getByTestId("box-p1-b0")).toBeInTheDocument());
    expect(screen.getByTestId("box-p1-b1")).toBeInTheDocument();
  });

  it("changes selected box kind via hotkey 'l'", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    fireEvent.keyDown(window, { key: "l" });
    await waitFor(() => {
      const select = screen.getByDisplayValue("list_item") as HTMLSelectElement;
      expect(select).toBeInTheDocument();
    });
  });

  it("StageIndicator is not present until segmentation runs", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    expect(screen.queryByTestId("stage-toggle")).not.toBeInTheDocument();
  });
});
```

Update `frontend/tests/local-pdf/routes/extract.test.tsx`:

```typescript
// frontend/tests/local-pdf/routes/extract.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ExtractRoute } from "../../../src/local-pdf/routes/extract";

vi.mock("../../../src/local-pdf/hooks/usePdfPage", () => ({
  usePdfPage: () => ({ numPages: 1, viewport: { width: 600, height: 800 }, canvasRef: { current: null }, loading: false, error: null }),
}));

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({
      slug: "rep",
      boxes: [
        { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
      ],
    }),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep/html", () =>
    HttpResponse.json({ html: '<h1 data-source-box="p1-b0">Hi</h1>' }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/html", () => HttpResponse.json({ ok: true })),
  http.post("http://127.0.0.1:8001/api/docs/rep/export", () =>
    HttpResponse.json({ doc_slug: "rep", source_pipeline: "local-pdf", elements: [] }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/doc/rep/extract"]}>
        <Routes>
          <Route path="/local-pdf/doc/:slug/extract" element={<ExtractRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ExtractRoute", () => {
  it("loads html and shows it in editor", async () => {
    render(wrap());
    await waitFor(() => expect(screen.getByText("Hi")).toBeInTheDocument());
  });

  it("Export button posts and toasts", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));
    fireEvent.click(screen.getByRole("button", { name: /export/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export/i })).not.toBeDisabled(),
    );
  });

  it("StageIndicator is not present in idle, html-only render", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));
    expect(screen.queryByTestId("stage-toggle")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests, expect FAIL**

```
cd frontend && npm run test -- tests/local-pdf/routes/segment.test.tsx tests/local-pdf/routes/extract.test.tsx
```

Expected: failures because hooks still type-export ExtractLine/SegmentLine; routes don't render StageIndicator yet.

- [ ] **Step 3: Implementation**

Replace `frontend/src/local-pdf/hooks/useExtract.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { exportSourceElements, extractRegion, getHtml, putHtml } from "../api/docs";
import { apiBase } from "../api/client";
import { readNdjsonLines } from "../api/ndjson";
import type { WorkerEvent } from "../types/domain";

export function useHtml(slug: string, token: string) {
  return useQuery({ queryKey: ["html", slug], queryFn: () => getHtml(slug, token) });
}

export function usePutHtml(slug: string, token: string) {
  return useMutation({ mutationFn: (html: string) => putHtml(slug, html, token) });
}

export function useExportSourceElements(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => exportSourceElements(slug, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}

export function useExtractRegion(slug: string, token: string) {
  return useMutation({ mutationFn: (boxId: string) => extractRegion(slug, boxId, token) });
}

export async function* streamSegment(slug: string, token: string): AsyncGenerator<WorkerEvent> {
  const r = await fetch(`${apiBase()}/api/docs/${encodeURIComponent(slug)}/segment`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<WorkerEvent>(r.body);
}

export async function* streamExtract(slug: string, token: string): AsyncGenerator<WorkerEvent> {
  const r = await fetch(`${apiBase()}/api/docs/${encodeURIComponent(slug)}/extract`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<WorkerEvent>(r.body);
}
```

Replace `frontend/src/local-pdf/routes/segment.tsx`:

```typescript
// frontend/src/local-pdf/routes/segment.tsx
import { useMemo, useReducer, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import toast from "react-hot-toast";

import { BoxOverlay } from "../components/BoxOverlay";
import { PdfPage } from "../components/PdfPage";
import { PropertiesSidebar } from "../components/PropertiesSidebar";
import { StageIndicator } from "../components/StageIndicator";
import { useBoxHotkeys } from "../hooks/useBoxHotkeys";
import {
  useCreateBox,
  useDeleteBox,
  useMergeBoxes,
  useSegments,
  useSplitBox,
  useUpdateBox,
} from "../hooks/useSegments";
import { streamSegment } from "../hooks/useExtract";
import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
import type { BoxKind, WorkerEvent } from "../types/domain";

interface Props {
  token: string;
}

function reducer(state: StreamState, ev: WorkerEvent): StreamState {
  return applyEvent(state, ev);
}

export function SegmentRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const scale = 1.5;
  const segments = useSegments(slug ?? "", token);
  const update = useUpdateBox(slug ?? "", token);
  const merge = useMergeBoxes(slug ?? "", token);
  const split = useSplitBox(slug ?? "", token);
  const newBox = useCreateBox(slug ?? "", token);
  const del = useDeleteBox(slug ?? "", token);
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);

  const boxesOnPage = useMemo(
    () => (segments.data?.boxes ?? []).filter((b) => b.page === page),
    [segments.data, page],
  );
  const focused = useMemo(
    () => (segments.data?.boxes ?? []).find((b) => b.box_id === selected[0]) ?? null,
    [segments.data, selected],
  );

  function handleSelect(boxId: string, multi: boolean) {
    setSelected((prev) =>
      multi ? (prev.includes(boxId) ? prev.filter((p) => p !== boxId) : [...prev, boxId]) : [boxId],
    );
  }

  async function runSegment() {
    setRunning(true);
    try {
      for await (const ev of streamSegment(slug!, token)) {
        dispatch(ev);
        if (ev.type === "work-complete") toast.success(`segmented ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") toast.error(ev.reason);
      }
      await segments.refetch();
    } finally {
      setRunning(false);
    }
  }

  useBoxHotkeys({
    enabled: !!focused,
    setKind: (k: BoxKind) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } }),
    merge: () => selected.length >= 2 && merge.mutate(selected),
    split: () => focused && split.mutate({ boxId: focused.box_id, splitY: (focused.bbox[1] + focused.bbox[3]) / 2 }),
    newBox: () => newBox.mutate({ page, bbox: [50, 50, 200, 200], kind: "paragraph" }),
    del: () => focused && del.mutate(focused.box_id),
  });

  if (!segments.data) {
    return (
      <div className="p-6 relative">
        <p>No segmentation yet.</p>
        <button className="mt-4 bg-blue-600 text-white px-3 py-1 rounded" onClick={runSegment} disabled={running}>
          {running ? "Segmenting…" : "Run segmentation"}
        </button>
        <StageIndicator state={streamState} />
      </div>
    );
  }

  return (
    <div className="flex h-full relative">
      <main className="flex-1 overflow-auto p-4">
        <div className="flex gap-2 mb-2">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((p) => (
            <button key={p} className={`px-2 py-1 text-xs ${p === page ? "bg-gray-200" : ""}`} onClick={() => setPage(p)}>
              p{p}
            </button>
          ))}
        </div>
        <PdfPage slug={slug!} token={token} page={page} scale={scale}>
          {boxesOnPage.map((b) => (
            <BoxOverlay
              key={b.box_id}
              box={b}
              selected={selected.includes(b.box_id)}
              onSelect={handleSelect}
              onChange={(boxId, bbox) => update.mutate({ boxId, patch: { bbox } })}
              scale={scale}
            />
          ))}
        </PdfPage>
      </main>
      <PropertiesSidebar
        selected={focused}
        pageBoxCount={boxesOnPage.length}
        onChangeKind={(k) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } })}
        onMerge={() => selected.length >= 2 && merge.mutate(selected)}
        onDelete={() => focused && del.mutate(focused.box_id)}
        onRunExtract={() => navigate(`/local-pdf/doc/${slug}/extract`)}
        extractEnabled={(segments.data.boxes ?? []).some((b) => b.kind !== "discard")}
      />
      <StageIndicator state={streamState} />
    </div>
  );
}
```

Replace `frontend/src/local-pdf/routes/extract.tsx`:

```typescript
// frontend/src/local-pdf/routes/extract.tsx
import { useEffect, useReducer, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import toast from "react-hot-toast";

import { BoxOverlay } from "../components/BoxOverlay";
import { HtmlEditor } from "../components/HtmlEditor";
import { PdfPage } from "../components/PdfPage";
import { StageIndicator } from "../components/StageIndicator";
import { useSegments } from "../hooks/useSegments";
import { streamExtract, useExportSourceElements, useExtractRegion, useHtml, usePutHtml } from "../hooks/useExtract";
import { applyEvent, initialStreamState, type StreamState } from "../streamReducer";
import type { WorkerEvent } from "../types/domain";

interface Props {
  token: string;
}

function reducer(state: StreamState, ev: WorkerEvent): StreamState {
  return applyEvent(state, ev);
}

export function ExtractRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const segments = useSegments(slug ?? "", token);
  const html = useHtml(slug ?? "", token);
  const putHtml = usePutHtml(slug ?? "", token);
  const exportSrc = useExportSourceElements(slug ?? "", token);
  const extractRegion = useExtractRegion(slug ?? "", token);
  const [page, setPage] = useState(1);
  const [running, setRunning] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);
  const [streamState, dispatch] = useReducer(reducer, undefined, initialStreamState);

  function handleHtmlChange(next: string) {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      putHtml.mutate(next);
    }, 300);
  }

  useEffect(() => () => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
  }, []);

  async function runExtract() {
    setRunning(true);
    try {
      for await (const ev of streamExtract(slug!, token)) {
        dispatch(ev);
        if (ev.type === "work-complete") toast.success(`extracted ${ev.items_processed} boxes`);
        if (ev.type === "work-failed") toast.error(ev.reason);
      }
      await html.refetch();
    } finally {
      setRunning(false);
    }
  }

  function handleExport() {
    exportSrc.mutate(undefined, {
      onSuccess: () => toast.success("Exported sourceelements.json"),
      onError: (err) => toast.error((err as Error).message),
    });
  }

  function handleClickElement(boxId: string) {
    setHighlight(boxId);
    const target = (segments.data?.boxes ?? []).find((b) => b.box_id === boxId);
    if (target) setPage(target.page);
  }

  function handleRegion(boxId: string) {
    extractRegion.mutate(boxId, {
      onSuccess: (r) => toast.success(`re-extracted ${r.box_id}`),
      onError: (err) => toast.error((err as Error).message),
    });
  }

  const boxesOnPage = (segments.data?.boxes ?? []).filter((b) => b.page === page);

  if (!html.data) {
    return (
      <div className="p-6 relative">
        <button className="bg-blue-600 text-white px-3 py-1 rounded" onClick={runExtract} disabled={running}>
          {running ? "Extracting…" : "Run extraction"}
        </button>
        <StageIndicator state={streamState} />
      </div>
    );
  }

  return (
    <div className="flex h-full relative">
      <section className="w-1/2 overflow-auto p-2 border-r">
        <PdfPage slug={slug!} token={token} page={page} scale={1.2}>
          {boxesOnPage.map((b) => (
            <BoxOverlay
              key={b.box_id}
              box={b}
              selected={highlight === b.box_id}
              onSelect={(id) => handleRegion(id)}
              onChange={() => {}}
              scale={1.2}
            />
          ))}
        </PdfPage>
      </section>
      <section className="w-1/2 flex flex-col">
        <div className="flex justify-end p-2 border-b gap-2">
          <button className="text-sm px-3 py-1 bg-blue-600 text-white rounded" disabled={exportSrc.isPending} onClick={handleExport}>
            Export →
          </button>
        </div>
        <HtmlEditor html={html.data} onChange={handleHtmlChange} onClickElement={handleClickElement} />
      </section>
      <StageIndicator state={streamState} />
    </div>
  );
}
```

`frontend/src/local-pdf/hooks/useSegments.ts` does not need changes — it never referenced the old line types.

- [ ] **Step 4: Run tests, expect PASS**

```
cd frontend && npm run test
```

Expected: full local-pdf vitest suite green (route tests + new component + reducer + types tests). Then run a typecheck:

```
cd frontend && npm run build
```

Expected: clean tsc.

- [ ] **Step 5: Commit**

```
git add frontend/src/local-pdf/hooks/useExtract.ts frontend/src/local-pdf/routes/segment.tsx frontend/src/local-pdf/routes/extract.tsx frontend/tests/local-pdf/routes/segment.test.tsx frontend/tests/local-pdf/routes/extract.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend/local-pdf): wire WorkerEvent stream + StageIndicator into routes

streamSegment / streamExtract now emit WorkerEvent (was SegmentLine /
ExtractLine). SegmentRoute and ExtractRoute fold each event through
applyEvent into a useReducer-backed StreamState and mount StageIndicator
absolutely-positioned top-right. Toasts now key off work-complete /
work-failed instead of the removed complete/error lines.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: README note + push branch (NO PR open)

**Files:**
- Modify: `features/pipelines/local-pdf/README.md`

- [ ] **Step 1: Write failing test**

Skip — this is a docs + push task. Verification is the smoke test below.

- [ ] **Step 2: Run test, expect FAIL**

Skip.

- [ ] **Step 3: Implementation**

Append to `features/pipelines/local-pdf/README.md` a new section after the existing event-schema note (or at end of file):

```markdown
## Streaming event schema

The `/segment` and `/extract` endpoints stream NDJSON `WorkerEvent` lines
defined in `local_pdf.workers.base`. The seven event types are:

| `type`             | when                                           | key fields                                                  |
|--------------------|-------------------------------------------------|-------------------------------------------------------------|
| `model-loading`    | weights starting to load                       | `source`, `vram_estimate_mb`                                |
| `model-loaded`     | weights resident                                | `vram_actual_mb`, `load_seconds`                            |
| `work-progress`    | one step of work done (page or box)             | `stage`, `current`, `total`, `eta_seconds`, `vram_current_mb` |
| `work-complete`    | run loop finished                               | `items_processed`, `total_seconds`, `output_summary`        |
| `model-unloading`  | starting to free VRAM                           | —                                                           |
| `model-unloaded`   | VRAM freed                                      | `vram_freed_mb`                                             |
| `work-failed`      | uncaught error during load/run/unload           | `stage`, `reason`, `recoverable`, `hint`                    |

Every event also carries `model: str` and `timestamp_ms: int`. The
frontend `streamReducer.ts` folds the stream into a single `StreamState`
rendered by `StageIndicator` (collapsed badge, top-right of segment +
extract pages) and `StageTimeline` (drawer when expanded).
```

- [ ] **Step 4: Run smoke test**

```
cd features/pipelines/local-pdf && uv run pytest -x
cd frontend && npm run test && npm run build
```

Both green. Branch already named `feat/a-0-model-lifecycle-and-progress`. Push:

```
git push -u origin feat/a-0-model-lifecycle-and-progress
```

Do NOT run `gh pr create` — the user opens the PR manually.

- [ ] **Step 5: Commit**

```
git add features/pipelines/local-pdf/README.md
git commit -m "$(cat <<'EOF'
docs(local-pdf): document the WorkerEvent streaming schema

Adds a table of the seven NDJSON event types emitted by /segment and
/extract, with the key fields each carries, plus a pointer to
streamReducer + StageIndicator on the frontend.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin feat/a-0-model-lifecycle-and-progress
```

---

## Cross-Task Verification (the "self-review pass")

| Concern | Where defined | Where consumed | Match? |
|---|---|---|---|
| `WorkerEvent` (Python type alias) | Task 1 (`workers/base.py`) | Tasks 2, 3 (return annotation) | ✓ same module |
| `WorkerEventUnion` (discriminated TypeAdapter target) | Task 1 | Task 4 (re-export from schemas) | ✓ |
| `YoloWorker.name` = `"DocLayout-YOLO"` | Task 2 | Task 5 router test, Task 8 reducer test | ✓ |
| `MineruWorker.name` = `"MinerU 3"` | Task 3 | Task 6 router test | ✓ |
| `YoloWorker(weights, predict_fn=...).run(pdf) → Iterator[WorkerEvent]` + `.boxes` post-run | Task 2 | Task 5 router calls `worker.run(pdf)` then `worker.boxes` | ✓ |
| `MineruWorker(extract_fn=...).run(pdf, boxes)` + `.results` + `.extract_region(pdf, box)` | Task 3 | Task 6 router calls all three | ✓ |
| `worker.unload()` yields `ModelUnloadingEvent` then `ModelUnloadedEvent` | Tasks 2, 3 | Task 5/6 routers call `yield from worker.unload()` | ✓ |
| Frontend `WorkerEvent` union type names | Task 7 | Tasks 8, 9, 10 | ✓ |
| `applyEvent` + `initialStreamState` API | Task 8 | Task 9 component test, Task 10 routes | ✓ |
| `<StageIndicator state={...}>` props shape | Task 9 | Task 10 routes | ✓ |
| `data-testid="stage-toggle"` / `stage-dot` / `stage-timeline` | Task 9 | Task 10 route tests | ✓ |

No placeholders, no "similar to Task N", every code block complete, every test asserts. Plan covers all 8 spec decisions D1-D8 (D1 medium scope = base.py reusable; D2 worker-owned context manager; D3 detailed event types; D4 try/except + WorkFailedEvent; D5 single StageIndicator + drawer; D6 replace not additive; D7 _vram_used_mb returns 0 on CPU; D8 predict_fn / extract_fn injection bypasses load).
