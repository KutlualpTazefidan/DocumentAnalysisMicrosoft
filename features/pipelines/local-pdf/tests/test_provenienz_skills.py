"""Skill model: kind enum + kind-specific validation."""

from __future__ import annotations

import pytest
from local_pdf.provenienz.skills import (
    Skill,
    SkillKind,
    SkillOutput,
    SkillPrompt,
    TriggerConditions,
)
from pydantic import ValidationError


def test_skill_kind_is_string_enum():
    assert SkillKind.PROMPT_OVERLAY.value == "prompt-overlay"
    assert SkillKind.SUBAGENT.value == "subagent"
    assert SkillKind.ENRICHMENT.value == "enrichment"
    assert SkillKind.REACTIVE.value == "reactive"
    assert SkillKind.NOTE.value == "note"


def test_skill_minimal_construction_with_defaults():
    s = Skill(
        skill_id="01K1",
        name="test",
        version=1,
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
    )
    assert s.enabled is True
    assert s.description == ""
    assert s.parent_skill == ""
    assert s.conditions.verdicts == []
    assert s.output.consumed_by == []


def test_skill_rejects_empty_fires_on_for_non_global_kinds():
    """fires_on may not be empty for non-note skills."""
    with pytest.raises(ValidationError):
        Skill(
            skill_id="01K2",
            name="bad",
            version=1,
            skill_kind=SkillKind.PROMPT_OVERLAY,
            fires_on=[],
            prompt=SkillPrompt(free_text="x"),
        )


def test_enrichment_skill_requires_attaches_to():
    """enrichment skills must declare their anchor kind."""
    with pytest.raises(ValidationError):
        Skill(
            skill_id="01K3",
            name="bad",
            version=1,
            skill_kind=SkillKind.ENRICHMENT,
            fires_on=["extract_claims"],
            prompt=SkillPrompt(questions=["?"]),
            output=SkillOutput(annotation_kind="x"),  # no attaches_to
        )


def test_skill_serialises_round_trip():
    s = Skill(
        skill_id="01K4",
        name="round-trip",
        version=2,
        skill_kind=SkillKind.REACTIVE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(domain_rules="rule"),
        conditions=TriggerConditions(verdicts=["contradicts"]),
    )
    raw = s.model_dump()
    s2 = Skill.model_validate(raw)
    assert s2 == s
