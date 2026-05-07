"""One-shot migration: legacy approaches + reasons → unified skills.jsonl.

Runs at startup (wired in by Task 4). Idempotent via a flag file at
``{data_root}/skills/_meta.json`` — once present, the migration is a
no-op. The legacy event logs are preserved with a
``.migrated-YYYY-MM-DD`` suffix so the prior data is not lost.

Mapping rules (per the unification plan):
  - Approach with non-empty ``triggers`` → ``REACTIVE`` skill
  - Approach with ``mode == "active"`` → ``SUBAGENT`` skill
  - Otherwise an Approach → ``PROMPT_OVERLAY`` skill
  - Reason → ``NOTE`` skill

If no legacy approach already provides a ``claim_background`` skill,
a factory-default enrichment skill is seeded so the out-of-the-box
behaviour matches the prior hardcoded claim-background path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003

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
    """True iff the migration flag file exists for this data_root."""
    flag = data_root / "skills" / "_meta.json"
    return flag.exists()


def _set_migrated_flag(data_root: Path) -> None:
    (data_root / "skills").mkdir(parents=True, exist_ok=True)
    (data_root / "skills" / "_meta.json").write_text(
        json.dumps({"migrated_at": datetime.now(UTC).isoformat()})
    )


def _seed_default_claim_background_skill(data_root: Path) -> None:
    now = datetime.now(UTC).isoformat()
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
                (
                    "Werden Voraussetzungen oder Annahmen erwähnt "
                    "(Auslegung, Betriebspunkt, Zeitraum)?"
                ),
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
    prose = rec.get("reason_text") or rec.get("text", "")
    return Skill(
        skill_id=rec.get("reason_id", new_id()),
        name=f"note-{rec.get('reason_id', new_id())[:8]}",
        version=1,
        enabled=True,
        description=prose[:80],
        created_at=rec.get("created_at", ""),
        updated_at=rec.get("created_at", ""),
        skill_kind=SkillKind.NOTE,
        fires_on=[rec["step_kind"]],
        conditions=TriggerConditions(),
        prompt=SkillPrompt(free_text=prose),
    )


def _rename_with_suffix(src: Path) -> None:
    if not src.exists():
        return
    suffix = datetime.now(UTC).strftime("%Y-%m-%d")
    dst = src.with_suffix(src.suffix + f".migrated-{suffix}")
    src.rename(dst)


def migrate_legacy_to_skills(data_root: Path) -> None:
    """Translate legacy approaches.jsonl + reasons.jsonl to skills.jsonl.

    No-op if already migrated (``_meta.json`` exists).

    Approaches replay mirrors ``approaches._latest_by_name``: tombstones
    suppress by ``approach_id`` (look up name from prior records);
    re-creating a tombstoned name un-suppresses it. The migration only
    persists the final, non-tombstoned set.
    """
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

    reason_records = [r for r in _read_legacy_jsonl(reasons_path) if not r.get("_tombstone")]
    for rec in reason_records:
        skill = _reason_to_skill(rec)
        append_skill_event(data_root, skill)

    # Seed factory-default claim_background skill only when there is no
    # legacy data at all — otherwise a curator's existing setup would
    # be augmented with a skill they never asked for. If a legacy
    # approach happens to be named ``claim_background``, the migration
    # already produced the skill above and we must not duplicate it.
    has_legacy = bool(by_name) or bool(reason_records)
    existing_names = {s["name"] for s in by_name.values()}
    if not has_legacy and "claim_background" not in existing_names:
        _seed_default_claim_background_skill(data_root)

    _rename_with_suffix(approaches_path)
    _rename_with_suffix(reasons_path)
    _set_migrated_flag(data_root)
