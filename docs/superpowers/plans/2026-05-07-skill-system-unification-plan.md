# Skill System Unification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace today's three fragmented mechanisms (Approach passive,
Approach active, Reactive Capability, Reasons) with one unified `Skill`
abstraction, exposed through a template-driven UI that domain experts can
operate without programming knowledge.

**Architecture:** A `Skill` is a tagged record with `skill_kind` discriminator
routing it through one of five behaviour pipelines. Storage is a single
event-sourced `skills.jsonl` (replacing `approaches.jsonl` + `reasons.jsonl`)
with a one-shot startup migration. UI shows a template-picker for the 5
common patterns plus a power-user fallback.

**Tech Stack:** Python 3.12 (FastAPI, Pydantic v2, ruff, pytest), TypeScript
React (Vite, Tailwind, react-query). Storage: JSONL append-only.

**Spec:** `docs/superpowers/specs/2026-05-07-skill-system-unification-design.md`

**Decisions taken (D-1 through D-6):**
- D-1: claim_background hardcoded path REMOVED, replaced by pre-seeded default Skill
- D-2: 6 templates initially (Aussage anreichern, Such-Anfrage verbessern, Bewertung neu fassen, Lehr-Notiz, Agent-Denkregel, Eigener Skill)
- D-3: "Roh-Daten anzeigen" accordion in every template form
- D-4: Migration runs at service start (eager)
- D-5: Per-template `consumed_by` defaults, editable in power-user mode
- D-6: Skill-run audit kept lightweight, separate `skill_runs.jsonl`

---

## File Structure

### New backend files
- `features/pipelines/local-pdf/src/local_pdf/provenienz/skills.py` — Skill model + storage
- `features/pipelines/local-pdf/src/local_pdf/provenienz/skill_dispatcher.py` — `apply_skills()` central routing
- `features/pipelines/local-pdf/src/local_pdf/provenienz/skill_migration.py` — One-shot approach+reason → skill migration
- `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/skills.py` — REST API for skills
- `features/pipelines/local-pdf/tests/test_provenienz_skills.py` — Skill model + dispatcher tests
- `features/pipelines/local-pdf/tests/test_provenienz_skill_migration.py` — Migration tests
- `features/pipelines/local-pdf/tests/test_router_skills.py` — API tests

### Modified backend files
- `features/pipelines/local-pdf/src/local_pdf/api/app.py` — wire migration + new router
- `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz_approaches.py` — translate to skills.jsonl backed
- `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py` — replace `_gather_guidance` callsites with `apply_skills`, remove hardcoded `_llm_extract_claim_backgrounds`

### New frontend files
- `frontend/src/admin/hooks/useSkills.ts` — react-query hooks
- `frontend/src/admin/provenienz/skills/SkillLibrary.tsx` — list/group page
- `frontend/src/admin/provenienz/skills/SkillCard.tsx` — list-item component
- `frontend/src/admin/provenienz/skills/SkillDetailPanel.tsx` — detail/edit panel
- `frontend/src/admin/provenienz/skills/TemplatePicker.tsx` — modal: pick a template
- `frontend/src/admin/provenienz/skills/templates/EnrichmentForm.tsx`
- `frontend/src/admin/provenienz/skills/templates/PromptOverlayForm.tsx`
- `frontend/src/admin/provenienz/skills/templates/ReactiveForm.tsx`
- `frontend/src/admin/provenienz/skills/templates/NoteForm.tsx`
- `frontend/src/admin/provenienz/skills/templates/AgentRuleForm.tsx`
- `frontend/src/admin/provenienz/skills/templates/CustomForm.tsx` (= ApproachFormModal extracted)

### Modified frontend files
- `frontend/src/admin/routes/Provenienz.tsx` — add `/skills` route
- `frontend/src/admin/provenienz/ApproachLibrary.tsx` — keep as legacy redirect to /skills
- `frontend/src/admin/provenienz/panels/ClaimPanel.tsx` — generic annotation rendering
- `frontend/src/admin/provenienz/panels/SearchResultPanel.tsx` — generic annotation rendering

---

## Phase S-1: Backend Schema + Storage

### Task 1: Skill Pydantic model + types

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/skills.py`
- Test: `features/pipelines/local-pdf/tests/test_provenienz_skills.py`

- [ ] **Step 1: Write the failing tests for the Skill model**

```python
# tests/test_provenienz_skills.py
import pytest
from pydantic import ValidationError

from local_pdf.provenienz.skills import (
    Skill,
    SkillKind,
    SkillPrompt,
    SkillOutput,
    TriggerConditions,
)


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd features/pipelines/local-pdf
uv run pytest tests/test_provenienz_skills.py -v
```
Expected: ImportError / module not found.

- [ ] **Step 3: Implement the model**

```python
# src/local_pdf/provenienz/skills.py
from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field, model_validator


class SkillKind(str, Enum):
    PROMPT_OVERLAY = "prompt-overlay"
    SUBAGENT = "subagent"
    ENRICHMENT = "enrichment"
    REACTIVE = "reactive"
    NOTE = "note"


class TriggerConditions(BaseModel):
    verdicts: list[str] = Field(default_factory=list)
    sentence_regex: list[str] = Field(default_factory=list)
    claim_regex: list[str] = Field(default_factory=list)
    topic_keywords: list[str] = Field(default_factory=list)
    anchor_kinds: list[str] = Field(default_factory=list)
    goal_contains: list[str] = Field(default_factory=list)
    text_contains: list[str] = Field(default_factory=list)


class SkillPrompt(BaseModel):
    free_text: str = ""
    questions: list[str] = Field(default_factory=list)
    domain_rules: str = ""


