"""Segmenter routes: run YOLO (legacy) or MinerU VLM (default) + CRUD on boxes."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from local_pdf.api.routers.admin.extract import _wrap_html
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
    read_mineru,
    read_segments,
    read_yolo,
    write_html,
    write_meta,
    write_mineru,
    write_segments,
    write_yolo,
)
from local_pdf.workers.base import now_ms
from local_pdf.workers.mineru import VlmSegmentBlock, vlm_extract_bbox, vlm_segment_doc
from local_pdf.workers.yolo import YoloWorker

router = APIRouter()

# Test hook: assign a fake predict_fn here from tests.
_YOLO_PREDICT_FN = None

# Test hook: inject a fake parse_doc_fn for the VLM path.
# Signature: (pdf_bytes: bytes) -> dict  (middle_json with pdf_info)
_VLM_PARSE_DOC_FN = None

# Test hook: inject a fake crop+VLM function for the per-bbox re-extract path.
# Signature: (pdf_bytes, page, bbox_pts, user_kind, *, box_id, parse_doc_fn, ...) -> str
# Assign a callable here to skip the real VLM in tests.
_VLM_EXTRACT_BBOX_FN: Callable[..., str] | None = None


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
async def run_segment(
    slug: str,
    request: Request,
    start: int | None = None,
    end: int | None = None,
) -> StreamingResponse:
    """Stream segmentation for *slug*.

    Default path: MinerU VLM (``LOCAL_PDF_SEGMENT_BACKEND`` unset or not "yolo").
    Legacy path:  YOLO (``LOCAL_PDF_SEGMENT_BACKEND=yolo``).

    Optional *start* / *end* query parameters (1-based, inclusive) restrict
    processing to a page range.  When provided, existing boxes outside that
    range are preserved; boxes inside the range are replaced with fresh output.
    Omitting both processes the full document (original behaviour).
    """
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    _bump_meta(cfg.data_root, slug, DocStatus.segmenting)

    env_backend = os.environ.get("LOCAL_PDF_SEGMENT_BACKEND", "").strip().lower()

    if env_backend == "yolo":
        # ── Legacy YOLO path ──────────────────────────────────────────────────
        def stream_yolo():
            try:
                with YoloWorker(_yolo_weights_path(), predict_fn=_YOLO_PREDICT_FN) as worker:
                    for ev in worker.run(pdf, start_page=start, end_page=end):
                        yield ev.model_dump_json() + "\n"
                    new_boxes = worker.boxes

                    # ── yolo.json: merge pristine output ──────────────────────
                    existing_yolo = read_yolo(cfg.data_root, slug) or {"boxes": []}
                    if start is not None or end is not None:
                        lo = start if start is not None else 1
                        hi = end if end is not None else float("inf")
                        kept_yolo = [
                            b
                            for b in existing_yolo.get("boxes", [])
                            if not (lo <= b.get("page", 0) <= hi)
                        ]
                    else:
                        kept_yolo = []
                    merged_yolo_boxes = kept_yolo + [b.model_dump(mode="json") for b in new_boxes]
                    write_yolo(cfg.data_root, slug, {"boxes": merged_yolo_boxes})

                    # ── segments.json: same merge logic ───────────────────────
                    existing_seg = read_segments(cfg.data_root, slug)
                    if existing_seg is not None and (start is not None or end is not None):
                        lo = start if start is not None else 1
                        hi = end if end is not None else float("inf")
                        kept_seg = [b for b in existing_seg.boxes if not (lo <= b.page <= hi)]
                    else:
                        kept_seg = []
                    all_boxes = kept_seg + new_boxes
                    all_boxes.sort(key=lambda b: (b.page, b.reading_order))
                    write_segments(cfg.data_root, slug, SegmentsFile(slug=slug, boxes=all_boxes))

                    meta = read_meta(cfg.data_root, slug)
                    if meta is not None:
                        write_meta(
                            cfg.data_root,
                            slug,
                            meta.model_copy(
                                update={
                                    "box_count": len(
                                        [b for b in all_boxes if b.kind != BoxKind.discard]
                                    ),
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

        return StreamingResponse(stream_yolo(), media_type="application/x-ndjson")

    # ── VLM path (default) ────────────────────────────────────────────────────
    def stream_vlm():
        try:
            pdf_bytes = pdf.read_bytes()

            # Build the page_subset from ?start / ?end.
            if start is not None or end is not None:
                # We don't know the total page count here; we'll pass the range
                # as the page_subset.  We rely on vlm_segment_doc emitting only
                # those pages.  Build a conservative range: we read the existing
                # segments to infer max page if end is None.
                existing_seg = read_segments(cfg.data_root, slug)
                lo = start if start is not None else 1
                if end is not None:
                    hi = end
                elif existing_seg is not None and existing_seg.boxes:
                    hi = max(b.page for b in existing_seg.boxes)
                else:
                    hi = 9999  # safe sentinel — vlm_segment_doc only yields pages in the PDF
                page_subset: list[int] | None = list(range(lo, hi + 1))
            else:
                page_subset = None

            new_boxes: list[SegmentBox] = []
            new_elements: list[dict] = []

            for ev in vlm_segment_doc(
                pdf_bytes,
                raster_dpi=288,
                page_subset=page_subset,
                parse_doc_fn=_VLM_PARSE_DOC_FN,
            ):
                if isinstance(ev, VlmSegmentBlock):
                    new_boxes.append(ev.box)
                    new_elements.append({"box_id": ev.box.box_id, "html_snippet": ev.html_snippet})
                else:
                    # WorkerEvent — yield to client.
                    yield ev.model_dump_json() + "\n"

            # ── Partial-page merge: preserve boxes/elements for untouched pages ─
            if start is not None or end is not None:
                lo = start if start is not None else 1
                hi = end if end is not None else float("inf")

                existing_seg = read_segments(cfg.data_root, slug)
                kept_boxes = (
                    [b for b in existing_seg.boxes if not (lo <= b.page <= hi)]
                    if existing_seg is not None
                    else []
                )

                existing_mineru = read_mineru(cfg.data_root, slug)
                existing_elements = existing_mineru["elements"] if existing_mineru else []

                def _page_from_bid(bid: str) -> int | None:
                    import re as _re

                    m = _re.match(r"p(\d+)-", bid or "")
                    return int(m.group(1)) if m else None

                kept_elements = [
                    e
                    for e in existing_elements
                    if not (lo <= (_page_from_bid(e.get("box_id", "")) or 0) <= hi)
                ]
            else:
                kept_boxes = []
                kept_elements = []

            all_boxes = kept_boxes + new_boxes
            all_boxes.sort(key=lambda b: (b.page, b.reading_order))
            all_elements = kept_elements + new_elements

            write_segments(
                cfg.data_root, slug, SegmentsFile(slug=slug, boxes=all_boxes, raster_dpi=288)
            )
            write_mineru(cfg.data_root, slug, {"elements": all_elements, "diagnostics": []})
            write_html(cfg.data_root, slug, _wrap_html(all_elements))

            meta = read_meta(cfg.data_root, slug)
            if meta is not None:
                write_meta(
                    cfg.data_root,
                    slug,
                    meta.model_copy(
                        update={
                            "box_count": len([b for b in all_boxes if b.kind != BoxKind.discard]),
                            "last_touched_utc": _now_iso(),
                        }
                    ),
                )
        except Exception as exc:
            from local_pdf.workers.mineru import MineruWorker

            failure = WorkFailedEvent(
                model=MineruWorker.name,
                timestamp_ms=now_ms(),
                stage="run",
                reason=str(exc),
                recoverable=False,
                hint=None,
            )
            yield failure.model_dump_json() + "\n"
            raise

    return StreamingResponse(stream_vlm(), media_type="application/x-ndjson")


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


def _re_extract_box(cfg, slug: str, box: SegmentBox, raster_dpi: int) -> None:
    """Crop the PDF page to box.bbox, run VLM, and write the new html_snippet
    into mineru.json + html.html.

    Skipped silently when mineru.json does not exist yet (document has not been
    through the VLM segmentation pass).  Any exception is logged and swallowed
    so callers (bbox edits, kind changes) always succeed even when VLM is
    unavailable.
    """
    import logging

    existing_mineru = read_mineru(cfg.data_root, slug)
    if existing_mineru is None:
        # VLM not run yet — nothing to update.
        return

    pdf_path = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf_path.exists():
        return

    try:
        pdf_bytes = pdf_path.read_bytes()
        # bbox stored in pixel space at raster_dpi; convert to PDF points.
        k = 72.0 / raster_dpi
        bbox_pts = (
            box.bbox[0] * k,
            box.bbox[1] * k,
            box.bbox[2] * k,
            box.bbox[3] * k,
        )

        if _VLM_EXTRACT_BBOX_FN is not None:
            new_html = _VLM_EXTRACT_BBOX_FN(
                pdf_bytes,
                box.page,
                bbox_pts,
                box.kind,
                box_id=box.box_id,
            )
        else:
            new_html = vlm_extract_bbox(
                pdf_bytes,
                box.page,
                bbox_pts,
                box.kind,
                box_id=box.box_id,
            )

        # Replace / insert this element in the existing elements list.
        elements = list(existing_mineru.get("elements", []))
        found = False
        for i, el in enumerate(elements):
            if el.get("box_id") == box.box_id:
                elements[i] = {"box_id": box.box_id, "html_snippet": new_html}
                found = True
                break
        if not found:
            elements.append({"box_id": box.box_id, "html_snippet": new_html})

        diagnostics = existing_mineru.get("diagnostics", [])
        write_mineru(cfg.data_root, slug, {"elements": elements, "diagnostics": diagnostics})
        write_html(cfg.data_root, slug, _wrap_html(elements))
    except Exception:
        logging.getLogger(__name__).exception(
            "vlm_extract_bbox failed for %s/%s — keeping old html_snippet", slug, box.box_id
        )


@router.put("/api/admin/docs/{slug}/segments/{box_id}")
async def update_box(
    slug: str,
    box_id: str,
    body: UpdateBoxRequest,
    request: Request,
    reextract: bool = True,
) -> dict[str, Any]:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    seg = read_segments(cfg.data_root, slug)
    raster_dpi = seg.raster_dpi if seg is not None else 288
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            bbox_changed = body.bbox is not None and tuple(body.bbox) != tuple(b.bbox)
            kind_changed = body.kind is not None and body.kind != b.kind
            updates: dict[str, Any] = {}
            if body.kind is not None:
                updates["kind"] = body.kind
            if body.bbox is not None:
                updates["bbox"] = body.bbox
            if body.reading_order is not None:
                updates["reading_order"] = body.reading_order
            if body.manually_activated is not None:
                updates["manually_activated"] = body.manually_activated
            boxes[i] = b.model_copy(update=updates)
            _replace_segments(cfg.data_root, slug, boxes)
            if reextract and (bbox_changed or kind_changed):
                _re_extract_box(cfg, slug, boxes[i], raster_dpi)
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
async def create_box(
    slug: str,
    body: CreateBoxRequest,
    request: Request,
    reextract: bool = True,
) -> dict[str, Any]:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"no segments for {slug}")
    raster_dpi = seg.raster_dpi
    boxes = list(seg.boxes)
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
    if reextract:
        _re_extract_box(cfg, slug, new, raster_dpi)
    return dict(new.model_dump(mode="json"))


def _load_yolo_or_404(data_root, slug: str) -> dict:
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
async def reset_box(
    slug: str,
    box_id: str,
    request: Request,
    reextract: bool = True,
) -> dict[str, Any]:
    """Restore a single box's bbox + kind + confidence from yolo.json."""
    cfg = request.app.state.config
    yolo = _load_yolo_or_404(cfg.data_root, slug)
    yolo_by_id = {b["box_id"]: b for b in yolo.get("boxes", [])}
    if box_id not in yolo_by_id:
        raise HTTPException(
            status_code=409,
            detail="no original to reset to (this box wasn't YOLO-detected)",
        )
    seg = read_segments(cfg.data_root, slug)
    raster_dpi = seg.raster_dpi if seg is not None else 288
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            orig = yolo_by_id[box_id]
            boxes[i] = b.model_copy(
                update={
                    "bbox": tuple(orig["bbox"]),
                    "kind": BoxKind(orig["kind"]),
                    "confidence": orig["confidence"],
                    "manually_activated": False,
                    "continues_from": None,
                    "continues_to": None,
                }
            )
            _replace_segments(cfg.data_root, slug, boxes)
            if reextract:
                _re_extract_box(cfg, slug, boxes[i], raster_dpi)
            return dict(boxes[i].model_dump(mode="json"))
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")


