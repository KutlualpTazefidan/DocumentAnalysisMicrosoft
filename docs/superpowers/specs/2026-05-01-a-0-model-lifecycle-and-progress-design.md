# A.0 Model Lifecycle + Progress Visibility — Design Spec

**Phase:** A.0 follow-up (incremental on the merged Local PDF Pipeline)
**Date:** 2026-05-01
**Status:** Spec — proceed directly to writing-plans (user approved as "ship it").

## 1. Goal

Two related problems on the just-merged A.0 stack:

1. **VRAM contention.** `workers/yolo.py` and `workers/mineru.py` load model weights into VRAM and never explicitly release them. PyTorch's CUDA caching keeps weights pinned even after the function returns. Result: when DocLayout-YOLO finishes (~600MB) and MinerU's 1.2B-param VLM tries to load (~2-3GB), they fight for the same GPU. On 8-12GB cards this OOMs.

2. **Progress invisibility.** Backend already emits NDJSON for per-page / per-box progress, but no events for *model loading* or *unloading* — the slowest steps on a fresh run. Frontend renders the count progress but no stage indicator. User sees a spinning UI for 30 seconds during weight-download with no signal that anything is happening.

Solution scope is **medium** (per brainstorming): a model-lifecycle abstraction usable by every current and future worker (Phase B LLM-judge, Phase E span_match), with **worker-owned** lifecycle (no central registry — each worker is its own context manager).

## 2. Decisions Log

| ID | Topic | Decision | Reasoning |
|----|-------|----------|-----------|
| D1 | Scope | Medium — model-lifecycle abstraction reusable across workers, not narrow per-feature fix | Phase B/E will need this; building it once now amortizes |
| D2 | Lifecycle ownership | Worker-owned — each worker is a Python context manager that loads on `__enter__`, unloads on `__exit__` | Pure-function workers stay pure; no shared state; no central registry to debug |
| D3 | Event granularity | Detailed — emit ModelLoading/Loaded/Unloading/Unloaded + per-item progress + ETA + VRAM stats | Per-page ETA is genuinely useful; per-load events fire infrequently so cost is small |
| D4 | OOM handling | Fail-loud during load (no retry); during run, free cache + retry batch with `batch_size//2`, max 3 retries | Load OOM means too-much-other-stuff; can't help. Run OOM is a transient pressure spike, retry with smaller batch is the standard fix. |
| D5 | UI shape | Single `<StageIndicator>` component, top-right of segmenter + extract pages, persistent, click-to-expand for full event log | Compact, doesn't crowd the work surface, expandable when the user wants detail |
| D6 | Event-name compatibility | New events REPLACE the existing `SegmentStart/Page/Complete` and `ExtractStart/Item/Complete` lines (not additive) | Cleaner; the old types weren't documented as a public contract; existing tests update mechanically |
| D7 | CPU fallback | If `torch.cuda.is_available() == False`, workers run on CPU and emit VRAM=0 in events | Don't break dev machines without GPU |
| D8 | Test injection | Workers continue to accept `predict_fn` / `extract_fn` injection — bypasses load/unload entirely in tests | No mocking of CUDA; tests stay fast and machine-independent |

## 3. Worker Contract (the abstraction)

```python
from typing import Protocol, Iterator, Self
from collections.abc import Iterable

class ModelWorker(Protocol):
    """Context-managed worker that loads a model on __enter__, runs work,
    and unloads on __exit__. Subclasses emit lifecycle + progress events
    via the run() generator.
    """
    name: str                    # e.g. "DocLayout-YOLO", "MinerU 2.5"
    estimated_vram_mb: int       # for pre-load UI hint

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

    def run(self, *args, **kwargs) -> Iterator["WorkerEvent"]: ...
```

Concrete worker shape (yolo.py refactor):