class SkillOutput(BaseModel):
    annotation_kind: str = ""        # e.g. "claim_background"
    attaches_to: str = ""             # e.g. "claim"
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
    def _validate_kind_specific(self) -> "Skill":
        if self.skill_kind != SkillKind.NOTE and not self.fires_on:
            raise ValueError(
                f"fires_on must be non-empty for skill_kind={self.skill_kind}"
            )
        if self.skill_kind == SkillKind.ENRICHMENT and not self.output.attaches_to:
            raise ValueError(
                "enrichment skills must declare output.attaches_to"
            )
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_provenienz_skills.py -v
```
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/local_pdf/provenienz/skills.py tests/test_provenienz_skills.py
git commit -m "feat(skills): Skill model with kind-specific validation"
```

---

### Task 2: Skill JSONL storage layer

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/provenienz/skills.py`
- Test: `features/pipelines/local-pdf/tests/test_provenienz_skills.py` (extend)

- [ ] **Step 1: Write failing tests for storage operations**

```python
# extend tests/test_provenienz_skills.py
def test_append_and_read_single_skill(tmp_path):
    from local_pdf.provenienz.skills import (
        append_skill_event, read_skills, upsert_skill,
    )
    s = upsert_skill(
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
    from local_pdf.provenienz.skills import upsert_skill
    a = upsert_skill(tmp_path, name="bg", skill_kind=SkillKind.NOTE,
                     fires_on=["evaluate"], prompt=SkillPrompt(free_text="v1"))
    b = upsert_skill(tmp_path, name="bg", skill_kind=SkillKind.NOTE,
                     fires_on=["evaluate"], prompt=SkillPrompt(free_text="v2"))
    assert a.skill_id == b.skill_id
    assert b.version == 2
    out = read_skills(tmp_path)
    assert len(out) == 1
    assert out[0].prompt.free_text == "v2"


def test_tombstone_removes_skill_from_read(tmp_path):
    from local_pdf.provenienz.skills import (
        upsert_skill, tombstone_skill, read_skills,
    )
    s = upsert_skill(tmp_path, name="bg", skill_kind=SkillKind.NOTE,
                    fires_on=["evaluate"], prompt=SkillPrompt(free_text="x"))
    tombstone_skill(tmp_path, s.skill_id)
    out = read_skills(tmp_path)
    assert out == []


def test_read_skills_filters_by_kind(tmp_path):
    from local_pdf.provenienz.skills import upsert_skill, read_skills
    upsert_skill(tmp_path, name="a", skill_kind=SkillKind.NOTE,
                fires_on=["evaluate"], prompt=SkillPrompt(free_text="x"))
    upsert_skill(tmp_path, name="b", skill_kind=SkillKind.PROMPT_OVERLAY,
                fires_on=["evaluate"], prompt=SkillPrompt(free_text="y"))
    notes = read_skills(tmp_path, kind=SkillKind.NOTE)
    assert len(notes) == 1
    assert notes[0].name == "a"


def test_read_skills_filters_by_fires_on(tmp_path):
    from local_pdf.provenienz.skills import upsert_skill, read_skills
    upsert_skill(tmp_path, name="a", skill_kind=SkillKind.NOTE,
                fires_on=["evaluate"], prompt=SkillPrompt(free_text="x"))
    upsert_skill(tmp_path, name="b", skill_kind=SkillKind.NOTE,
                fires_on=["formulate_task"], prompt=SkillPrompt(free_text="y"))
    fired = read_skills(tmp_path, fires_on="evaluate")
    assert len(fired) == 1
    assert fired[0].name == "a"
```

- [ ] **Step 2: Run, expect failures (functions not implemented)**

- [ ] **Step 3: Implement storage functions in `skills.py`**

```python
# extend src/local_pdf/provenienz/skills.py
import json
from datetime import datetime, timezone
from pathlib import Path

from local_pdf.provenienz.storage import new_id


def _skills_path(data_root: Path) -> Path:
    return data_root / "skills" / "skills.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_record(data_root: Path, record: dict) -> None:
    path = _skills_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_skill_event(data_root: Path, skill: Skill) -> Skill:
    _append_record(data_root, skill.model_dump(mode="json"))
    return skill


def tombstone_skill(data_root: Path, skill_id: str) -> None:
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
    items = list(_latest_by_name(data_root).values())
    if enabled_only:
        items = [s for s in items if s.enabled]
    if kind is not None:
        items = [s for s in items if s.skill_kind == kind]
    if fires_on is not None:
        items = [s for s in items if fires_on in s.fires_on]
    items.sort(key=lambda s: s.name)
    return items


def get_skill(data_root: Path, skill_id: str) -> Skill | None:
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
        new = latest.model_copy(update={
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
        })
    return append_skill_event(data_root, new)
```

- [ ] **Step 4: Run tests, expect 5/5 PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): event-sourced JSONL storage with versioned upsert"
```

---

## Phase S-2: Migration

### Task 3: One-shot Approach + Reason → Skill migration

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/skill_migration.py`
- Create: `features/pipelines/local-pdf/tests/test_provenienz_skill_migration.py`

- [ ] **Step 1: Write failing migration tests**

```python
# tests/test_provenienz_skill_migration.py
from pathlib import Path
from local_pdf.provenienz.skills import read_skills, SkillKind
from local_pdf.provenienz.skill_migration import (
    migrate_legacy_to_skills,
    is_migrated,
)


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
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement migration**

```python
# src/local_pdf/provenienz/skill_migration.py
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from local_pdf.provenienz.skills import (
    Skill,
    SkillKind,
    SkillOutput,
    SkillPrompt,
    TriggerConditions,
    append_skill_event,
)
from local_pdf.provenienz.storage import new_id


def is_migrated(data_root: Path) -> bool:
    flag = data_root / "skills" / "_meta.json"
    return flag.exists()


def _set_migrated_flag(data_root: Path) -> None:
    (data_root / "skills").mkdir(parents=True, exist_ok=True)
    (data_root / "skills" / "_meta.json").write_text(
        json.dumps({"migrated_at": datetime.now(timezone.utc).isoformat()})
    )


def _seed_default_claim_background_skill(data_root: Path) -> None:
    now = datetime.now(timezone.utc).isoformat()
    s = Skill(
        skill_id=new_id(),
        name="claim_background",
        version=1,
        enabled=True,
        description=(
            "Auto-extrahiert pro Aussage 2-4 Sätze Hintergrund aus dem "
            "Quell-Chunk: Bezugsgrößen, Voraussetzungen, definierende "
            "Begriffe."
        ),
        created_at=now,
        updated_at=now,
        skill_kind=SkillKind.ENRICHMENT,
        fires_on=["extract_claims"],
        prompt=SkillPrompt(
            questions=[
                "Welche Bezugsgrößen oder Vergleichswerte sind im Chunk genannt?",
                "Werden Voraussetzungen oder Annahmen erwähnt (Auslegung, Betriebspunkt, Zeitraum)?",
                "Welches Einheitensystem oder welcher Standort/Anlage-Typ ist gemeint?",
            ]
        ),
        output=SkillOutput(
            annotation_kind="claim_background",
            attaches_to="claim",
            consumed_by=["formulate_task", "evaluate"],
        ),
    )
    append_skill_event(data_root, s)


def _read_legacy_jsonl(path: Path) -> list[dict]:
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


def _approach_to_skill(rec: dict) -> Skill:
    triggers = rec.get("triggers") or {}
    domain_rules = rec.get("domain_rules") or ""
    if triggers:
        kind = SkillKind.REACTIVE
    elif rec.get("mode") == "active":
        kind = SkillKind.SUBAGENT
    else:
        kind = SkillKind.PROMPT_OVERLAY
    sel = rec.get("selection_criteria") or {}
    conditions = TriggerConditions(
        verdicts=triggers.get("verdicts") or [],
        sentence_regex=triggers.get("sentence_regex") or [],
        claim_regex=triggers.get("claim_regex") or [],
        topic_keywords=triggers.get("topic_keywords") or [],
        anchor_kinds=sel.get("anchor_kinds") or [],
        goal_contains=sel.get("goal_contains") or [],
        text_contains=sel.get("text_contains") or [],
    )
    return Skill(
        skill_id=rec.get("approach_id", new_id()),
        name=rec["name"],
        version=int(rec.get("version", 1)),
        enabled=bool(rec.get("enabled", True)),
        description="",
        created_at=rec.get("created_at", ""),
        updated_at=rec.get("updated_at", ""),
        skill_kind=kind,
        fires_on=list(rec.get("step_kinds") or []),
        conditions=conditions,
        parent_skill=rec.get("parent_capability") or "",
        prompt=SkillPrompt(
            free_text=rec.get("extra_system") or "",
            domain_rules=domain_rules,
        ),
    )


def _reason_to_skill(rec: dict) -> Skill:
    return Skill(
        skill_id=rec.get("reason_id", new_id()),
        name=f"note-{rec.get('reason_id', new_id())[:8]}",
        version=1,
        enabled=True,
        description=rec.get("text", "")[:80],
        created_at=rec.get("created_at", ""),
        updated_at=rec.get("created_at", ""),
        skill_kind=SkillKind.NOTE,
        fires_on=[rec["step_kind"]],
        conditions=TriggerConditions(
            anchor_kinds=rec.get("applies_to_anchor_kinds") or [],
        ),
        prompt=SkillPrompt(free_text=rec.get("text", "")),
    )


def _rename_with_suffix(src: Path) -> None:
    if not src.exists():
        return
    suffix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dst = src.with_suffix(src.suffix + f".migrated-{suffix}")
    src.rename(dst)


def migrate_legacy_to_skills(data_root: Path) -> None:
    if is_migrated(data_root):
        return
    approaches_path = data_root / "provenienz" / "approaches.jsonl"
    reasons_path = data_root / "provenienz" / "reasons.jsonl"

    # Replay approaches: latest non-tombstoned per name (mirrors legacy reader)
    by_name: dict[str, dict] = {}
    name_by_id: dict[str, str] = {}
    suppressed: set[str] = set()
    for rec in _read_legacy_jsonl(approaches_path):
        if rec.get("_tombstone"):
            aid = rec.get("approach_id", "")
            n = name_by_id.get(aid)
            if n is not None:
                suppressed.add(n)
                by_name.pop(n, None)
            continue
        name_by_id[rec["approach_id"]] = rec["name"]
        if rec["name"] in suppressed:
            suppressed.discard(rec["name"])
        by_name[rec["name"]] = rec

    for rec in by_name.values():
        skill = _approach_to_skill(rec)
        append_skill_event(data_root, skill)

    for rec in _read_legacy_jsonl(reasons_path):
        if not rec.get("_tombstone"):
            skill = _reason_to_skill(rec)
            append_skill_event(data_root, skill)

    # Seed default claim_background only if no legacy approach already provides it
    existing_names = {s.name for s in by_name.values()}
    if "claim_background" not in existing_names:
        _seed_default_claim_background_skill(data_root)

    _rename_with_suffix(approaches_path)
    _rename_with_suffix(reasons_path)
    _set_migrated_flag(data_root)
```

- [ ] **Step 4: Run tests, expect 9/9 PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): one-shot migration from approaches+reasons to skills.jsonl"
```

---

### Task 4: Wire migration into app startup

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/app.py`
- Test: extend `tests/test_provenienz_skill_migration.py`

