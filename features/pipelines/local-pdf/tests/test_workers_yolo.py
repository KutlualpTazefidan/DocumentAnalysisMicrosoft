"""Tests for the DocLayout-YOLO worker wrapper.

The actual model is heavy and gated behind an env var. We test the wrapper's
input handling, deterministic box-id generation, and result conversion using
a fake `predict` callable injected via the public API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_yolo_class_to_kind_mapping_covers_doclaynet_classes() -> None:
    from local_pdf.workers.yolo import YOLO_CLASS_TO_BOX_KIND

    # DocLayNet class names DocLayout-YOLO uses.
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


def test_run_yolo_with_injected_predict(tmp_path: Path) -> None:
    """Run end-to-end with a fake predict() that returns one synthetic box."""
    from local_pdf.api.schemas import BoxKind
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox, run_yolo

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

    boxes = run_yolo(pdf, predict_fn=fake_predict)
    assert len(boxes) == 2
    assert boxes[0].box_id == "p1-b0"
    assert boxes[0].kind == BoxKind.heading
    assert boxes[0].confidence == 0.95
    assert boxes[1].kind == BoxKind.paragraph
