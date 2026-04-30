"""Extraction routes: full-doc + region MinerU runs, html GET/PUT, export."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    BoxKind,
    DocStatus,
    ExtractCompleteLine,
    ExtractElementLine,
    ExtractRegionRequest,
    ExtractStartLine,
    HtmlPayload,
)
from local_pdf.convert.source_elements import build_source_elements_payload
from local_pdf.storage.sidecar import (
    doc_dir,
    read_html,
    read_meta,
    read_segments,
    write_html,
    write_meta,
    write_mineru,
    write_source_elements,
)
from local_pdf.workers.mineru import run_mineru, run_mineru_region

router = APIRouter()

# Test hook for MinerU.
_MINERU_EXTRACT_FN = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wrap_html(elements: list[dict]) -> str:
    body = "\n".join(e["html_snippet"] for e in elements)
    return f"<!DOCTYPE html>\n<html><body>\n{body}\n</body></html>\n"


@router.post("/api/docs/{slug}/extract")
async def run_extract(slug: str, request: Request) -> StreamingResponse:
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

    def stream():
        yield json.dumps(ExtractStartLine(total_boxes=len(targets)).model_dump(mode="json")) + "\n"
        elements: list[dict] = []
        for r in run_mineru(pdf, targets, extract_fn=_MINERU_EXTRACT_FN):
            line = ExtractElementLine(box_id=r.box_id, html_snippet=r.html)
            elements.append(line.model_dump(mode="json"))
            yield json.dumps(line.model_dump(mode="json")) + "\n"
        write_mineru(cfg.data_root, slug, {"elements": elements})
        write_html(cfg.data_root, slug, _wrap_html(elements))
        yield (
            json.dumps(ExtractCompleteLine(boxes_extracted=len(elements)).model_dump(mode="json"))
            + "\n"
        )

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/api/docs/{slug}/extract/region")
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
    result = run_mineru_region(pdf, target, extract_fn=_MINERU_EXTRACT_FN)
    return {"box_id": result.box_id, "html": result.html}


@router.get("/api/docs/{slug}/html")
async def get_html(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=404, detail=f"no html for {slug}")
    return {"html": html}


@router.put("/api/docs/{slug}/html")
async def put_html(slug: str, body: HtmlPayload, request: Request) -> dict:
    cfg = request.app.state.config
    if not (doc_dir(cfg.data_root, slug)).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    write_html(cfg.data_root, slug, body.html)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"last_touched_utc": _now_iso()}))
    return {"ok": True}


@router.post("/api/docs/{slug}/export")
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
