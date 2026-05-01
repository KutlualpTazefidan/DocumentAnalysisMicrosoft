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
