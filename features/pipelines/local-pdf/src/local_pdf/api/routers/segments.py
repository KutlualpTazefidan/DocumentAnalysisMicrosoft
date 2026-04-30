"""Segmenter routes: run YOLO + CRUD on boxes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    DocStatus,
    SegmentCompleteLine,
    SegmentPageLine,
    SegmentsFile,
    SegmentStartLine,
)
from local_pdf.storage.sidecar import (
    doc_dir,
    read_meta,
    read_segments,
    write_meta,
    write_segments,
    write_yolo,
)
from local_pdf.workers.yolo import run_yolo

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


@router.post("/api/docs/{slug}/segment")
async def run_segment(slug: str, request: Request) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    _bump_meta(cfg.data_root, slug, DocStatus.segmenting)

    def stream():
        boxes = run_yolo(pdf, predict_fn=_YOLO_PREDICT_FN)
        pages = sorted({b.page for b in boxes})
        yield json.dumps(SegmentStartLine(total_pages=len(pages)).model_dump(mode="json")) + "\n"
        for p in pages:
            count = sum(1 for b in boxes if b.page == p)
            yield (
                json.dumps(SegmentPageLine(page=p, boxes_found=count).model_dump(mode="json"))
                + "\n"
            )
        write_yolo(cfg.data_root, slug, {"boxes": [b.model_dump(mode="json") for b in boxes]})
        write_segments(cfg.data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
        meta = read_meta(cfg.data_root, slug)
        if meta is not None:
            write_meta(
                cfg.data_root,
                slug,
                meta.model_copy(update={"box_count": len(boxes), "last_touched_utc": _now_iso()}),
            )
        yield json.dumps(SegmentCompleteLine(boxes_total=len(boxes)).model_dump(mode="json")) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/api/docs/{slug}/segments")
async def get_segments(slug: str, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"no segments yet for {slug}")
    return dict(seg.model_dump(mode="json"))
