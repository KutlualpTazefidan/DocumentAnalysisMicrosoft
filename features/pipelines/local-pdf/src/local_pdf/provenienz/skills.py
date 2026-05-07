"""Unified Skill model: kind-tagged guidance records for the provenienz audit graph.

The skill_kind enum collapses what used to be a zoo of overlapping concepts
(prompt overlays, sub-agent expertise, enrichment annotations, reactive
domain rules, and free-form curator notes) into a single record schema.
Each kind constrains which fields are required:

  - PROMPT_OVERLAY  : non-empty fires_on; prompt text injected into a
                      step's system prompt.
  - SUBAGENT        : non-empty fires_on; runs as a separate LLM call.
  - ENRICHMENT      : non-empty fires_on; output.attaches_to declares
                      the anchor kind the annotation pins to.
  - REACTIVE        : non-empty fires_on; conditions match an evaluation's
                      verdict / sentence text / claim text.
  - NOTE            : free-form curator note; fires_on may be empty
                      (the only globally-stored kind).

Storage is event-sourced JSONL at
``{data_root}/skills/skills.jsonl`` (mirrors
``provenienz/approaches.py``): each line is either a full Skill
record (latest by *name* wins on read) or a tombstone
``{"skill_id": "...", "_tombstone": true}``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path  # noqa: TC003

from pydantic import BaseModel, Field, model_validator

from local_pdf.provenienz.storage import new_id


class SkillKind(StrEnum):
    PROMPT_OVERLAY = "prompt-overlay"
    SUBAGENT = "subagent"
    ENRICHMENT = "enrichment"
    REACTIVE = "reactive"
    NOTE = "note"


class TriggerConditions(BaseModel):
    """AND-across-keys, OR-within-each-list trigger predicates."""

    verdicts: list[str] = Field(default_factory=list)
    sentence_regex: list[str] = Field(default_factory=list)
    claim_regex: list[str] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    anchor_kinds: list[str] = Field(default_factory=list)
    goal_contains: list[str] = Field(default_factory=list)
    text_contains: list[str] = Field(default_factory=list)


class SkillPrompt(BaseModel):
    """Prompt fragments injected into the consuming step's LLM call."""

    free_text: str = ""
    questions: list[str] = Field(default_factory=list)
    domain_rules: str = ""


class SkillOutput(BaseModel):
    """Where the skill's product lands in the audit graph."""

    annotation_kind: str = ""
    attaches_to: str = ""
    consumed_by: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    skill_id: str
    name: str
    version: int
    enabled: bool = True
    description: str = ""
    created_at: str = ""
    updated_at: str = ""

    skill_kind: SkillKind
    fires_on: list[str] = Field(default_factory=list)
    conditions: TriggerConditions = Field(default_factory=TriggerConditions)
    parent_skill: str = ""
    prompt: SkillPrompt = Field(default_factory=SkillPrompt)
    output: SkillOutput = Field(default_factory=SkillOutput)

    @model_validator(mode="after")
    def _validate_kind_specific(self) -> Skill:
        if self.skill_kind != SkillKind.NOTE and not self.fires_on:
            raise ValueError(f"fires_on must be non-empty for skill_kind={self.skill_kind}")
        if self.skill_kind == SkillKind.ENRICHMENT and not self.output.attaches_to:
            raise ValueError("enrichment skills must declare output.attaches_to")
        return self


def _skills_path(data_root: Path) -> Path:
    return data_root / "skills" / "skills.jsonl"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _append_record(data_root: Path, record: dict) -> None:
    path = _skills_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_skill_event(data_root: Path, skill: Skill) -> Skill:
    """Append a versioned Skill record verbatim."""
    _append_record(data_root, skill.model_dump(mode="json"))
    return skill


def tombstone_skill(data_root: Path, skill_id: str) -> None:
    """Append a tombstone so subsequent reads suppress this skill."""
    _append_record(data_root, {"skill_id": skill_id, "_tombstone": True})


