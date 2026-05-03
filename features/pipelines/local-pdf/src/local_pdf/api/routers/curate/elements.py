"""Curator element listing + detail."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from local_pdf.api.routers.curate.docs import _curator_can_see
from local_pdf.storage.sidecar import read_source_elements

router = APIRouter()


def _to_dom(e: dict) -> dict:
    kind = e.get("kind", "paragraph")
    return {
        "element_id": e["box_id"],
        "page_number": e.get("page", 1),
        "element_type": "list_item" if kind == "list_item" else kind,
        "content": e.get("text", ""),
    }


@router.get("/api/curate/docs/{slug}/elements")
async def list_elements(slug: str, request: Request) -> list[dict]:
    cfg = request.app.state.config
    ident = getattr(request.state, "identity", None)
    if ident is None or ident.role != "curator":
        raise HTTPException(status_code=403, detail="curator role required")
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    payload = read_source_elements(cfg.data_root, slug) or {"elements": []}
    return [_to_dom(e) for e in payload.get("elements", [])]


@router.get("/api/curate/docs/{slug}/elements/{element_id}")
async def get_element(slug: str, element_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    ident = getattr(request.state, "identity", None)
    if ident is None or ident.role != "curator":
        raise HTTPException(status_code=403, detail="curator role required")
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    payload = read_source_elements(cfg.data_root, slug) or {"elements": []}
    match = next((e for e in payload.get("elements", []) if e["box_id"] == element_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"element not found: {element_id}")
    return _to_dom(match)