- [ ] **Step 1: Write failing test for startup wiring**

```python
def test_app_startup_runs_migration(tmp_path, monkeypatch):
    """Service start triggers migration if not yet migrated."""
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    (tmp_path / "provenienz").mkdir()
    (tmp_path / "provenienz" / "approaches.jsonl").write_text(
        '{"approach_id":"a1","name":"x","version":1,"step_kinds":["evaluate"],'
        '"extra_system":"r","enabled":true,"mode":"passive","triggers":{},'
        '"parent_capability":"","domain_rules":"",'
        '"created_at":"","updated_at":"","selection_criteria":{}}\n'
    )
    from local_pdf.api.app import build_app
    app = build_app()
    # Just constructing the app should run migration
    from local_pdf.provenienz.skill_migration import is_migrated
    assert is_migrated(tmp_path)
```

- [ ] **Step 2: Run, expect failure (build_app doesn't migrate)**

- [ ] **Step 3: Add migration call in build_app**

Identify the existing build_app() (or app construction equivalent), and after data_root resolution call `migrate_legacy_to_skills(data_root)`. Use try/except + log.warning so migration failure doesn't crash app.

- [ ] **Step 4: Run, expect PASS + all existing app tests still pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): run migration at service start"
```

---

## Phase S-3: Backend Dispatcher

### Task 5: `apply_skills` central routing

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/provenienz/skill_dispatcher.py`
- Test: extend `tests/test_provenienz_skills.py`

