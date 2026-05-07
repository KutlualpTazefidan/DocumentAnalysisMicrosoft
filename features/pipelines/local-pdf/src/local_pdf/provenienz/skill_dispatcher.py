from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from local_pdf.provenienz.skills import Skill, SkillKind, read_skills

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class SkillBundle:
    """Result of running apply_skills() — what the caller injects into
    the LLM call's system prompt + side-channel arrays."""

    extra_system: str = ""
    notes: list[str] = field(default_factory=list)
    consulted_skill_ids: list[str] = field(default_factory=list)
    matched_reactive_skills: list[Skill] = field(default_factory=list)


def apply_skills(
    data_root: Path,
    *,
    step_kind: str,
    anchor: object | None = None,
    session_goal: str = "",
) -> SkillBundle:
    """Walk skills.jsonl, return the parts that fire for this step.

    - prompt-overlay skills → concatenated to extra_system
    - note skills → returned as a list (caller decides format)
    - subagent skills → caller must invoke separately (return list of Skill)
    - enrichment skills → caller must invoke separately
    - reactive skills → caller scans matched_reactive_skills
    """
    out = SkillBundle()
    for skill in read_skills(data_root, fires_on=step_kind):
        if not skill.enabled:
            continue
        if skill.skill_kind == SkillKind.PROMPT_OVERLAY and skill.prompt.free_text:
            out.extra_system += "\n\n" + skill.prompt.free_text
            out.consulted_skill_ids.append(skill.skill_id)
        elif skill.skill_kind == SkillKind.NOTE and skill.prompt.free_text:
            out.notes.append(skill.prompt.free_text)
            out.consulted_skill_ids.append(skill.skill_id)
        # subagent / enrichment / reactive returned via dedicated callers below
    return out


def list_enrichment_skills(data_root: Path, *, fires_on: str) -> list[Skill]:
    return [
        s for s in read_skills(data_root, kind=SkillKind.ENRICHMENT, fires_on=fires_on) if s.enabled
    ]


def list_reactive_skills(data_root: Path) -> list[Skill]:
    return [s for s in read_skills(data_root, kind=SkillKind.REACTIVE) if s.enabled]


def list_subagent_skills(data_root: Path, *, fires_on: str) -> list[Skill]:
    return [
        s for s in read_skills(data_root, kind=SkillKind.SUBAGENT, fires_on=fires_on) if s.enabled
    ]
