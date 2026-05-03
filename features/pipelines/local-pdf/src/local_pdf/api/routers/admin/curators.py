"""Admin curator + assignment management."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from local_pdf.api.schemas import (
    AssignCuratorRequest,
    CreateCuratorRequest,
    CreateCuratorResponse,
    Curator,
    CuratorsFile,
)
from local_pdf.storage.curators import (
    hash_token,
    new_curator_id,
    new_token,
    read_curators,
    token_prefix,
    write_curators,
)
from local_pdf.storage.sidecar import read_meta

router = APIRouter()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _public_view(c: Curator) -> dict:
    d = c.model_dump(mode="json")
    d.pop("token_sha256", None)
    return d  # type: ignore[no-any-return]


@router.get("/api/admin/curators")
async def list_curators(request: Request) -> list[dict]:
    cf = read_curators(request.app.state.config.data_root)
    return [_public_view(c) for c in cf.curators]


@router.post(
    "/api/admin/curators",
    response_model=CreateCuratorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_curator(body: CreateCuratorRequest, request: Request) -> CreateCuratorResponse:
    cfg = request.app.state.config
    cf = read_curators(cfg.data_root)
    raw = new_token()
    cur = Curator(
        id=new_curator_id(),
        name=body.name,
        token_prefix=token_prefix(raw),
        token_sha256=hash_token(raw),
        assigned_slugs=[],
        created_at=_now(),
        last_seen_at=None,
        active=True,
    )
    write_curators(cfg.data_root, CuratorsFile(curators=[*cf.curators, cur]))
    return CreateCuratorResponse(
        id=cur.id,
        name=cur.name,
        token=raw,
        token_prefix=cur.token_prefix,
        created_at=cur.created_at,
    )


@router.delete(
    "/api/admin/curators/{curator_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_curator(curator_id: str, request: Request) -> Response:
    cfg = request.app.state.config
    cf = read_curators(cfg.data_root)
    keep = [c for c in cf.curators if c.id != curator_id]
    if len(keep) == len(cf.curators):
        raise HTTPException(status_code=404, detail=f"curator not found: {curator_id}")
    write_curators(cfg.data_root, CuratorsFile(curators=keep))
    return Response(status_code=204)


@router.get("/api/admin/docs/{slug}/curators")
async def list_doc_curators(slug: str, request: Request) -> list[dict]:
    cfg = request.app.state.config
    if read_meta(cfg.data_root, slug) is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    cf = read_curators(cfg.data_root)
    return [_public_view(c) for c in cf.curators if slug in c.assigned_slugs]


@router.post("/api/admin/docs/{slug}/curators")
async def assign_curator(slug: str, body: AssignCuratorRequest, request: Request) -> dict:
    cfg = request.app.state.config
    if read_meta(cfg.data_root, slug) is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    cf = read_curators(cfg.data_root)
    out: list[Curator] = []
    found = False
    for c in cf.curators:
        if c.id == body.curator_id:
            found = True
            if slug not in c.assigned_slugs:
                out.append(c.model_copy(update={"assigned_slugs": [*c.assigned_slugs, slug]}))
            else:
                out.append(c)
        else:
            out.append(c)
    if not found:
        raise HTTPException(status_code=404, detail=f"curator not found: {body.curator_id}")
    write_curators(cfg.data_root, CuratorsFile(curators=out))
    return {"slug": slug, "curator_id": body.curator_id, "assigned": True}


@router.delete("/api/admin/docs/{slug}/curators/{curator_id}")
async def unassign_curator(slug: str, curator_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    cf = read_curators(cfg.data_root)
    out: list[Curator] = []
    for c in cf.curators:
        if c.id == curator_id:
            out.append(
                c.model_copy(update={"assigned_slugs": [s for s in c.assigned_slugs if s != slug]})
            )
        else:
            out.append(c)
    write_curators(cfg.data_root, CuratorsFile(curators=out))
    return {"slug": slug, "curator_id": curator_id, "assigned": False}