- [ ] **Step 1: Write tests for the dispatcher**

```python
# in tests/test_provenienz_skills.py
def test_apply_skills_returns_prompt_overlay_text(tmp_path):
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    from local_pdf.provenienz.skills import upsert_skill
    upsert_skill(tmp_path, name="r", skill_kind=SkillKind.PROMPT_OVERLAY,
                fires_on=["evaluate"],
                prompt=SkillPrompt(free_text="check units"))
    bundle = apply_skills(tmp_path, step_kind="evaluate", anchor=None)
    assert "check units" in bundle.extra_system


def test_apply_skills_filters_by_step_kind(tmp_path):
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    from local_pdf.provenienz.skills import upsert_skill
    upsert_skill(tmp_path, name="a", skill_kind=SkillKind.PROMPT_OVERLAY,
                fires_on=["evaluate"],
                prompt=SkillPrompt(free_text="x"))
    upsert_skill(tmp_path, name="b", skill_kind=SkillKind.PROMPT_OVERLAY,
                fires_on=["formulate_task"],
                prompt=SkillPrompt(free_text="y"))
    bundle = apply_skills(tmp_path, step_kind="evaluate", anchor=None)
    assert "x" in bundle.extra_system
    assert "y" not in bundle.extra_system


def test_apply_skills_returns_notes_separately(tmp_path):
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    from local_pdf.provenienz.skills import upsert_skill
    upsert_skill(tmp_path, name="n", skill_kind=SkillKind.NOTE,
                fires_on=["evaluate"],
                prompt=SkillPrompt(free_text="reminder"))
    bundle = apply_skills(tmp_path, step_kind="evaluate", anchor=None)
    assert any("reminder" in n for n in bundle.notes)
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement dispatcher**

```python
# src/local_pdf/provenienz/skill_dispatcher.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from local_pdf.provenienz.skills import Skill, SkillKind, read_skills


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
    anchor: Optional[object] = None,
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
        if skill.skill_kind == SkillKind.PROMPT_OVERLAY:
            if skill.prompt.free_text:
                out.extra_system += "\n\n" + skill.prompt.free_text
                out.consulted_skill_ids.append(skill.skill_id)
        elif skill.skill_kind == SkillKind.NOTE:
            if skill.prompt.free_text:
                out.notes.append(skill.prompt.free_text)
                out.consulted_skill_ids.append(skill.skill_id)
        # subagent / enrichment / reactive returned via dedicated callers below
    return out


def list_enrichment_skills(
    data_root: Path, *, fires_on: str
) -> list[Skill]:
    return [
        s for s in read_skills(data_root, kind=SkillKind.ENRICHMENT, fires_on=fires_on)
        if s.enabled
    ]


def list_reactive_skills(data_root: Path) -> list[Skill]:
    return [
        s for s in read_skills(data_root, kind=SkillKind.REACTIVE)
        if s.enabled
    ]


def list_subagent_skills(
    data_root: Path, *, fires_on: str
) -> list[Skill]:
    return [
        s for s in read_skills(data_root, kind=SkillKind.SUBAGENT, fires_on=fires_on)
        if s.enabled
    ]
```

- [ ] **Step 4: Run, expect 3/3 PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): central apply_skills dispatcher"
```

---

### Task 6: Replace `_gather_guidance` callsites with `apply_skills`

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py`

- [ ] **Step 1: Add a thin compat shim**

Inside provenienz.py near `_gather_guidance`:

```python
def _gather_guidance_via_skills(data_root, meta, step_kind, *, anchor=None):
    """New skills-backed equivalent of _gather_guidance.

    Returns the same (extra_system, refs) tuple shape so callers don't
    change. References point to skill_ids now."""
    from local_pdf.provenienz.skill_dispatcher import apply_skills
    bundle = apply_skills(
        data_root, step_kind=step_kind, anchor=anchor,
        session_goal=meta.goal if meta else ""
    )
    text = bundle.extra_system
    if bundle.notes:
        text += "\n\n## Lehr-Notizen\n" + "\n".join(f"- {n}" for n in bundle.notes)
    refs = [
        GuidanceRef(kind="skill", id=sid, label="")
        for sid in bundle.consulted_skill_ids
    ]
    return text, refs