def _read_all_records(data_root: Path) -> list[dict]:
    path = _skills_path(data_root)
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _latest_by_name(data_root: Path) -> dict[str, Skill]:
    """Replay the event log; latest non-tombstoned record per *name* wins.

    Tombstones suppress the skill by skill_id (look up name from prior
    records, then drop that name). Re-creating a tombstoned name
    un-suppresses it.
    """
    by_name: dict[str, Skill] = {}
    name_by_id: dict[str, str] = {}
    suppressed: set[str] = set()
    for rec in _read_all_records(data_root):
        if rec.get("_tombstone"):
            sid = rec.get("skill_id", "")
            n = name_by_id.get(sid)
            if n is not None:
                suppressed.add(n)
                by_name.pop(n, None)
            continue
        s = Skill.model_validate(rec)
        name_by_id[s.skill_id] = s.name
        if s.name in suppressed:
            suppressed.discard(s.name)
        by_name[s.name] = s
    return by_name


def read_skills(
    data_root: Path,
    *,
    kind: SkillKind | None = None,
    fires_on: str | None = None,
    enabled_only: bool = True,
) -> list[Skill]:
    """Return latest record per name, sorted by name.

    Drops tombstoned names. By default also drops disabled skills, and
    optionally filters by *kind* and/or *fires_on* (membership in the
    skill's fires_on list).
    """
    items = list(_latest_by_name(data_root).values())
    if enabled_only:
        items = [s for s in items if s.enabled]
    if kind is not None:
        items = [s for s in items if s.skill_kind == kind]
    if fires_on is not None:
        items = [s for s in items if fires_on in s.fires_on]
    items.sort(key=lambda s: s.name)
    return items


def read_skill_events(
    data_root: Path,
    *,
    kind: SkillKind | None = None,
) -> list[Skill]:
    """Return every non-tombstoned skill record in file (insertion)
    order, with no name-dedup.

    Use this for append-only skill kinds (e.g. NOTE) where ``read_skills``'s
    ``_latest_by_name`` collapse would drop earlier records. ``_now()``
    has only second-level granularity, so callers that need to preserve
    write order across fast bursts must use this reader, not sort by
    ``created_at``.
    """
    tombstoned: set[str] = set()
    records: list[Skill] = []
    for rec in _read_all_records(data_root):
        if rec.get("_tombstone"):
            sid = rec.get("skill_id", "")
            if sid:
                tombstoned.add(sid)
            continue
        s = Skill.model_validate(rec)
        if s.skill_id in tombstoned:
            continue
        if kind is not None and s.skill_kind != kind:
            continue
        records.append(s)
    return records


def get_skill(data_root: Path, skill_id: str) -> Skill | None:
    """Return the latest record for *skill_id*, or None if missing or
    tombstoned."""
    for s in _latest_by_name(data_root).values():
        if s.skill_id == skill_id:
            return s
    return None


def upsert_skill(
    data_root: Path,
    *,
    name: str,
    skill_kind: SkillKind,
    fires_on: list[str],
    prompt: SkillPrompt,
    enabled: bool = True,
    description: str = "",
    conditions: TriggerConditions | None = None,
    parent_skill: str = "",
    output: SkillOutput | None = None,
) -> Skill:
    """Create or bump-version a skill by *name*.

    First write at version=1. Subsequent writes copy the existing
    skill_id forward and increment version.
    """
    latest = _latest_by_name(data_root).get(name)
    now = _now()
    if latest is None:
        new = Skill(
            skill_id=new_id(),
            name=name,
            version=1,
            enabled=enabled,
            description=description,
            created_at=now,
            updated_at=now,
            skill_kind=skill_kind,
            fires_on=list(fires_on),
            conditions=conditions or TriggerConditions(),
            parent_skill=parent_skill,
            prompt=prompt,
            output=output or SkillOutput(),
        )
    else:
        new = latest.model_copy(
            update={
                "version": latest.version + 1,
                "enabled": enabled,
                "description": description,
                "updated_at": now,
                "skill_kind": skill_kind,
                "fires_on": list(fires_on),
                "conditions": conditions or latest.conditions,
                "parent_skill": parent_skill,
                "prompt": prompt,
                "output": output or latest.output,
            }
        )
    return append_skill_event(data_root, new)
