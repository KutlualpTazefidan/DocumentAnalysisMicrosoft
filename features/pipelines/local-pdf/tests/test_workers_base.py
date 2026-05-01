"""Tests for WorkerEvent base models, ModelWorker Protocol, and helpers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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

    assert (
        ModelLoadingEvent(model="X", timestamp_ms=1, source="/w", vram_estimate_mb=100).type
        == "model-loading"
    )
    assert (
        ModelLoadedEvent(model="X", timestamp_ms=1, vram_actual_mb=120, load_seconds=2.5).type
        == "model-loaded"
    )
    assert (
        WorkProgressEvent(
            model="X",
            timestamp_ms=1,
            stage="page",
            current=1,
            total=10,
            eta_seconds=None,
            throughput_per_sec=None,
            vram_current_mb=120,
        ).type
        == "work-progress"
    )
    assert ModelUnloadingEvent(model="X", timestamp_ms=1).type == "model-unloading"
    assert ModelUnloadedEvent(model="X", timestamp_ms=1, vram_freed_mb=120).type == "model-unloaded"
    assert (
        WorkCompleteEvent(
            model="X", timestamp_ms=1, total_seconds=10.0, items_processed=4, output_summary={}
        ).type
        == "work-complete"
    )
    assert (
        WorkFailedEvent(
            model="X", timestamp_ms=1, stage="run", reason="OOM", recoverable=True, hint=None
        ).type
        == "work-failed"
    )


def test_worker_event_union_round_trip_via_pydantic_typeadapter() -> None:
    from local_pdf.workers.base import (
        ModelLoadedEvent,
        ModelLoadingEvent,
        WorkerEventUnion,
    )
    from pydantic import TypeAdapter

    adapter: TypeAdapter[WorkerEventUnion] = TypeAdapter(WorkerEventUnion)
    loading = adapter.validate_python(
        {
            "type": "model-loading",
            "model": "Y",
            "timestamp_ms": 1,
            "source": "/w",
            "vram_estimate_mb": 700,
        }
    )
    assert isinstance(loading, ModelLoadingEvent)

    loaded = adapter.validate_python(
        {
            "type": "model-loaded",
            "model": "Y",
            "timestamp_ms": 2,
            "vram_actual_mb": 712,
            "load_seconds": 3.1,
        }
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


def test_vram_used_mb_reads_torch_memory_when_cuda_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
