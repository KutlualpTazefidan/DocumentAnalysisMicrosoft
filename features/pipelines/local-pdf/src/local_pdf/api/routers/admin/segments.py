"""Segmenter routes: run YOLO + CRUD on boxes."""

from __future__ import annotations

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


@router.post("/api/admin/docs/{slug}/segment")
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
        except Exception as exc:
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


@router.get("/api/admin/docs/{slug}/segments")
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


@router.put("/api/admin/docs/{slug}/segments/{box_id}")
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


@router.delete("/api/admin/docs/{slug}/segments/{box_id}")
async def delete_box(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            boxes[i] = b.model_copy(update={"kind": BoxKind.discard})
            _replace_segments(cfg.data_root, slug, boxes)
            return dict(boxes[i].model_dump(mode="json"))
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")


@router.post("/api/admin/docs/{slug}/segments/merge")
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


@router.post("/api/admin/docs/{slug}/segments/split")
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


@router.post("/api/admin/docs/{slug}/segments", status_code=status.HTTP_201_CREATED)
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


def _load_yolo_or_404(data_root, slug: str) -> dict:
    from local_pdf.storage.sidecar import read_yolo

    yolo = read_yolo(data_root, slug)
    if yolo is None:
        raise HTTPException(status_code=404, detail="no yolo output to reset from")
    return yolo


def _yolo_boxes_for_page(yolo: dict, page: int) -> list[SegmentBox]:
    return [SegmentBox.model_validate(b) for b in yolo.get("boxes", []) if b.get("page") == page]


@router.post("/api/admin/docs/{slug}/segments/reset")
async def reset_page(slug: str, page: int, request: Request) -> dict[str, Any]:
    """Replace all boxes on page N with the original YOLO-detected boxes."""
    cfg = request.app.state.config
    yolo = _load_yolo_or_404(cfg.data_root, slug)
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    yolo_page_boxes = _yolo_boxes_for_page(yolo, page)
    # Keep boxes for other pages, replace this page with yolo originals
    other_pages = [b for b in boxes if b.page != page]
    new_boxes = other_pages + yolo_page_boxes
    new_boxes.sort(key=lambda b: (b.page, b.reading_order))
    _replace_segments(cfg.data_root, slug, new_boxes)
    seg = SegmentsFile(slug=slug, boxes=new_boxes)
    return dict(seg.model_dump(mode="json"))


@router.post("/api/admin/docs/{slug}/segments/{box_id}/reset")
async def reset_box(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    """Restore a single box's bbox + kind + confidence from yolo.json."""
    cfg = request.app.state.config
    yolo = _load_yolo_or_404(cfg.data_root, slug)
    yolo_by_id = {b["box_id"]: b for b in yolo.get("boxes", [])}
    if box_id not in yolo_by_id:
        raise HTTPException(
            status_code=409,
            detail="no original to reset to (this box wasn't YOLO-detected)",
        )
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            orig = yolo_by_id[box_id]
            boxes[i] = b.model_copy(
                update={
                    "bbox": tuple(orig["bbox"]),
                    "kind": BoxKind(orig["kind"]),
                    "confidence": orig["confidence"],
                }
            )
            _replace_segments(cfg.data_root, slug, boxes)
            return dict(boxes[i].model_dump(mode="json"))
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")