```

- [ ] **Step 2: Replace ALL `_gather_guidance(` callsites with `_gather_guidance_via_skills(`**

Use grep to find every callsite. Replace one by one. Run pytest after each replacement.

- [ ] **Step 3: Verify all existing tests pass**

```bash
uv run pytest tests/test_provenienz_*.py -v
```
Expected: same 69 pass / 1 deselect as before.

- [ ] **Step 4: Remove the old `_gather_guidance` function and `_walk_approaches` helper**

(Old code becomes dead. Delete it.)

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(skills): route guidance gathering through skill dispatcher"
```

---

## Phase S-4: Enrichment Runtime

### Task 7: Generic enrichment runner

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py`
- Modify: `features/pipelines/local-pdf/src/local_pdf/provenienz/skill_dispatcher.py`

- [ ] **Step 1: Write tests for enrichment runner**

In `tests/test_provenienz_skills.py`:

```python
def test_run_enrichment_skill_calls_llm_and_returns_per_input_strings(monkeypatch):
    """enrichment skill produces N strings for N inputs."""
    from local_pdf.provenienz.skill_dispatcher import run_enrichment_skill
    from local_pdf.provenienz.skills import Skill, SkillKind, SkillPrompt, SkillOutput
    skill = Skill(
        skill_id="s1", name="bg", version=1,
        skill_kind=SkillKind.ENRICHMENT, fires_on=["extract_claims"],
        prompt=SkillPrompt(questions=["What is X?", "What is Y?"]),
        output=SkillOutput(annotation_kind="claim_background", attaches_to="claim"),
    )

    class _Fake:
        def __init__(self, text): self.text = text
        @property
        def text_(self): return self.text

    class _Client:
        def complete(self, *, messages, model, max_tokens=None, **_):
            class C: text = '["X is Y", "alpha is beta"]'
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
    from local_pdf.provenienz.skills import Skill, SkillKind, SkillPrompt, SkillOutput
    skill = Skill(
        skill_id="s1", name="bg", version=1,
        skill_kind=SkillKind.ENRICHMENT, fires_on=["extract_claims"],
        prompt=SkillPrompt(questions=["?"]),
        output=SkillOutput(annotation_kind="x", attaches_to="claim"),
    )

    class _Client:
        def complete(self, *, messages, model, max_tokens=None, **_):
            class C: text = "not json"
            return C()
    monkeypatch.setattr("local_pdf.provenienz.skill_dispatcher.get_llm_client", lambda: _Client())
    monkeypatch.setattr("local_pdf.provenienz.skill_dispatcher.get_default_model", lambda: "test")
    out = run_enrichment_skill(skill, ["c1", "c2"], chunk_text="x")
    assert out == ["", ""]
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement runner**

In `skill_dispatcher.py`:

```python
import json
from local_pdf.llm import Message, get_default_model, get_llm_client


_ENRICHMENT_SYSTEM_DEFAULT = (
    "Du bekommst N Eingaben und eine Liste von Fragen. Beantworte jede "
    "Frage für jede Eingabe — knapp, in 1-3 deutschen Sätzen pro Eingabe. "
    "Antworte ausschließlich als JSON-Array von Strings (selbe Länge wie "
    "Eingaben), kein Vor- oder Nachtext, kein Markdown."
)


def run_enrichment_skill(
    skill: Skill,
    inputs: list[str],
    *,
    chunk_text: str = "",
    extra_system: str = "",
) -> list[str]:
    """Run an enrichment skill: returns a list of N strings (one per
    input). Empty strings on parse failure or LLM error."""
    if not inputs:
        return []
    questions_block = "\n".join(f"- {q}" for q in skill.prompt.questions)
    system = (
        _ENRICHMENT_SYSTEM_DEFAULT
        + ("\n\n## Domain-Anweisungen\n" + skill.prompt.free_text if skill.prompt.free_text else "")
        + ("\n\n" + extra_system if extra_system else "")
    )
    truncated = chunk_text.strip()[:1500]
    if len(chunk_text) > 1500:
        truncated += " […]"
    chunk_block = (
        f"Quell-Textabschnitt:\n{truncated}\n\n" if truncated else ""
    )
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(inputs))
    user = (
        f"{chunk_block}"
        f"Fragen:\n{questions_block}\n\n"
        f"Eingaben:\n{numbered}\n\n"
        f"JSON-Array (selbe Reihenfolge):"
    )
    try:
        client = get_llm_client()
        completion = client.complete(
            messages=[
                Message(role="system", content=system),
                Message(role="user", content=user),
            ],
            model=get_default_model(),
            max_tokens=2048,
        )
    except Exception:
        return [""] * len(inputs)
    raw = (completion.text or "").strip()
    # Strip ``` fences if present
    if raw.startswith("```"):
        raw = raw.lstrip("`").lstrip("json").strip()
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [""] * len(inputs)
    if not isinstance(parsed, list) or len(parsed) != len(inputs):
        return [""] * len(inputs)
    return [str(x).strip()[:1500] if isinstance(x, str) else "" for x in parsed]
```

- [ ] **Step 4: Run tests, expect 2/2 PASS**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): generic enrichment runner with JSON-array output"
```

---

### Task 8: Replace hardcoded `_llm_extract_claim_backgrounds` with skill-driven path

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz.py`

- [ ] **Step 1: In decide(extract_claims), replace the hardcoded call with skill-driven loop**

```python
# in decide handler, step_kind == "extract_claims" branch, replace
# the existing claim_backgrounds block with:

from local_pdf.provenienz.skill_dispatcher import (
    list_enrichment_skills, run_enrichment_skill,
)

enrichment_skills = list_enrichment_skills(cfg.data_root, fires_on="extract_claims")
# Group results: for each skill, get N strings (one per claim), then we
# spawn one annotation Node per (claim, skill) pair.
skill_results: dict[str, list[str]] = {}  # skill_id -> N results
for skill in enrichment_skills:
    if skill.output.attaches_to != "claim":
        continue
    try:
        out = run_enrichment_skill(
            skill, claim_texts, chunk_text=chunk_text_for_goals
        )
    except Exception as exc:
        _log.warning("enrichment skill %s failed: %s", skill.name, exc)
        out = [""] * len(claim_texts)
    skill_results[skill.skill_id] = out
```

Then after the claim Node is appended, for each enrichment skill spawn an
annotation Node:

```python
for skill in enrichment_skills:
    if skill.output.attaches_to != "claim":
        continue
    results = skill_results.get(skill.skill_id, [])
    text = results[idx] if idx < len(results) else ""
    if not text or not text.strip():
        continue
    bg_node = append_node(sd, Node(
        node_id=new_id(),
        session_id=session_id,
        kind=skill.output.annotation_kind,
        payload={
            "text": text.strip(),
            "claim_node_id": claim.node_id,
            "source_chunk_node_id": anchor_chunk,
            "skill_id": skill.skill_id,
            "skill_name": skill.name,
            "skill_version": skill.version,
        },
        actor="system",
    ))
    spawned_nodes.append(bg_node)
    spawned_edges.append(append_edge(sd, Edge(
        edge_id=new_id(),
        session_id=session_id,
        from_node=bg_node.node_id,
        to_node=claim.node_id,
        kind="enriches",
        reason=None,
        actor="system",
    )))
```

Remove the previously-hardcoded `_llm_extract_claim_backgrounds` function and its call.

- [ ] **Step 2: Run extract_claims tests + provenienz suite**

```bash
uv run pytest tests/test_provenienz_*.py
```
Expected: all pass, including the existing extract_claims wiring tests.

- [ ] **Step 3: Update `_build_decision_context` to read annotations generically**

```python
# Replace the hardcoded claim_background lookup with a generic one
# that respects the consumed_by setting on the producing skill.

from local_pdf.provenienz.skill_dispatcher import list_enrichment_skills

# Inside _build_decision_context, in place of the claim_background block:
relevant_skills = list_enrichment_skills(data_root_arg, fires_on="extract_claims")
# Filter by consumed_by step (the caller's step_kind)
# This requires data_root to be threaded into _build_decision_context.
# Simpler: skip filtering at this layer; consumed_by is enforced by callers.

annotations_for_claim = [
    n for n in nodes
    if n.kind in {s.output.annotation_kind for s in relevant_skills if "evaluate" in s.output.consumed_by}
    and n.payload.get("claim_node_id") == claim.node_id
]
# Pass relevant ones into the prompt
for ann in annotations_for_claim:
    text = str(ann.payload.get("text", "")).strip()
    label = str(ann.payload.get("skill_name", ann.kind))
    if text:
        parts.append(f"## {label.upper()}\n{text}")
```

(Refactor as needed: thread data_root through _build_decision_context, or use a
pre-computed allowlist. Pick the simpler approach.)

- [ ] **Step 4: Verify the system end-to-end**

Manual check (described in QA-section). Run pytest.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): claim_background extraction now driven by enrichment skill"
```

---

## Phase S-5: Backend API

### Task 9: REST endpoints for skills

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/skills.py`
- Test: `features/pipelines/local-pdf/tests/test_router_skills.py`

- [ ] **Step 1: Write failing API tests**

Use existing TestClient pattern from test_router_provenienz_pin_approach.py. Cover:

```python
def test_list_skills_empty(client): ...
def test_create_skill_via_post(client): ...
def test_patch_skill_bumps_version(client): ...
def test_delete_skill_tombstones(client): ...
def test_get_skill_by_id(client): ...
def test_create_rejects_invalid_kind_specific_combo(client):
    """e.g. enrichment without attaches_to → 400."""
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: Implement router**

```python
# src/local_pdf/api/routers/admin/skills.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from local_pdf.provenienz.skills import (
    Skill, SkillKind, SkillOutput, SkillPrompt,
    TriggerConditions, get_skill, read_skills, tombstone_skill, upsert_skill,
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


@router.get("/api/admin/provenienz/skills")
async def list_skills(request: Request) -> list[dict]:
    cfg = request.app.state.config
    return [s.model_dump(mode="json") for s in read_skills(cfg.data_root, enabled_only=False)]


@router.post("/api/admin/provenienz/skills", status_code=201)
async def create_skill(body: SkillCreate, request: Request) -> dict:
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
    return s.model_dump(mode="json")


@router.patch("/api/admin/provenienz/skills/{skill_id}")
async def patch_skill(skill_id: str, body: SkillPatch, request: Request) -> dict:
    cfg = request.app.state.config
    current = get_skill(cfg.data_root, skill_id)
    if current is None:
        raise HTTPException(404, f"skill not found: {skill_id}")
    merged = current.model_copy(update={
        k: v for k, v in body.model_dump(exclude_none=True).items()
    })
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
    return new_skill.model_dump(mode="json")


@router.delete("/api/admin/provenienz/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, request: Request) -> None:
    cfg = request.app.state.config
    current = get_skill(cfg.data_root, skill_id)
    if current is None:
        raise HTTPException(404, f"skill not found: {skill_id}")
    tombstone_skill(cfg.data_root, skill_id)
```

Wire the router in `app.py`.

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills): REST API for skill CRUD"
```

---

### Task 10: Translate legacy `/approaches` API to read from skills

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/provenienz_approaches.py`

- [ ] **Step 1: Write a test that ensures legacy responses still work after migration**

```python
def test_legacy_approaches_endpoint_returns_skills_translated(client_with_skills):
    r = client_with_skills.get("/api/admin/provenienz/approaches", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    data = r.json()
    # After migration, every skill is visible as a legacy-Approach record
    assert any(a["name"] == "claim_background" for a in data)
```

- [ ] **Step 2: Add a translation layer**

```python
# inside provenienz_approaches.py
def _skill_to_legacy_approach_dict(s: Skill) -> dict:
    """Render a skill record in the legacy Approach shape so
    existing UI calls keep working until the new UI lands."""
    return {
        "approach_id": s.skill_id,
        "name": s.name,
        "version": s.version,
        "step_kinds": s.fires_on,
        "extra_system": s.prompt.free_text,
        "enabled": s.enabled,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "selection_criteria": {
            "anchor_kinds": s.conditions.anchor_kinds,
            "goal_contains": s.conditions.goal_contains,
            "text_contains": s.conditions.text_contains,
        },
        "mode": "active" if s.skill_kind == SkillKind.SUBAGENT else "passive",
        "triggers": {
            k: v for k, v in {
                "verdicts": s.conditions.verdicts,
                "sentence_regex": s.conditions.sentence_regex,
                "claim_regex": s.conditions.claim_regex,
                "topic_keywords": s.conditions.topic_keywords,
            }.items() if v
        },
        "parent_capability": s.parent_skill,
        "domain_rules": s.prompt.domain_rules,
    }
```

Replace `read_approaches` calls with `read_skills` + translation. Same for create/patch/delete (write to skills.jsonl, return legacy shape).

- [ ] **Step 3: Tests pass**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(skills): legacy approaches endpoint backed by skills.jsonl"
```

---

## Phase S-6: Frontend Skill Library

### Task 11: useSkills hook

**Files:**
- Create: `frontend/src/admin/hooks/useSkills.ts`

- [ ] **Step 1: Implement the hook**

```typescript
// frontend/src/admin/hooks/useSkills.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchOk, apiBase } from "./fetchOk";

export type SkillKind =
  | "prompt-overlay"
  | "subagent"
  | "enrichment"
  | "reactive"
  | "note";

export interface TriggerConditions {
  verdicts: string[];
  sentence_regex: string[];
  claim_regex: string[];
  topic_keywords: string[];
  anchor_kinds: string[];
  goal_contains: string[];
  text_contains: string[];
}

export interface SkillPrompt {
  free_text: string;
  questions: string[];
  domain_rules: string;
}

export interface SkillOutput {
  annotation_kind: string;
  attaches_to: string;
  consumed_by: string[];
}

export interface Skill {
  skill_id: string;
  name: string;
  version: number;
  enabled: boolean;
  description: string;
  created_at: string;
  updated_at: string;
  skill_kind: SkillKind;
  fires_on: string[];
  conditions: TriggerConditions;
  parent_skill: string;
  prompt: SkillPrompt;
  output: SkillOutput;
}

export function useSkills(token: string) {
  return useQuery<Skill[]>({
    queryKey: ["provenienz", "skills"],
    enabled: !!token,
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills`,
        { method: "GET" },
        token,
      );
      return (await r.json()) as Skill[];
    },
  });
}

export function useCreateSkill(token: string) {
  const qc = useQueryClient();
  return useMutation<Skill, Error, Omit<Skill, "skill_id" | "version" | "created_at" | "updated_at">>({
    mutationFn: async (body) => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/provenienz/skills`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        token,
      );
      return (await r.json()) as Skill;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["provenienz", "skills"] }),
  });
}

