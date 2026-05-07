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


def test_append_and_read_single_skill(tmp_path):
    from local_pdf.provenienz.skills import read_skills, upsert_skill

    upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="watch units"),
    )
    out = read_skills(tmp_path)
    assert len(out) == 1
    assert out[0].name == "bg"
    assert out[0].version == 1


def test_upsert_bumps_version(tmp_path):
    from local_pdf.provenienz.skills import read_skills, upsert_skill

    a = upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="v1"),
    )
    b = upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="v2"),
    )
    assert a.skill_id == b.skill_id
    assert b.version == 2
    out = read_skills(tmp_path)
    assert len(out) == 1
    assert out[0].prompt.free_text == "v2"


def test_tombstone_removes_skill_from_read(tmp_path):
    from local_pdf.provenienz.skills import (
        read_skills,
        tombstone_skill,
        upsert_skill,
    )

    s = upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
    )
    tombstone_skill(tmp_path, s.skill_id)
    out = read_skills(tmp_path)
    assert out == []


def test_read_skills_filters_by_kind(tmp_path):
    from local_pdf.provenienz.skills import read_skills, upsert_skill

    upsert_skill(
        tmp_path,
        name="a",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
    )
    upsert_skill(
        tmp_path,
        name="b",
        skill_kind=SkillKind.PROMPT_OVERLAY,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="y"),
    )
    notes = read_skills(tmp_path, kind=SkillKind.NOTE)
    assert len(notes) == 1
    assert notes[0].name == "a"


def test_read_skills_filters_by_fires_on(tmp_path):
    from local_pdf.provenienz.skills import read_skills, upsert_skill

    upsert_skill(
        tmp_path,
        name="a",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
    )
    upsert_skill(
        tmp_path,
        name="b",
        skill_kind=SkillKind.NOTE,
        fires_on=["formulate_task"],
        prompt=SkillPrompt(free_text="y"),
    )
    fired = read_skills(tmp_path, fires_on="evaluate")
    assert len(fired) == 1
    assert fired[0].name == "a"


def test_tombstone_then_recreate_unsuppresses_name(tmp_path):
    """A tombstoned name can be re-created — the suppression flag is
    cleared on the next live record with the same name."""
    from local_pdf.provenienz.skills import (
        read_skills,
        tombstone_skill,
        upsert_skill,
    )

    s1 = upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="v1"),
    )
    tombstone_skill(tmp_path, s1.skill_id)
    assert read_skills(tmp_path) == []
    s2 = upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="reborn"),
    )
    out = read_skills(tmp_path)
    assert len(out) == 1
    assert out[0].name == "bg"
    assert out[0].prompt.free_text == "reborn"
    # Re-created records get a fresh skill_id; the old one stays tombstoned.
    assert s2.skill_id != s1.skill_id


def test_get_skill_on_tombstoned_id_returns_none(tmp_path):
    from local_pdf.provenienz.skills import (
        get_skill,
        tombstone_skill,
        upsert_skill,
    )

    s = upsert_skill(
        tmp_path,
        name="bg",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
    )
    tombstone_skill(tmp_path, s.skill_id)
    assert get_skill(tmp_path, s.skill_id) is None


def test_read_skills_with_enabled_only_false_includes_disabled(tmp_path):
    """The admin UI lists disabled skills too; enabled_only=False covers
    that path."""
    from local_pdf.provenienz.skills import read_skills, upsert_skill

    upsert_skill(
        tmp_path,
        name="active",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
        enabled=True,
    )
    upsert_skill(
        tmp_path,
        name="off",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="y"),
        enabled=False,
    )
    enabled_default = read_skills(tmp_path)
    assert len(enabled_default) == 1
    assert enabled_default[0].name == "active"
    full = read_skills(tmp_path, enabled_only=False)
    assert len(full) == 2
    assert {s.name for s in full} == {"active", "off"}


