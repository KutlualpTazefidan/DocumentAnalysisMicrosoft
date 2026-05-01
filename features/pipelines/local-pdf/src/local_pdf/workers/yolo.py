"""DocLayout-YOLO segmentation wrapper.

Public entry point: `run_yolo(pdf_path, *, predict_fn=None)`. When
`predict_fn` is None, the default loads the doclayout_yolo package and
the configured weights (LOCAL_PDF_YOLO_WEIGHTS) and runs inference.
Tests inject a fake predict_fn to avoid loading the real model.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from local_pdf.api.schemas import BoxKind, SegmentBox

# DocLayNet class names from DocLayout-YOLO -> our BoxKind enum.
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


def run_yolo(pdf_path: Path, *, predict_fn: PredictFn | None = None) -> list[SegmentBox]:
    """Run DocLayout-YOLO on a PDF and return canonical SegmentBox list."""
    fn = predict_fn or _default_predict
    pages = fn(pdf_path)
    out: list[SegmentBox] = []
    for page_pred in pages:
        for idx, b in enumerate(page_pred.boxes):
            kind = YOLO_CLASS_TO_BOX_KIND.get(b.class_name, BoxKind.paragraph)
            out.append(
                SegmentBox(
                    box_id=make_box_id(page_pred.page, idx),
                    page=page_pred.page,
                    bbox=b.bbox,
                    kind=kind,
                    confidence=b.confidence,
                    reading_order=idx,
                )
            )
    return out