```python
class YoloWorker:
    name = "DocLayout-YOLO"
    estimated_vram_mb = 700

    def __init__(self, weights: Path, *, predict_fn=None) -> None:
        self._weights = weights
        self._predict_fn = predict_fn        # test injection point
        self._model = None
        self._loaded_vram_mb = 0

    def __enter__(self) -> "YoloWorker":
        if self._predict_fn is not None:
            return self  # test mode — no real load
        # production load path
        from doclayout_yolo import YOLOv10
        before = _vram_used_mb()
        self._model = YOLOv10(str(self._weights))
        self._loaded_vram_mb = _vram_used_mb() - before
        return self

    def __exit__(self, *exc) -> None:
        if self._model is None:
            return
        del self._model
        self._model = None
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    def run(self, pdf_path: Path) -> Iterator[WorkerEvent]:
        yield ModelLoadingEvent(model=self.name, source=str(self._weights),
                                vram_estimate_mb=self.estimated_vram_mb)
        # __enter__ already loaded; emit Loaded with measured stats
        yield ModelLoadedEvent(model=self.name,
                              vram_actual_mb=self._loaded_vram_mb,
                              load_seconds=...)
        # ... run loop with WorkProgressEvent per page ...
        # caller exits the `with` block → __exit__ fires →
        # ModelUnloading + ModelUnloaded events emitted by __exit__'s yield-equivalent
```

Note: `__exit__` can't yield. Two options for unload events:
- **A)** Have `__exit__` write to a thread-local buffer; caller pulls events post-context. Awkward.
- **B)** Use an explicit `unload()` method that yields events; `__exit__` calls it as a fallback if the user forgot. Cleaner.

We pick **B** — workers expose `__enter__`, `run()`, `unload()`, `__exit__`. The router calls `unload()` explicitly after the run loop, getting unload events in the same NDJSON stream. `__exit__` is a safety net if the user code crashes mid-run.

```python
# Router usage:
with YoloWorker(weights) as worker:
    yield from worker.run(pdf_path)
    yield from worker.unload()  # emits ModelUnloading + ModelUnloaded
# __exit__ is no-op since unload() already ran; only fires unload-on-exception path
```

## 4. Event Surface

```python
class WorkerEvent(BaseModel):
    type: str
    model: str
    timestamp_ms: int

class ModelLoadingEvent(WorkerEvent):
    type: Literal["model-loading"] = "model-loading"
    source: str                          # weights path or remote URL
    vram_estimate_mb: int

class ModelLoadedEvent(WorkerEvent):
    type: Literal["model-loaded"] = "model-loaded"
    vram_actual_mb: int                  # 0 on CPU
    load_seconds: float

class WorkProgressEvent(WorkerEvent):
    type: Literal["work-progress"] = "work-progress"
    stage: str                           # "page" | "box" | <worker-specific>
    current: int
    total: int
    eta_seconds: float | None            # None until enough samples
    throughput_per_sec: float | None     # None until enough samples
    vram_current_mb: int                 # 0 on CPU

class ModelUnloadingEvent(WorkerEvent):
    type: Literal["model-unloading"] = "model-unloading"

class ModelUnloadedEvent(WorkerEvent):
    type: Literal["model-unloaded"] = "model-unloaded"
    vram_freed_mb: int

class WorkCompleteEvent(WorkerEvent):
    type: Literal["work-complete"] = "work-complete"
    total_seconds: float
    items_processed: int
    output_summary: dict                 # worker-specific final stats

class WorkFailedEvent(WorkerEvent):
    type: Literal["work-failed"] = "work-failed"
    stage: str                           # "load" | "run" | "unload"
    reason: str
    recoverable: bool                    # True if user can free VRAM and retry
    hint: str | None                     # e.g. "reduce other VRAM use"
```

ETA computed via exponential moving average of throughput, only emitted after 3 samples to avoid wild estimates on the first page.

## 5. Failure Handling (D4)

```python
def run(self, pdf_path: Path) -> Iterator[WorkerEvent]:
    try:
        # ... loop ...
        for batch in batches:
            try:
                yield from self._process_batch(batch)
            except torch.cuda.OutOfMemoryError as e:
                if batch.size > 1:
                    torch.cuda.empty_cache()
                    yield WorkProgressEvent(stage="retry", current=batch.size//2, ...)
                    smaller = batch.split(2)
                    for sub in smaller:
                        yield from self._process_batch(sub)
                else:
                    yield WorkFailedEvent(stage="run", reason=str(e),
                                          recoverable=True,
                                          hint="batch_size already 1; reduce concurrent VRAM consumers")
                    raise
    except Exception as e:
        yield WorkFailedEvent(stage="run", reason=str(e), recoverable=False, hint=None)
        raise
```

