"""Skill library CRUD routes (Stage 6.4).

Unified successor to :mod:`provenienz_approaches`: curators author
kind-tagged skills (prompt-overlay / subagent / enrichment / reactive /
note) here. Storage is event-sourced JSONL at
``{data_root}/skills/skills.jsonl`` (see :mod:`local_pdf.provenienz.skills`).

Auth is enforced by the global X-Auth-Token middleware in
:mod:`local_pdf.api.auth`; admin role is required for all
``/api/admin/*`` paths.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from local_pdf.auth.tenant_root import tenant_data_root, tenant_slug_from_request
from local_pdf.provenienz.skills import (
    Skill,
    SkillKind,
    SkillOutput,
    SkillPrompt,
    TriggerConditions,
    get_skill,
    read_skills,
    tombstone_skill,
    upsert_skill,
)

router = APIRouter()


def _tr(request: Request):
    """Tenant-aware data_root for the active request. Cookie-mode
    users in tenant != default get data_root/tenants/{slug}/; legacy
    callers see the bare data_root."""
    raw = request.app.state.config.data_root
    return tenant_data_root(raw, tenant_slug_from_request(request))


class SkillCreate(BaseModel):
    name: str
    skill_kind: SkillKind
    fires_on: list[str]
    prompt: SkillPrompt
    enabled: bool = True
    description: str = ""
    conditions: TriggerConditions = Field(default_factory=TriggerConditions)
    parent_skill: str = ""
    output: SkillOutput = Field(default_factory=SkillOutput)


class SkillPatch(BaseModel):
    skill_kind: SkillKind | None = None
    fires_on: list[str] | None = None
    prompt: SkillPrompt | None = None
    enabled: bool | None = None
    description: str | None = None
    conditions: TriggerConditions | None = None
    parent_skill: str | None = None
    output: SkillOutput | None = None


def _dump(s: Skill) -> dict[str, Any]:
    """Serialize a Skill to a JSON-mode dict, narrowing the type for mypy."""
    return dict(s.model_dump(mode="json"))


@router.get("/api/admin/provenienz/skills")
async def list_skills(request: Request) -> list[dict[str, Any]]:
    """List all skills (including disabled) for the admin UI."""
    return [_dump(s) for s in read_skills(_tr(request), enabled_only=False)]


@router.post("/api/admin/provenienz/skills", status_code=201)
async def create_skill(body: SkillCreate, request: Request) -> dict[str, Any]:
    s = upsert_skill(
        _tr(request),
        name=body.name,
        skill_kind=body.skill_kind,
        fires_on=body.fires_on,
        prompt=body.prompt,
        enabled=body.enabled,
        description=body.description,
        conditions=body.conditions,
        parent_skill=body.parent_skill,
        output=body.output,
    )
    return _dump(s)


@router.get("/api/admin/provenienz/skills/{skill_id}")
async def get_one_skill(skill_id: str, request: Request) -> dict[str, Any]:
    s = get_skill(_tr(request), skill_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    return _dump(s)


@router.patch("/api/admin/provenienz/skills/{skill_id}")
async def patch_skill(skill_id: str, body: SkillPatch, request: Request) -> dict[str, Any]:
    current = get_skill(_tr(request), skill_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    merged = current.model_copy(update=dict(body.model_dump(exclude_none=True)))
    new_skill = upsert_skill(
        _tr(request),
        name=current.name,
        skill_kind=merged.skill_kind,
        fires_on=merged.fires_on,
        prompt=merged.prompt,
        enabled=merged.enabled,
        description=merged.description,
        conditions=merged.conditions,
        parent_skill=merged.parent_skill,
        output=merged.output,
    )
    return _dump(new_skill)


@router.delete("/api/admin/provenienz/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, request: Request) -> None:
    current = get_skill(_tr(request), skill_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    tombstone_skill(_tr(request), skill_id)


@router.get("/api/admin/provenienz/skills/{skill_id}/runs")
async def list_skill_runs(skill_id: str, request: Request) -> list[dict[str, Any]]:
    """Return the most recent runs for ``skill_id`` (newest first, capped at 50).

    Sources ``{data_root}/skills/skill_runs.jsonl``. Non-enrichment skills
    typically have no runs — the endpoint returns ``[]`` then.
    """
    from local_pdf.provenienz.skill_dispatcher import read_skill_runs

    return read_skill_runs(_tr(request), skill_id=skill_id, last_n=50)
