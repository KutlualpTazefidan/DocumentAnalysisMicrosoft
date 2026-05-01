"""Tests for the DocLayout-YOLO worker class.

The actual model is heavy and gated behind an env var. We test the wrapper's
input handling, deterministic box-id generation, lifecycle event emission,
and result conversion using a fake `predict_fn` injected via the constructor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
                    YOLOPredictedBox(
                        class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88
                    ),
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
                    YOLOPredictedBox(
                        class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88
                    ),
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
