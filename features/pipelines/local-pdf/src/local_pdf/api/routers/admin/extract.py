"""Extraction routes: full-doc + region MinerU runs, html GET/PUT, export."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    BoxKind,
    DocStatus,
    ExtractRegionRequest,
    HtmlPayload,
    WorkFailedEvent,
)
from local_pdf.convert.source_elements import build_source_elements_payload
from local_pdf.storage.sidecar import (
    doc_dir,
    read_html,
    read_meta,
    read_mineru,
    read_segments,
    write_html,
    write_meta,
    write_mineru,
    write_source_elements,
)
from local_pdf.workers.base import now_ms
from local_pdf.workers.mineru import MineruWorker

router = APIRouter()

# Test hook for MinerU.
_MINERU_EXTRACT_FN = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


_PDF_STYLE = (
    "<style>"
    "body{font-family:Georgia,'Times New Roman',serif;"
    "max-width:720px;margin:2rem auto;line-height:1.6;color:#1f2937}"
    "h1{font-size:2em;font-weight:bold;text-align:center;margin:1.5em 0 0.5em}"
    "h2{font-size:1.5em;font-weight:bold;margin:1.2em 0 0.4em;"
    "border-bottom:1px solid #d1d5db;padding-bottom:0.2em}"
    "h3{font-size:1.2em;font-weight:bold;margin:1em 0 0.3em}"
    "p{margin:0.6em 0}"
    ".page-header,.page-footer{font-size:0.75em;color:#6b7280;"
    "text-align:center;margin:0.5em 0}"
    ".page-number{display:inline-block;font-size:0.75em;color:#6b7280}"
    ".extracted-table{margin:1em 0;overflow-x:auto}"
    ".extracted-table table{border-collapse:collapse;width:100%}"
    ".extracted-table th,.extracted-table td{"
    "border:1px solid #d1d5db;padding:0.4em 0.6em}"
    ".toc{margin:1em 0;padding-left:1em}"
    ".md-list{margin:0.6em 0;padding-left:1.5em}"
    "pre{background:#f3f4f6;padding:1em;border-radius:4px;overflow-x:auto}"
    'code{font-family:"SF Mono",Menlo,monospace}'
    "hr.page-break{border:none;border-top:2px dashed #d1d5db;margin:2em 0}"
    "</style>"
)


def _wrap_html(elements: list[dict]) -> str:
    """Wrap extracted HTML snippets with PDF-like typography and page-break separators.

    Inserts ``<hr class="page-break">`` between elements from different pages.
    The page number is derived from the box_id prefix (``pN-bM`` convention).
    """

    def _page_from_box_id(box_id: str) -> str:
        """Return the page prefix (e.g. 'p1') from a box_id like 'p1-b0'."""
        return box_id.split("-")[0] if box_id else ""

    parts: list[str] = []
    prev_page = ""
    for e in elements:
        cur_page = _page_from_box_id(e.get("box_id", ""))
        if prev_page and cur_page != prev_page:
            parts.append('<hr class="page-break">')
        parts.append(e["html_snippet"])
        prev_page = cur_page

    body = "\n".join(parts)
    return f"<!DOCTYPE html>\n<html><head>{_PDF_STYLE}</head><body>\n{body}\n</body></html>\n"


@router.post("/api/admin/docs/{slug}/extract")
async def run_extract(slug: str, request: Request, page: int | None = None) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(
            cfg.data_root,
            slug,
            meta.model_copy(
                update={"status": DocStatus.extracting, "last_touched_utc": _now_iso()}
            ),
        )

    targets = [b for b in seg.boxes if b.kind != BoxKind.discard]
    if page is not None:
        targets = [b for b in targets if b.page == page]

    def stream():
        try:
            with MineruWorker(extract_fn=_MINERU_EXTRACT_FN, raster_dpi=seg.raster_dpi) as worker:
                for ev in worker.run(pdf, targets):
                    # Persist after each yielded WorkProgressEvent's box result.
                    yield ev.model_dump_json() + "\n"
                # Build elements list from worker.results.
                elements = [{"box_id": r.box_id, "html_snippet": r.html} for r in worker.results]
                write_mineru(cfg.data_root, slug, {"elements": elements})
                write_html(cfg.data_root, slug, _wrap_html(elements))
                for ev in worker.unload():
                    yield ev.model_dump_json() + "\n"
        except Exception as exc:
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

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/api/admin/docs/{slug}/extract/region")
async def run_extract_region(slug: str, body: ExtractRegionRequest, request: Request) -> dict:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    target = next((b for b in seg.boxes if b.box_id == body.box_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"box not found: {body.box_id}")
    with MineruWorker(extract_fn=_MINERU_EXTRACT_FN, raster_dpi=seg.raster_dpi) as worker:
        result = worker.extract_region(pdf, target)
    return {"box_id": result.box_id, "html": result.html}


@router.get("/api/admin/docs/{slug}/mineru")
async def get_mineru(slug: str, request: Request) -> dict:
    """Return the stored MinerU extraction output (mineru-out.json).

    Used by the frontend to compute per-page extraction state for the
    colored page-button grid.  Returns 404 when no extraction has been
    run yet.
    """
    cfg = request.app.state.config
    data = read_mineru(cfg.data_root, slug)
    if data is None:
        raise HTTPException(status_code=404, detail=f"no mineru data for {slug}")
    return data


@router.get("/api/admin/docs/{slug}/html")
async def get_html(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=404, detail=f"no html for {slug}")
    return {"html": html}


@router.put("/api/admin/docs/{slug}/html")
async def put_html(slug: str, body: HtmlPayload, request: Request) -> dict:
    cfg = request.app.state.config
    if not (doc_dir(cfg.data_root, slug)).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    write_html(cfg.data_root, slug, body.html)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"last_touched_utc": _now_iso()}))
    return {"ok": True}


@router.get("/api/admin/docs/{slug}/extract/diagnose")
async def diagnose_extract(slug: str, request: Request, page: int = 1) -> dict:
    """Diagnostic: parse one page via MinerU and return raw bbox + text data.

    Returns the MinerU para_block bboxes alongside their IoU against each
    segment box on that page, so the caller can verify coordinate alignment
    without running a full extraction.

    Response shape::

        {
          "page": 1,
          "raster_dpi": 144,
          "page_size_pts": [728, 927],
          "mineru_blocks": [
            {"type": "title", "bbox": [198, 145, 527, 178],
             "text_preview": "A Study of...",
             "iou_to_user_boxes": [{"box_id": "p1-b0", "iou": 0.87}]}
          ]
        }
    """
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    raster_dpi = seg.raster_dpi if seg is not None else 144

    try:
        from mineru.backend.pipeline.pipeline_analyze import doc_analyze_streaming
        from mineru.backend.pipeline.pipeline_middle_json_mkcontent import (
            merge_para_with_text,
            merge_visual_blocks_to_markdown,
        )
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"MinerU not available: {exc}") from exc

    pdf_bytes = pdf.read_bytes()
    all_page_infos: list[dict] = []

    class _NullWriter:
        def write(self, *_a: object, **_kw: object) -> None:
            pass

    def _on_ready(
        doc_index: int,
        model_list: list,
        middle_json: dict,
        ocr_enable: bool,
    ) -> None:
        pdf_info = middle_json.get("pdf_info", [])
        all_page_infos.extend(pdf_info)

    doc_analyze_streaming(
        pdf_bytes_list=[pdf_bytes],
        image_writer_list=[_NullWriter()],
        lang_list=[None],
        on_doc_ready=_on_ready,
        parse_method="auto",
    )

    if page < 1 or page > len(all_page_infos):
        raise HTTPException(
            status_code=404,
            detail=f"page {page} out of range (1-{len(all_page_infos)})",
        )

    page_info = all_page_infos[page - 1]
    page_size = page_info.get("page_size") or [0, 0]

    # Build user-bbox-to-pts lookup for IoU comparison.
    from local_pdf.workers.mineru import _iou, _user_bbox_to_pts

    user_boxes_pts: list[tuple[str, tuple[float, float, float, float]]] = []
    if seg is not None:
        for b in seg.boxes:
            if b.page == page:
                user_boxes_pts.append((b.box_id, _user_bbox_to_pts(b.bbox, raster_dpi)))

    visual_block_types = {"image", "table", "chart", "code"}
    blocks_out = []
    for blk in page_info.get("para_blocks", []) or []:
        raw_bbox = blk.get("bbox")
        if raw_bbox is None:
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in raw_bbox[:4])
        except (TypeError, ValueError):
            continue
        blk_type = blk.get("type", "unknown")
        try:
            if blk_type in visual_block_types:
                text = merge_visual_blocks_to_markdown(blk) or ""
            else:
                text = merge_para_with_text(blk) or ""
        except Exception:
            text = ""
        iou_scores: list[tuple[float, str]] = [
            (_iou((x0, y0, x1, y1), bpts), bid) for bid, bpts in user_boxes_pts
        ]
        iou_scores.sort(key=lambda t: -t[0])
        iou_list = [{"box_id": bid, "iou": round(score, 4)} for score, bid in iou_scores[:5]]
        blocks_out.append(
            {
                "type": blk_type,
                "bbox": [x0, y0, x1, y1],
                "text_preview": text[:120],
                "iou_to_user_boxes": iou_list,
            }
        )

    return {
        "page": page,
        "raster_dpi": raster_dpi,
        "page_size_pts": page_size,
        "mineru_blocks": blocks_out,
    }


@router.post("/api/admin/docs/{slug}/export")
async def run_export(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=400, detail="run /extract first")
    payload = build_source_elements_payload(slug=slug, segments=seg, html=html)
    write_source_elements(cfg.data_root, slug, payload)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(
            cfg.data_root,
            slug,
            meta.model_copy(update={"status": DocStatus.done, "last_touched_utc": _now_iso()}),
        )
    return payload
