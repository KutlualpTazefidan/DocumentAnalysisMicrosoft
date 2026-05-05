"""Approach library CRUD routes (Stage 6.3).

Curators author named, versioned system-prompt overlays here. Sessions
pin one or more approach IDs via routes in :mod:`provenienz`. On every
LLM step, pinned + step-kind-matching + enabled approaches are
prepended to the helper's system prompt.

Kept in its own module so :mod:`provenienz` doesn't keep ballooning.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from local_pdf.provenienz.approaches import (
    Approach,
    delete_approach,
    get_approach,
    read_approaches,
    upsert_approach,
)

router = APIRouter()


class CreateApproachRequest(BaseModel):
    name: str
    step_kinds: list[str]
    extra_system: str


class PatchApproachRequest(BaseModel):
    enabled: bool | None = None
    extra_system: str | None = None
    step_kinds: list[str] | None = None


class ApproachResponse(BaseModel):
    approach_id: str
    name: str
    version: int
    step_kinds: list[str]
    extra_system: str
    enabled: bool
    created_at: str
    updated_at: str


def _to_response(a: Approach) -> ApproachResponse:
    return ApproachResponse(**a.__dict__)


@router.get("/api/admin/provenienz/approaches")
async def list_approaches(
    request: Request,
    step_kind: str | None = None,
    enabled_only: bool = True,
) -> dict:
    cfg = request.app.state.config
    items = read_approaches(cfg.data_root, step_kind=step_kind, enabled_only=enabled_only)
    return {"approaches": [_to_response(a).model_dump() for a in items]}


@router.post("/api/admin/provenienz/approaches", status_code=201)
async def create_approach(body: CreateApproachRequest, request: Request) -> dict:
    cfg = request.app.state.config
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not body.step_kinds:
        raise HTTPException(status_code=400, detail="step_kinds must be non-empty")
    a = upsert_approach(
        cfg.data_root,
        name=name,
        step_kinds=list(body.step_kinds),
        extra_system=body.extra_system or "",
    )
    return {"approach": _to_response(a).model_dump()}


@router.patch("/api/admin/provenienz/approaches/{approach_id}")
async def patch_approach(approach_id: str, body: PatchApproachRequest, request: Request) -> dict:
    cfg = request.app.state.config
    current = get_approach(cfg.data_root, approach_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"approach not found: {approach_id}")
    new_enabled = current.enabled if body.enabled is None else bool(body.enabled)
    new_extra = current.extra_system if body.extra_system is None else body.extra_system
    new_kinds = list(current.step_kinds) if body.step_kinds is None else list(body.step_kinds)
    if not new_kinds:
        raise HTTPException(status_code=400, detail="step_kinds must be non-empty")
    a = upsert_approach(
        cfg.data_root,
        name=current.name,
        step_kinds=new_kinds,
        extra_system=new_extra,
        enabled=new_enabled,
    )
    return {"approach": _to_response(a).model_dump()}


@router.delete("/api/admin/provenienz/approaches/{approach_id}")
async def remove_approach(approach_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    ok = delete_approach(cfg.data_root, approach_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"approach not found: {approach_id}")
    return {"ok": True}