// patch + delete analogously…
```

- [ ] **Step 2: Run `npx tsc --noEmit`, expect clean**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(skills/fe): useSkills react-query hooks"
```

---

### Task 12: SkillLibrary page

**Files:**
- Create: `frontend/src/admin/provenienz/skills/SkillLibrary.tsx`
- Modify: `frontend/src/admin/routes/Provenienz.tsx`

- [ ] **Step 1: Implement SkillLibrary**

Group skills by skill_kind. Use existing styling patterns from ApproachLibrary. Each card shows: name, kind-badge, fires_on, enabled toggle, edit button.

- [ ] **Step 2: Add `/skills` route in Provenienz**

- [ ] **Step 3: Verify in browser**

```bash
cd frontend && npm run dev
# Open http://localhost:5173/admin/provenienz/skills
```

Skills (post-migration) should appear grouped. tsc clean.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(skills/fe): SkillLibrary page with kind-grouped cards"
```

---

### Task 13: TemplatePicker modal

**Files:**
- Create: `frontend/src/admin/provenienz/skills/TemplatePicker.tsx`

- [ ] **Step 1: Implement the picker**

Six clickable cards. Each onClick opens a specific template form modal (next task).

- [ ] **Step 2: Wire into SkillLibrary's "Neu" button**

- [ ] **Step 3: Visual check + tsc**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(skills/fe): TemplatePicker with 6 template cards"
```

