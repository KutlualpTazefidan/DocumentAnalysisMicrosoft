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
    cfg = request.app.state.config
    return [_dump(s) for s in read_skills(cfg.data_root, enabled_only=False)]


@router.post("/api/admin/provenienz/skills", status_code=201)
async def create_skill(body: SkillCreate, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    s = upsert_skill(
        cfg.data_root,
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
    cfg = request.app.state.config
    s = get_skill(cfg.data_root, skill_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    return _dump(s)


@router.patch("/api/admin/provenienz/skills/{skill_id}")
async def patch_skill(skill_id: str, body: SkillPatch, request: Request) -> dict[str, Any]:
    cfg = request.app.state.config
    current = get_skill(cfg.data_root, skill_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    merged = current.model_copy(update=dict(body.model_dump(exclude_none=True)))
    new_skill = upsert_skill(
        cfg.data_root,
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
    cfg = request.app.state.config
    current = get_skill(cfg.data_root, skill_id)
    if current is None:
        raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
    tombstone_skill(cfg.data_root, skill_id)