@router.post("/api/admin/docs/{slug}/segments/{box_id}/merge-down")
async def merge_down(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    """Link source box to the topmost non-discard box on the next page."""
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    by_id = {b.box_id: (i, b) for i, b in enumerate(boxes)}
    if box_id not in by_id:
        raise HTTPException(status_code=404, detail=f"box not found: {box_id}")
    src_idx, src = by_id[box_id]
    if src.continues_to is not None:
        raise HTTPException(status_code=409, detail="already linked downwards")
    next_page_candidates = [
        b for b in boxes if b.page == src.page + 1 and b.kind != BoxKind.discard
    ]
    if not next_page_candidates:
        raise HTTPException(status_code=409, detail="no box on next page to merge with")
    target = min(next_page_candidates, key=lambda b: b.bbox[1])
    tgt_idx, _ = by_id[target.box_id]
    boxes[src_idx] = src.model_copy(update={"continues_to": target.box_id})
    boxes[tgt_idx] = target.model_copy(update={"continues_from": box_id})
    _replace_segments(cfg.data_root, slug, boxes)
    seg = read_segments(cfg.data_root, slug)
    return dict(seg.model_dump(mode="json"))  # type: ignore[union-attr]


@router.post("/api/admin/docs/{slug}/segments/{box_id}/merge-up")
async def merge_up(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    """Link source box to the bottommost non-discard box on the previous page."""
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    by_id = {b.box_id: (i, b) for i, b in enumerate(boxes)}
    if box_id not in by_id:
        raise HTTPException(status_code=404, detail=f"box not found: {box_id}")
    src_idx, src = by_id[box_id]
    if src.continues_from is not None:
        raise HTTPException(status_code=409, detail="already linked upwards")
    prev_page_candidates = [
        b for b in boxes if b.page == src.page - 1 and b.kind != BoxKind.discard
    ]
    if not prev_page_candidates:
        raise HTTPException(status_code=409, detail="no box on previous page to merge with")
    target = max(prev_page_candidates, key=lambda b: b.bbox[3])
    tgt_idx, _ = by_id[target.box_id]
    boxes[src_idx] = src.model_copy(update={"continues_from": target.box_id})
    boxes[tgt_idx] = target.model_copy(update={"continues_to": box_id})
    _replace_segments(cfg.data_root, slug, boxes)
    seg = read_segments(cfg.data_root, slug)
    return dict(seg.model_dump(mode="json"))  # type: ignore[union-attr]


@router.post("/api/admin/docs/{slug}/segments/{box_id}/unmerge-down")
async def unmerge_down(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    """Clear continues_to on source and continues_from on the linked target."""
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    by_id = {b.box_id: (i, b) for i, b in enumerate(boxes)}
    if box_id not in by_id:
        raise HTTPException(status_code=404, detail=f"box not found: {box_id}")
    src_idx, src = by_id[box_id]
    if src.continues_to is None:
        raise HTTPException(status_code=409, detail="continues_to not set; nothing to unmerge")
    target_id = src.continues_to
    boxes[src_idx] = src.model_copy(update={"continues_to": None})
    if target_id in by_id:
        tgt_idx, tgt = by_id[target_id]
        boxes[tgt_idx] = tgt.model_copy(update={"continues_from": None})
    _replace_segments(cfg.data_root, slug, boxes)
    seg = read_segments(cfg.data_root, slug)
    return dict(seg.model_dump(mode="json"))  # type: ignore[union-attr]


@router.post("/api/admin/docs/{slug}/segments/{box_id}/unmerge-up")
async def unmerge_up(slug: str, box_id: str, request: Request) -> dict[str, Any]:
    """Clear continues_from on source and continues_to on the linked target."""
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    by_id = {b.box_id: (i, b) for i, b in enumerate(boxes)}
    if box_id not in by_id:
        raise HTTPException(status_code=404, detail=f"box not found: {box_id}")
    src_idx, src = by_id[box_id]
    if src.continues_from is None:
        raise HTTPException(status_code=409, detail="continues_from not set; nothing to unmerge")
    target_id = src.continues_from
    boxes[src_idx] = src.model_copy(update={"continues_from": None})
    if target_id in by_id:
        tgt_idx, tgt = by_id[target_id]
        boxes[tgt_idx] = tgt.model_copy(update={"continues_to": None})
    _replace_segments(cfg.data_root, slug, boxes)
    seg = read_segments(cfg.data_root, slug)
    return dict(seg.model_dump(mode="json"))  # type: ignore[union-attr]