---

### Task 14: Template form — Enrichment ("📜 Aussage anreichern")

**Files:**
- Create: `frontend/src/admin/provenienz/skills/templates/EnrichmentForm.tsx`

- [ ] **Step 1: Implement form**

3-4 fields:
- Name
- Questions (textarea, one per line)
- Optional: goal_contains keywords

Hidden: skill_kind=enrichment, fires_on=['extract_claims'], output={annotation_kind: 'claim_background', attaches_to: 'claim', consumed_by: ['formulate_task', 'evaluate']}

Add "Roh-Daten anzeigen" accordion at the bottom (D-3).

- [ ] **Step 2: Submit creates skill via useCreateSkill**

- [ ] **Step 3: Visual check, tsc**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(skills/fe): EnrichmentForm template with 3 visible fields"
```

---

### Task 15: Template forms — PromptOverlay, Reactive, Note, AgentRule

**Files:**
- Create one form per template (4 files)

- [ ] **Step 1: Implement each**

For each: identify the 2-4 visible fields, hide the rest (defaulted via the template).

- [ ] **Step 2: tsc clean per form**

- [ ] **Step 3: Commit each separately**

```bash
git commit -m "feat(skills/fe): PromptOverlayForm template"
git commit -m "feat(skills/fe): ReactiveForm template"
git commit -m "feat(skills/fe): NoteForm template"
git commit -m "feat(skills/fe): AgentRuleForm template"
```

---

### Task 16: Template form — Custom (= ApproachFormModal extracted)

**Files:**
- Create: `frontend/src/admin/provenienz/skills/templates/CustomForm.tsx`
- Modify: existing `ApproachFormModal.tsx` mostly moves here

- [ ] **Step 1: Move ApproachFormModal contents into CustomForm**

Adapt to write to skills API instead of approaches API. All fields visible.

- [ ] **Step 2: tsc clean, behaviour parity check**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(skills/fe): CustomForm template (full power-user form)"
```

