"""Approach library CRUD routes (Stage 6.3).

Curators author named, versioned system-prompt overlays here. Sessions
pin one or more approach IDs via routes in :mod:`provenienz`. On every
LLM step, pinned + step-kind-matching + enabled approaches are
prepended to the helper's system prompt.

Kept in its own module so :mod:`provenienz` doesn't keep ballooning.

Storage routes through ``skills.jsonl`` (the unified skill store) but
the wire shape is preserved for the legacy UI: each Skill is rendered
back into a legacy Approach dict. The translation lives in
:func:`_skill_to_legacy_approach_dict`. Once the new skill UI lands
the route layer can be deleted (Phase S-6).
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


class CreateApproachRequest(BaseModel):
    name: str
    step_kinds: list[str]
    extra_system: str
    selection_criteria: dict[str, Any] = Field(default_factory=dict)
    mode: str = "passive"
    triggers: dict[str, Any] = Field(default_factory=dict)
    parent_capability: str = ""
    domain_rules: str = ""


class PatchApproachRequest(BaseModel):
    enabled: bool | None = None
    extra_system: str | None = None
    step_kinds: list[str] | None = None
    selection_criteria: dict[str, Any] | None = None
    mode: str | None = None
    triggers: dict[str, Any] | None = None
    parent_capability: str | None = None
    domain_rules: str | None = None


class ApproachResponse(BaseModel):
    approach_id: str
    name: str
    version: int
    step_kinds: list[str]
    extra_system: str
    enabled: bool
    created_at: str
    updated_at: str
    selection_criteria: dict[str, Any] = Field(default_factory=dict)
    mode: str = "passive"
    triggers: dict[str, Any] = Field(default_factory=dict)
    parent_capability: str = ""
    domain_rules: str = ""


def _skill_to_legacy_approach_dict(s: Skill) -> dict:
    """Render a unified Skill record in the legacy Approach shape so
    existing UI calls keep working until the new skill UI lands.

    The reverse mapping (legacy → SkillKind) lives in
    :func:`_legacy_to_skill_kind`; the two MUST stay symmetric.
    """
    return {
        "approach_id": s.skill_id,
        "name": s.name,
        "version": s.version,
        "step_kinds": list(s.fires_on),
        "extra_system": s.prompt.free_text,
        "enabled": s.enabled,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "selection_criteria": {
            "anchor_kinds": list(s.conditions.anchor_kinds),
            "goal_contains": list(s.conditions.goal_contains),
            "text_contains": list(s.conditions.text_contains),
        },
        "mode": "active" if s.skill_kind == SkillKind.SUBAGENT else "passive",
        "triggers": {
            k: v
            for k, v in {
                "verdicts": list(s.conditions.verdicts),
                "sentence_regex": list(s.conditions.sentence_regex),
                "claim_regex": list(s.conditions.claim_regex),
                "topic_keywords": list(s.conditions.topic_keywords),
            }.items()
            if v
        },
        "parent_capability": s.parent_skill,
        "domain_rules": s.prompt.domain_rules,
    }


def _legacy_to_skill_kind(mode: str, triggers: dict[str, Any]) -> SkillKind:
    """Mirror of ``skill_migration._approach_to_skill``'s kind decision.

    Kept in sync there: triggers > active > prompt-overlay.
    """
    if triggers:
        return SkillKind.REACTIVE
    if mode == "active":
        return SkillKind.SUBAGENT
    return SkillKind.PROMPT_OVERLAY


def _build_conditions(
    *,
    selection_criteria: dict[str, Any],
    triggers: dict[str, Any],
) -> TriggerConditions:
    return TriggerConditions(
        verdicts=list(triggers.get("verdicts") or []),
        sentence_regex=list(triggers.get("sentence_regex") or []),
        claim_regex=list(triggers.get("claim_regex") or []),
        topic_keywords=list(triggers.get("topic_keywords") or []),
        anchor_kinds=list(selection_criteria.get("anchor_kinds") or []),
        goal_contains=list(selection_criteria.get("goal_contains") or []),
        text_contains=list(selection_criteria.get("text_contains") or []),
    )


def _to_response(s: Skill) -> ApproachResponse:
    return ApproachResponse(**_skill_to_legacy_approach_dict(s))


_LEGACY_APPROACH_KINDS = {
    SkillKind.PROMPT_OVERLAY,
    SkillKind.SUBAGENT,
    SkillKind.REACTIVE,
}


@router.get("/api/admin/provenienz/approaches")
async def list_approaches(
    request: Request,
    step_kind: str | None = None,
    enabled_only: bool = True,
) -> dict:
    cfg = request.app.state.config
    items = read_skills(cfg.data_root, fires_on=step_kind, enabled_only=enabled_only)
    # Legacy callers see only the kinds that originated as approaches:
    # NOTE (former reasons) and ENRICHMENT (seeded factory defaults like
    # claim_background) must stay invisible to the legacy library.
    items = [s for s in items if s.skill_kind in _LEGACY_APPROACH_KINDS]
    return {"approaches": [_to_response(s).model_dump() for s in items]}


@router.post("/api/admin/provenienz/approaches", status_code=201)
async def create_approach(body: CreateApproachRequest, request: Request) -> dict:
    cfg = request.app.state.config
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not body.step_kinds:
        raise HTTPException(status_code=400, detail="step_kinds must be non-empty")
    triggers = dict(body.triggers or {})
    selection_criteria = dict(body.selection_criteria or {})
    mode = body.mode or "passive"
    s = upsert_skill(
        cfg.data_root,
        name=name,
        skill_kind=_legacy_to_skill_kind(mode, triggers),
        fires_on=list(body.step_kinds),
        prompt=SkillPrompt(
            free_text=body.extra_system or "",
            domain_rules=body.domain_rules or "",
        ),
        enabled=True,
        conditions=_build_conditions(
            selection_criteria=selection_criteria,
            triggers=triggers,
        ),
        parent_skill=body.parent_capability or "",
        output=SkillOutput(),
    )
    return {"approach": _to_response(s).model_dump()}


@router.patch("/api/admin/provenienz/approaches/{approach_id}")
async def patch_approach(approach_id: str, body: PatchApproachRequest, request: Request) -> dict:
    cfg = request.app.state.config
    current = get_skill(cfg.data_root, approach_id)
    if current is None or current.skill_kind == SkillKind.NOTE:
        raise HTTPException(status_code=404, detail=f"approach not found: {approach_id}")

    new_enabled = current.enabled if body.enabled is None else bool(body.enabled)
    new_extra = current.prompt.free_text if body.extra_system is None else body.extra_system
    new_kinds = list(current.fires_on) if body.step_kinds is None else list(body.step_kinds)
    if not new_kinds:
        raise HTTPException(status_code=400, detail="step_kinds must be non-empty")

    # Re-derive selection_criteria + triggers from current Skill if the
    # patch doesn't touch them; otherwise take the patched dict verbatim.
    current_selection = {
        "anchor_kinds": list(current.conditions.anchor_kinds),
        "goal_contains": list(current.conditions.goal_contains),
        "text_contains": list(current.conditions.text_contains),
    }
    current_triggers = {
        k: v
        for k, v in {
            "verdicts": list(current.conditions.verdicts),
            "sentence_regex": list(current.conditions.sentence_regex),
            "claim_regex": list(current.conditions.claim_regex),
            "topic_keywords": list(current.conditions.topic_keywords),
        }.items()
        if v
    }
    new_criteria = (
        dict(current_selection)
        if body.selection_criteria is None
        else dict(body.selection_criteria)
    )
    new_triggers = dict(current_triggers) if body.triggers is None else dict(body.triggers)

    # Mode is encoded in skill_kind. Recover the legacy mode if the
    # patch doesn't touch it.
    current_mode = "active" if current.skill_kind == SkillKind.SUBAGENT else "passive"
    new_mode = current_mode if body.mode is None else body.mode

    new_parent = current.parent_skill if body.parent_capability is None else body.parent_capability
    new_domain_rules = (
        current.prompt.domain_rules if body.domain_rules is None else body.domain_rules
    )

    s = upsert_skill(
        cfg.data_root,
        name=current.name,
        skill_kind=_legacy_to_skill_kind(new_mode, new_triggers),
        fires_on=new_kinds,
        prompt=SkillPrompt(
            free_text=new_extra,
            questions=list(current.prompt.questions),
            domain_rules=new_domain_rules,
        ),
        enabled=new_enabled,
        description=current.description,
        conditions=_build_conditions(
            selection_criteria=new_criteria,
            triggers=new_triggers,
        ),
        parent_skill=new_parent,
        output=current.output,
    )
    return {"approach": _to_response(s).model_dump()}


@router.delete("/api/admin/provenienz/approaches/{approach_id}")
async def remove_approach(approach_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    current = get_skill(cfg.data_root, approach_id)
    if current is None or current.skill_kind == SkillKind.NOTE:
        raise HTTPException(status_code=404, detail=f"approach not found: {approach_id}")
    tombstone_skill(cfg.data_root, approach_id)
    return {"ok": True}