def test_apply_skills_returns_prompt_overlay_text(tmp_path):
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    from local_pdf.provenienz.skills import upsert_skill

    upsert_skill(
        tmp_path,
        name="r",
        skill_kind=SkillKind.PROMPT_OVERLAY,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="check units"),
    )
    bundle = apply_skills(tmp_path, step_kind="evaluate", anchor=None)
    assert "check units" in bundle.extra_system


def test_apply_skills_filters_by_step_kind(tmp_path):
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    from local_pdf.provenienz.skills import upsert_skill

    upsert_skill(
        tmp_path,
        name="a",
        skill_kind=SkillKind.PROMPT_OVERLAY,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="x"),
    )
    upsert_skill(
        tmp_path,
        name="b",
        skill_kind=SkillKind.PROMPT_OVERLAY,
        fires_on=["formulate_task"],
        prompt=SkillPrompt(free_text="y"),
    )
    bundle = apply_skills(tmp_path, step_kind="evaluate", anchor=None)
    assert "x" in bundle.extra_system
    assert "y" not in bundle.extra_system


def test_apply_skills_returns_notes_separately(tmp_path):
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    from local_pdf.provenienz.skills import upsert_skill

    upsert_skill(
        tmp_path,
        name="n",
        skill_kind=SkillKind.NOTE,
        fires_on=["evaluate"],
        prompt=SkillPrompt(free_text="reminder"),
    )
    bundle = apply_skills(tmp_path, step_kind="evaluate", anchor=None)
    assert any("reminder" in n for n in bundle.notes)


def test_run_enrichment_skill_calls_llm_and_returns_per_input_strings(monkeypatch):
    """enrichment skill produces N strings for N inputs."""
    from local_pdf.provenienz.skill_dispatcher import run_enrichment_skill
    from local_pdf.provenienz.skills import Skill, SkillKind, SkillOutput, SkillPrompt

    skill = Skill(
        skill_id="s1",
        name="bg",
        version=1,
        skill_kind=SkillKind.ENRICHMENT,
        fires_on=["extract_claims"],
        prompt=SkillPrompt(questions=["What is X?", "What is Y?"]),
        output=SkillOutput(annotation_kind="claim_background", attaches_to="claim"),
    )

    class _Fake:
        def __init__(self, text):
            self.text = text

        @property
        def text_(self):
            return self.text

    class _Client:
        def complete(self, *, messages, model, max_tokens=None, **_):
            class C:
                text = '["X is Y", "alpha is beta"]'

            return C()

    monkeypatch.setattr(
        "local_pdf.provenienz.skill_dispatcher.get_llm_client",
        lambda: _Client(),
    )
    monkeypatch.setattr(
        "local_pdf.provenienz.skill_dispatcher.get_default_model",
        lambda: "test",
    )
    out = run_enrichment_skill(skill, ["c1", "c2"], chunk_text="surrounding")
    assert out == ["X is Y", "alpha is beta"]


def test_run_enrichment_skill_handles_parse_failure(monkeypatch):
    from local_pdf.provenienz.skill_dispatcher import run_enrichment_skill
    from local_pdf.provenienz.skills import Skill, SkillKind, SkillOutput, SkillPrompt

    skill = Skill(
        skill_id="s1",
        name="bg",
        version=1,
        skill_kind=SkillKind.ENRICHMENT,
        fires_on=["extract_claims"],
        prompt=SkillPrompt(questions=["?"]),
        output=SkillOutput(annotation_kind="x", attaches_to="claim"),
    )

    class _Client:
        def complete(self, *, messages, model, max_tokens=None, **_):
            class C:
                text = "not json"

            return C()

    monkeypatch.setattr("local_pdf.provenienz.skill_dispatcher.get_llm_client", lambda: _Client())
    monkeypatch.setattr("local_pdf.provenienz.skill_dispatcher.get_default_model", lambda: "test")
    out = run_enrichment_skill(skill, ["c1", "c2"], chunk_text="x")
    assert out == ["", ""]
