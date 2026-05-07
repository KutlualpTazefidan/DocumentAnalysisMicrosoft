from local_pdf.provenienz.skill_migration import (
    is_migrated,
    migrate_legacy_to_skills,
)
from local_pdf.provenienz.skills import SkillKind, read_skills


def test_migration_no_op_when_skills_file_present(tmp_path):
    """Migration must NOT run if skills.jsonl already exists."""
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "skills.jsonl").write_text("")
    (tmp_path / "skills" / "_meta.json").write_text('{"migrated_at": "x"}')
    (tmp_path / "provenienz").mkdir()
    (tmp_path / "provenienz" / "approaches.jsonl").write_text(
        '{"approach_id":"a1","name":"a","version":1,"step_kinds":["evaluate"],'
        '"extra_system":"x","enabled":true,"created_at":"","updated_at":""}\n'
    )
    migrate_legacy_to_skills(tmp_path)
    # approaches.jsonl is NOT renamed
    assert (tmp_path / "provenienz" / "approaches.jsonl").exists()
    # No skills imported
    assert read_skills(tmp_path) == []


def test_migration_translates_passive_approach_to_prompt_overlay(tmp_path):
    (tmp_path / "provenienz").mkdir()
    (tmp_path / "provenienz" / "approaches.jsonl").write_text(
        '{"approach_id":"a1","name":"my-rule","version":1,'
        '"step_kinds":["evaluate"],"extra_system":"watch units",'
        '"enabled":true,"mode":"passive","triggers":{},'
        '"parent_capability":"","domain_rules":"",'
        '"created_at":"2026-01-01","updated_at":"2026-01-01",'
        '"selection_criteria":{}}\n'
    )
    migrate_legacy_to_skills(tmp_path)
    skills = read_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].skill_kind == SkillKind.PROMPT_OVERLAY
    assert skills[0].name == "my-rule"
    assert skills[0].prompt.free_text == "watch units"
    assert skills[0].fires_on == ["evaluate"]


def test_migration_translates_active_approach_to_subagent(tmp_path):
    (tmp_path / "provenienz").mkdir()
    (tmp_path / "provenienz" / "approaches.jsonl").write_text(
        '{"approach_id":"a1","name":"deep","version":1,'
        '"step_kinds":["next_step"],"extra_system":"think hard",'
        '"enabled":true,"mode":"active","triggers":{},'
        '"parent_capability":"","domain_rules":"",'
        '"created_at":"","updated_at":"","selection_criteria":{}}\n'
    )
    migrate_legacy_to_skills(tmp_path)
    skills = read_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].skill_kind == SkillKind.SUBAGENT


def test_migration_translates_reactive_capability(tmp_path):
    (tmp_path / "provenienz").mkdir()
    (tmp_path / "provenienz" / "approaches.jsonl").write_text(
        '{"approach_id":"a1","name":"compare-numbers","version":1,'
        '"step_kinds":["evaluate"],"extra_system":"","enabled":true,'
        '"mode":"passive","triggers":{"verdicts":["contradicts"]},'
        '"parent_capability":"","domain_rules":"hold conservatism",'
        '"created_at":"","updated_at":"","selection_criteria":{}}\n'
    )
    migrate_legacy_to_skills(tmp_path)
    skills = read_skills(tmp_path)
    assert skills[0].skill_kind == SkillKind.REACTIVE
    assert skills[0].conditions.verdicts == ["contradicts"]
    assert skills[0].prompt.domain_rules == "hold conservatism"


def test_migration_translates_reasons_to_notes(tmp_path):
    (tmp_path / "provenienz").mkdir()
    (tmp_path / "provenienz" / "reasons.jsonl").write_text(
        '{"reason_id":"r1","step_kind":"evaluate","text":"check unit",'
        '"applies_to_anchor_kinds":["search_result"],'
        '"created_at":"","author":"human"}\n'
    )
    migrate_legacy_to_skills(tmp_path)
    skills = read_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].skill_kind == SkillKind.NOTE
    assert skills[0].prompt.free_text == "check unit"
    assert skills[0].fires_on == ["evaluate"]


def test_migration_preserves_legacy_files_with_renamed_suffix(tmp_path):
    (tmp_path / "provenienz").mkdir()
    src = tmp_path / "provenienz" / "approaches.jsonl"
    src.write_text(
        '{"approach_id":"a1","name":"x","version":1,"step_kinds":["evaluate"],'
        '"extra_system":"","enabled":true,"mode":"passive","triggers":{},'
        '"parent_capability":"","domain_rules":"",'
        '"created_at":"","updated_at":"","selection_criteria":{}}\n'
    )
    migrate_legacy_to_skills(tmp_path)
    assert not src.exists()
    legacy = list((tmp_path / "provenienz").glob("approaches.jsonl.migrated-*"))
    assert len(legacy) == 1


def test_migration_seeds_default_claim_background_skill(tmp_path):
    """A factory-default 'claim_background' enrichment skill is seeded if no
    legacy data exists, so out-of-the-box behaviour matches the prior
    hardcoded path."""
    migrate_legacy_to_skills(tmp_path)
    skills = read_skills(tmp_path)
    assert any(s.name == "claim_background" for s in skills)
    bg = next(s for s in skills if s.name == "claim_background")
    assert bg.skill_kind == SkillKind.ENRICHMENT
    assert bg.fires_on == ["extract_claims"]
    assert bg.output.attaches_to == "claim"
    assert "formulate_task" in bg.output.consumed_by
    assert "evaluate" in bg.output.consumed_by


def test_migration_idempotent(tmp_path):
    migrate_legacy_to_skills(tmp_path)
    skills_first = read_skills(tmp_path)
    migrate_legacy_to_skills(tmp_path)
    skills_second = read_skills(tmp_path)
    assert [s.skill_id for s in skills_first] == [s.skill_id for s in skills_second]


def test_is_migrated_flag_returns_true_after_run(tmp_path):
    assert is_migrated(tmp_path) is False
    migrate_legacy_to_skills(tmp_path)
    assert is_migrated(tmp_path) is True
