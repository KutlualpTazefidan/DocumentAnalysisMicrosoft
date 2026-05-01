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
from typing import TYPE_CHECKING, Annotated, Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Iterator


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
