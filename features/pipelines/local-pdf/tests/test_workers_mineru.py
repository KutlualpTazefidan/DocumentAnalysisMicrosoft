"""Tests for the MinerU 3 worker class."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
        WorkCompleteEvent,
        WorkProgressEvent,
    )
    from local_pdf.workers.mineru import MinerUResult, MineruWorker

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(
            box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.heading, confidence=0.95
        ),
        SegmentBox(
            box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.88
        ),
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
        SegmentBox(
            box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.discard, confidence=0.5
        ),
        SegmentBox(
            box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.9
        ),
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
    box = SegmentBox(
        box_id="p2-b3", page=2, bbox=(50, 50, 200, 200), kind=BoxKind.table, confidence=0.7
    )

    calls: list[str] = []

    def fake(_p: Path, b: SegmentBox) -> MinerUResult:
        calls.append(b.box_id)
        return MinerUResult(box_id=b.box_id, html="<table><tr><td>x</td></tr></table>")

    with MineruWorker(extract_fn=fake) as worker:
        out = worker.extract_region(pdf, box)

    assert calls == ["p2-b3"]
    assert out.html.startswith("<table>")