Load-time OOM bubbles up from `__enter__`; router wraps in try/except and emits `WorkFailedEvent{stage="load"}`.

## 6. UI Shape (D5)

`frontend/src/local-pdf/components/StageIndicator.tsx`:

```
┌─ top-right of segmenter / extract page ──────────────┐
│  [●] DocLayout-YOLO • page 14/47 • ETA 2:14 • 612MB  │  ← collapsed
└──────────────────────────────────────────────────────┘
```

Click the badge → expands into a vertical drawer showing the full event timeline:

```
┌─ stage timeline ──────────────────────────────────┐
│  [✓] 21:43:12  DocLayout-YOLO • loaded (12s, 612MB) │
│  [●] 21:43:24  DocLayout-YOLO • page 14/47          │
│  [○] 21:43:24  ETA 2:14 (throughput 3.6 pg/s)       │
└───────────────────────────────────────────────────┘
```

Color rules:
- yellow `[●]` while loading or unloading
- green `[●]` while running
- red `[✗]` on failure
- gray `[✓]` on completed step (history)
- gray `[○]` on stat-only line (no state change)

## 7. Module Changes

Backend:
```
features/pipelines/local-pdf/src/local_pdf/workers/
  base.py         (NEW) — WorkerEvent + ModelWorker Protocol + helper _vram_used_mb()
  yolo.py         refactor → YoloWorker class with __enter__/__exit__/run/unload
  mineru.py       refactor → MineruWorker class with __enter__/__exit__/run/unload

features/pipelines/local-pdf/src/local_pdf/api/
  schemas.py      remove SegmentStart/Page/Complete + ExtractStart/Item/Complete; add WorkerEvent union
  routers/
    segments.py   replace router stream() with `with YoloWorker(): yield from worker.run() + worker.unload()`
    extract.py    same with MineruWorker
```

Frontend:
```
frontend/src/local-pdf/types.ts        add WorkerEvent + sub-types matching backend
frontend/src/local-pdf/streamReducer.ts (NEW) — reduces WorkerEvent stream → {stage, progress, eta, vram_mb, errors}
frontend/src/local-pdf/components/
  StageIndicator.tsx  (NEW) — collapsed + expanded views
  StageTimeline.tsx   (NEW) — drawer content
frontend/src/local-pdf/hooks/
  useSegments.ts      consume new events via streamReducer
  useExtract.ts       same
frontend/src/local-pdf/routes/
  SegmentRoute.tsx    mount <StageIndicator>
  ExtractRoute.tsx    mount <StageIndicator>
```

Tests update mechanically: every test that yields old `SegmentStart` / `ExtractStart` etc. now yields `ModelLoadingEvent + ModelLoadedEvent + WorkProgressEvent...` — same logic, new schema.

## 8. Out of Scope

- **Central model registry** with cross-call reuse (rejected per D2)
- **Multi-GPU dispatch** — workers assume one GPU; multi-GPU is a Phase E concern
- **Persistent disk model cache management** — relies on the underlying library's cache (HuggingFace / DocLayout-YOLO download caches); we don't add our own
- **Model warm-up prefetch** (start downloading MinerU weights while user is editing boxes) — possible follow-up; not in this spec
- **Per-document concurrency** — single-doc-at-a-time stays the model

## 9. Known Follow-ups

- Once Phase B (LLM-Judge) lands, audit whether its LLM-client should also be a `ModelWorker` (probably yes for non-API local LLMs; API-call clients don't need lifecycle).
- Phase E `span_match` will likely add a 3rd worker — same pattern.
- Model warm-up prefetch is a natural Phase A.0.1 if user-perceived latency proves to be a real issue.

## 10. Migration Note

This is a breaking change to the NDJSON event schema, but the schema isn't a published contract — the only consumers are this repo's own frontend hooks. Tests get updated in the same plan. Branch: `feat/a-0-model-lifecycle-and-progress` off `main`.