---

### Task 17: SkillDetailPanel + skill-aware ClaimPanel/SearchResultPanel

**Files:**
- Create: `frontend/src/admin/provenienz/skills/SkillDetailPanel.tsx`
- Modify: `frontend/src/admin/provenienz/panels/ClaimPanel.tsx`
- Modify: `frontend/src/admin/provenienz/panels/SearchResultPanel.tsx`

- [ ] **Step 1: SkillDetailPanel — opens when user clicks skill card**

Shows config, recent activity (skill_runs.jsonl entries), Edit/Disable/Delete.

- [ ] **Step 2: Generic annotation rendering in ClaimPanel**

Replace hardcoded backgroundText logic with a loop over ALL Nodes whose
kind matches an `enrichment` skill that consumed_by includes the current
panel's context, and whose payload.claim_node_id matches.

- [ ] **Step 3: Same for SearchResultPanel (annotations attached to search_result)**

- [ ] **Step 4: tsc + visual check**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(skills/fe): SkillDetailPanel + generic annotation rendering"
```

---

## Phase S-7: Audit + Cleanup

### Task 18: skill_runs.jsonl audit

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/provenienz/skill_dispatcher.py`

- [ ] **Step 1: Write tests for run-audit**

```python
def test_skill_run_appended_to_audit_file(tmp_path, monkeypatch):
    # Configure dispatcher to append a record after each enrichment call
    # Verify (skill_id, n_inputs, success_count, ts) end up in skill_runs.jsonl
    ...
```

- [ ] **Step 2: Implement audit append in `run_enrichment_skill`**

- [ ] **Step 3: Tests pass**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(skills): per-run audit log in skill_runs.jsonl"
```

---

### Task 19: Remove dead code (legacy approaches/reasons read paths)

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/provenienz/approaches.py` — keep only types as legacy translation surface, drop `_walk_approaches`, `_gather_guidance`, etc.
- Modify: `features/pipelines/local-pdf/src/local_pdf/provenienz/reasons.py` — drop or wrap

- [ ] **Step 1: grep usages of dead functions, ensure no callers**

```bash
grep -rn '_walk_approaches\|_gather_guidance\b' src/ tests/
```
Expected: no hits outside the modules that define them.

- [ ] **Step 2: Delete dead functions**

- [ ] **Step 3: Run full pytest**

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(skills): remove dead approach/reason walk helpers"
```

---

### Task 20: Manual test plan + final lint

- [ ] **Step 1: Walk the manual test plan in section 8**

Document results in PR description.

- [ ] **Step 2: Run all linters + types**

```bash
cd features/pipelines/local-pdf && uv run ruff check src/ tests/
cd features/pipelines/local-pdf && uv run mypy src/local_pdf/provenienz/skills.py src/local_pdf/provenienz/skill_dispatcher.py src/local_pdf/provenienz/skill_migration.py src/local_pdf/api/routers/admin/skills.py
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Use `superpowers:requesting-code-review`** for a final independent review

- [ ] **Step 4: Use `superpowers:finishing-a-development-branch`** to wrap up

---

## Manual Test Plan (run after Phase S-6 lands)

1. **Migration: existing data preserved**
   - Take a session with the current `compare-numbers` + `nachzerfallsleistung_konservativ` Approaches
   - Restart backend
   - Verify `skills.jsonl` exists, contains both as `reactive` skills
   - Verify `approaches.jsonl.migrated-2026-05-XX` exists
   - Verify Skill-Bibliothek shows them grouped under "⚖ Bewertung neu fassen"
   - Trigger an evaluate → reactive scan still fires + capability_gate appears

2. **Template-driven skill creation**
   - Click "Neu" → "📜 Aussage anreichern"
   - Name: "Reaktor-Hintergrund"
   - Questions: 4 lines (Reaktor-Typ, Werte-Klasse, Zeitpunkt, Einheit)
   - Save
   - Verify skills.jsonl has new record with skill_kind=enrichment
   - Trigger extract_claims on a chunk
   - Verify each claim has a `claim_background` Node (with skill_id pointing to new skill)
   - Open Aussage-Panel: cyan section shows the 4 questions answered
   - formulate_task: prompt should contain "## CLAIM_BACKGROUND" block

3. **Note skill workflow**
   - Click "Neu" → "📌 Lehr-Notiz" → step=evaluate → text="Always check unit conversion"
   - Trigger evaluate
   - Verify the audit shows guidance_consulted with the new skill_id
   - Verify system_prompt_used contains the note text

4. **Reactive flip still works (regression)**
   - Use existing compare-numbers reactive skill (now in skills.jsonl)
   - Trigger evaluate with a number-mismatch case
   - Verify capability_gate appears, re-evaluate works

5. **Power-user form parity**
   - Click "Neu" → "🛠 Eigener Skill"
   - Verify all fields available (= heutige ApproachFormModal-Funktionalität)

---

## Out-of-scope (separate plans if needed)

- Skill marketplace / import-export
- Skill chains (Skill A's output feeds Skill B's input)
- External tool calls (web search, REST APIs)
- Live LLM-call preview in form
- Visual workflow builder

---

**Plan-Status: Draft, await user approval before execution.**
