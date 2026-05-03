"""Curator doc listing — assigned + open-for-curation only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from local_pdf.api.schemas import DocStatus
from local_pdf.storage.curators import read_curators
from local_pdf.storage.sidecar import read_html, read_meta

router = APIRouter()


@router.get("/api/curate/docs")
async def list_assigned_docs(request: Request) -> list[dict]:
    cfg = request.app.state.config
    ident = getattr(request.state, "identity", None)
    if ident is None or ident.role != "curator":
        raise HTTPException(status_code=403, detail="curator role required")
    cf = read_curators(cfg.data_root)
    me = next((c for c in cf.curators if c.id == ident.curator_id), None)
    if me is None:
        return []
    out: list[dict] = []
    for slug in me.assigned_slugs:
        meta = read_meta(cfg.data_root, slug)
        if meta is None:
            continue
        if meta.status != DocStatus.open_for_curation:
            continue
        out.append(meta.model_dump(mode="json"))
    return out


def _curator_can_see(cfg, ident, slug: str) -> bool:
    cf = read_curators(cfg.data_root)
    me = next((c for c in cf.curators if c.id == ident.curator_id), None)
    if me is None or slug not in me.assigned_slugs:
        return False
    meta = read_meta(cfg.data_root, slug)
    return meta is not None and meta.status == DocStatus.open_for_curation


@router.get("/api/curate/docs/{slug}")
async def get_assigned_doc(slug: str, request: Request) -> dict[str, object]:
    cfg = request.app.state.config
    ident = getattr(request.state, "identity", None)
    if ident is None or ident.role != "curator":
        raise HTTPException(status_code=403, detail="curator role required")
    if not _curator_can_see(cfg, ident, slug):
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    meta = read_meta(cfg.data_root, slug)
    assert meta is not None
    html = read_html(cfg.data_root, slug) or ""
    out: dict[str, object] = meta.model_dump(mode="json")
    out["html"] = html
    return out
