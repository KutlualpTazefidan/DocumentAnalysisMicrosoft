"""Explicit guidance corpus: named, versioned system-prompt overlays.

Stored at ``{LOCAL_PDF_DATA_ROOT}/provenienz/approaches.jsonl`` (global,
not per-session). Append-only event log: each line is either a full
Approach record (latest record per *name* wins on read) or a tombstone
``{"_tombstone": true, "approach_id": "..."}`` that suppresses an
approach from subsequent reads.

Curators author approaches via the admin CRUD HTTP routes; sessions
pin approach IDs they want active. On every LLM step the
session-pinned, step-kind-matching, enabled approaches are prepended
to the helper's system prompt (alongside the implicit reason corpus
from Stage 6.2) and recorded as ``GuidanceRef(kind="approach", ...)``
on the resulting action_proposal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Any

from local_pdf.provenienz.storage import _now, new_id


@dataclass(frozen=True)
class Approach:
    approach_id: str
    name: str
    version: int
    step_kinds: list[str] = field(default_factory=list)
    extra_system: str = ""
    enabled: bool = True
    created_at: str = ""
    updated_at: str = ""
    # Auto-selection rules. Empty dict = manual-pin only (legacy
    # behaviour). Non-empty = the planner auto-pins this approach
    # whenever every present rule matches the current anchor + goal.
    # Recognised keys:
    #   ``anchor_kinds``  : list[str]  - allowed anchor.kind values
    #   ``goal_contains`` : list[str]  - any-match keywords in session goal
    #   ``text_contains`` : list[str]  - any-match keywords in anchor text
    # AND-logic across keys; OR-logic within each list.
    selection_criteria: dict[str, Any] = field(default_factory=dict)
    # Phase-3 multi-agent flag. ``passive`` = legacy behaviour: the
    # approach's extra_system is text-injected into the Meta-Planner's
    # prompt. ``active`` = the next_step pipeline runs a SEPARATE LLM
    # call per active approach (sub-agent reasoning + step suggestion),
    # then a Coordinator LLM merges all sub-agent outputs + the
    # Meta-Plan into a final decision. Default ``passive`` preserves
    # behaviour for every existing record.
    mode: str = "passive"
    # Reactive-Capability layer: triggers + hierarchy + domain_rules.
    # Empty triggers dict = legacy approach (not reactive). When
    # set, this approach is matched against an evaluation's output
    # (verdict + per-Satz texts + claim text) and may load extra
    # domain expertise into a re-evaluation prompt.
    #
    # Recognised ``triggers`` keys (AND-across, OR-within):
    #   ``verdicts``        : list[str] — only fire when verdict in this list
    #   ``sentence_regex``  : list[str] — regex patterns matched against any
    #                        sentence text
    #   ``claim_regex``     : list[str] — regex against the upstream claim
    #   ``topic_keywords``  : list[str] — substring match on combined text
    triggers: dict[str, Any] = field(default_factory=dict)
    # Two-level hierarchy. Empty string = top-level capability.
    # Non-empty = sub-skill, only loaded when the parent fires AND
    # this sub's own triggers also match.
    parent_capability: str = ""
    # Free-text block injected into re-evaluate's extra_system. The
    # author's domain expertise (e.g. "Aufrundung der Wärmeleistung
    # ist konservativ wenn echter Wert kleiner...").
    domain_rules: str = ""


def _approaches_path(data_root: Path) -> Path:
    return data_root / "provenienz" / "approaches.jsonl"


def _append_record(data_root: Path, record: dict) -> None:
    path = _approaches_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_approach_event(data_root: Path, approach: Approach) -> Approach:
    """Append a versioned Approach record verbatim."""
    _append_record(data_root, dict(approach.__dict__))
    return approach


def _read_all_records(data_root: Path) -> list[dict]:
    path = _approaches_path(data_root)
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _latest_by_name(data_root: Path) -> dict[str, Approach]:
    """Replay the event log; latest non-tombstoned record per *name* wins.

    Tombstones suppress the approach by approach_id (look up name from
    prior records, then drop that name).
    """
    by_name: dict[str, Approach] = {}
    name_by_id: dict[str, str] = {}
    suppressed_names: set[str] = set()
    for rec in _read_all_records(data_root):
        if rec.get("_tombstone"):
            aid = rec.get("approach_id", "")
            n = name_by_id.get(aid)
            if n is not None:
                suppressed_names.add(n)
                by_name.pop(n, None)
            continue
        a = Approach(**rec)
        name_by_id[a.approach_id] = a.name
        if a.name in suppressed_names:
            # Re-creating an approach under a tombstoned name un-suppresses it.
            suppressed_names.discard(a.name)
        by_name[a.name] = a
    return by_name


def upsert_approach(
    data_root: Path,
    *,
    name: str,
    step_kinds: list[str],
    extra_system: str,
    enabled: bool = True,
    selection_criteria: dict[str, Any] | None = None,
    mode: str | None = None,
    triggers: dict[str, Any] | None = None,
    parent_capability: str | None = None,
    domain_rules: str | None = None,
) -> Approach:
    """Create or bump-version an approach by *name*.

    First write at version=1. Subsequent writes copy the existing
    approach_id forward and increment version. ``selection_criteria``
    and ``mode`` default to the previous version's value on update,
    or to their schema defaults on create.
    """
    latest = _latest_by_name(data_root).get(name)
    now = _now()
    if latest is None:
        new = Approach(
            approach_id=new_id(),
            name=name,
            version=1,
            step_kinds=list(step_kinds),
            extra_system=extra_system,
            enabled=enabled,
            created_at=now,
            updated_at=now,
            selection_criteria=dict(selection_criteria or {}),
            mode=(mode or "passive"),
            triggers=dict(triggers or {}),
            parent_capability=(parent_capability or ""),
            domain_rules=(domain_rules or ""),
        )
    else:
        new = Approach(
            approach_id=latest.approach_id,
            name=name,
            version=latest.version + 1,
            step_kinds=list(step_kinds),
            extra_system=extra_system,
            enabled=enabled,
            created_at=latest.created_at or now,
            updated_at=now,
            selection_criteria=dict(
                selection_criteria if selection_criteria is not None else latest.selection_criteria
            ),
            mode=(mode if mode is not None else latest.mode),
            triggers=dict(triggers if triggers is not None else latest.triggers),
            parent_capability=(
                parent_capability if parent_capability is not None else latest.parent_capability
            ),
            domain_rules=(domain_rules if domain_rules is not None else latest.domain_rules),
        )
    append_approach_event(data_root, new)
    # Write-through to the unified skill store so the new
    # apply_skills() reader picks up legacy-API-created approaches.
    # Kept alongside the legacy file path; Task 19 removes the duplicate.
    _write_through_to_skills(data_root, new)
    return new


def _write_through_to_skills(data_root: Path, a: Approach) -> None:
    """Mirror this Approach as a Skill in skills.jsonl.

    The Skill's ``skill_id`` is set to the Approach's ``approach_id`` so
    that the legacy ``/approaches`` API (which now reads skills.jsonl)
    can find it by approach_id without a separate index. Lazy import
    avoids a circular dependency at module load.
    """
    from local_pdf.provenienz.skills import (
        Skill,
        SkillKind,
        SkillOutput,
        SkillPrompt,
        TriggerConditions,
        append_skill_event,
    )

    if a.triggers:
        kind = SkillKind.REACTIVE
    elif a.mode == "active":
        kind = SkillKind.SUBAGENT
    else:
        kind = SkillKind.PROMPT_OVERLAY

    skill = Skill(
        skill_id=a.approach_id,
        name=a.name,
        version=a.version,
        enabled=a.enabled,
        description="",
        created_at=a.created_at,
        updated_at=a.updated_at,
        skill_kind=kind,
        fires_on=list(a.step_kinds),
        conditions=TriggerConditions(
            verdicts=list(a.triggers.get("verdicts") or []),
            sentence_regex=list(a.triggers.get("sentence_regex") or []),
            claim_regex=list(a.triggers.get("claim_regex") or []),
            topic_keywords=list(a.triggers.get("topic_keywords") or []),
            anchor_kinds=list(a.selection_criteria.get("anchor_kinds") or []),
            goal_contains=list(a.selection_criteria.get("goal_contains") or []),
            text_contains=list(a.selection_criteria.get("text_contains") or []),
        ),
        parent_skill=a.parent_capability,
        prompt=SkillPrompt(
            free_text=a.extra_system,
            domain_rules=a.domain_rules,
        ),
        output=SkillOutput(),
    )
    append_skill_event(data_root, skill)


def read_approaches(
    data_root: Path,
    *,
    step_kind: str | None = None,
    enabled_only: bool = True,
) -> list[Approach]:
    """Return latest record per name, sorted by name. Drops tombstoned
    names. By default also drops disabled approaches and filters by
    *step_kind* if supplied."""
    items = list(_latest_by_name(data_root).values())
    if enabled_only:
        items = [a for a in items if a.enabled]
    if step_kind is not None:
        items = [a for a in items if step_kind in a.step_kinds]
    items.sort(key=lambda a: a.name)
    return items


def get_approach(data_root: Path, approach_id: str) -> Approach | None:
    """Return the latest record for *approach_id* (regardless of enabled
    flag), or None if missing or tombstoned."""
    for a in _latest_by_name(data_root).values():
        if a.approach_id == approach_id:
            return a
    return None


def disable_approach(data_root: Path, approach_id: str) -> Approach | None:
    """Append a new event with enabled=False, version+1. Returns the new
    record, or None if approach_id is unknown."""
    current = get_approach(data_root, approach_id)
    if current is None:
        return None
    return upsert_approach(
        data_root,
        name=current.name,
        step_kinds=list(current.step_kinds),
        extra_system=current.extra_system,
        enabled=False,
        selection_criteria=dict(current.selection_criteria),
        mode=current.mode,
        triggers=dict(current.triggers),
        parent_capability=current.parent_capability,
        domain_rules=current.domain_rules,
    )


def delete_approach(data_root: Path, approach_id: str) -> bool:
    """Append a tombstone event so read_approaches no longer returns it.

    Idempotent: tombstoning an unknown id still succeeds (returns False
    only if the id has never been seen)."""
    current = get_approach(data_root, approach_id)
    if current is None:
        return False
    _append_record(data_root, {"_tombstone": True, "approach_id": approach_id})
    # Mirror the tombstone into skills.jsonl so the unified reader
    # also drops this record. Lazy import for the same reason as the
    # write-through above.
    from local_pdf.provenienz.skills import tombstone_skill as _tombstone_skill

    _tombstone_skill(data_root, approach_id)
    return True


def build_approach_id() -> str:
    """Re-export so callers don't need to import storage.new_id directly."""
    return new_id()


# ── Auto-selection ────────────────────────────────────────────────────
#
# Each approach can declare ``selection_criteria`` describing when it
# should auto-pin itself for a given anchor + session goal. Empty
# criteria (the default) = manual-pin only — preserves the legacy
# behaviour for every existing approach.


def auto_match_approach(
    criteria: dict[str, Any],
    *,
    anchor_kind: str,
    anchor_text: str,
    goal: str,
) -> tuple[bool, list[str]]:
    """Decide whether *criteria* match the current anchor + goal.

    AND-logic across keys present in criteria; OR-logic within each
    key's list. Empty / falsy criteria return ``(False, [])``.

    Returns (matched, human-readable reasons). Reasons are surfaced in
    the audit so the user can see why each approach auto-pinned.
    """
    if not criteria:
        return False, []
    reasons: list[str] = []

    anchor_kinds = criteria.get("anchor_kinds") or []
    if anchor_kinds:
        if anchor_kind not in anchor_kinds:
            return False, []
        reasons.append(f"Anker-Typ '{anchor_kind}' in [{', '.join(anchor_kinds)}]")

    goal_contains = criteria.get("goal_contains") or []
    if goal_contains:
        goal_lower = (goal or "").lower()
        matched = [k for k in goal_contains if k and k.lower() in goal_lower]
        if not matched:
            return False, []
        reasons.append(f"Ziel enthält: {', '.join(matched)}")

    text_contains = criteria.get("text_contains") or []
    if text_contains:
        text_lower = (anchor_text or "").lower()
        matched = [k for k in text_contains if k and k.lower() in text_lower]
        if not matched:
            return False, []
        reasons.append(f"Anker-Text enthält: {', '.join(matched)}")

    if not reasons:
        # criteria object had keys but all were empty lists - treat as
        # no auto-trigger configured rather than as a wildcard match.
        return False, []
    return True, reasons


def match_triggers(
    triggers: dict[str, Any],
    *,
    verdict: str,
    sentence_texts: list[str],
    claim_text: str,
) -> tuple[bool, list[str]]:
    """Reactive-Capability trigger matcher.

    AND-logic across keys present in ``triggers``; OR-logic within
    each key's list. Returns ``(matched, reasons)``. Empty/falsy
    triggers return ``(False, [])`` — non-reactive approaches never
    fire here.

    Recognised keys:
      - ``verdicts``       : list[str] — verdict must equal one
      - ``sentence_regex`` : list[str] — at least one regex matches
                            any sentence text
      - ``claim_regex``    : list[str] — at least one regex matches
                            the claim text
      - ``topic_keywords`` : list[str] — at least one substring is
                            in the combined claim + sentences text
                            (case-insensitive)
    """
    if not triggers:
        return False, []
    import re as _re

    reasons: list[str] = []
    combined_text = " ".join([claim_text, *sentence_texts]).lower()

    verdicts = triggers.get("verdicts") or []
    if verdicts:
        if verdict not in verdicts:
            return False, [f"❌ Verdict '{verdict}' nicht in {verdicts}"]
        reasons.append(f"✓ Verdict '{verdict}' in {verdicts}")

    sentence_regexes = triggers.get("sentence_regex") or []
    if sentence_regexes:
        matched_pattern = None
        invalid: list[str] = []
        for pat in sentence_regexes:
            if not isinstance(pat, str) or not pat:
                continue
            try:
                rx = _re.compile(pat, _re.IGNORECASE)
            except _re.error as e:
                invalid.append(f"{pat!r} ({e})")
                continue
            for s in sentence_texts:
                if rx.search(s):
                    matched_pattern = pat
                    break
            if matched_pattern:
                break
        if not matched_pattern:
            fail_reasons = list(reasons)
            if invalid:
                fail_reasons.append(f"❌ Satz-Regex: {len(invalid)} ungültig — {invalid[0]}")
            else:
                fail_reasons.append(
                    f"❌ Satz-Regex: keine von {sentence_regexes} matchte "
                    f"(geprüft: {len(sentence_texts)} Sätze)"
                )
            return False, fail_reasons
        reasons.append(f"✓ Satz-Regex {matched_pattern!r} matchte")

    claim_regexes = triggers.get("claim_regex") or []
    if claim_regexes:
        matched_pattern = None
        invalid = []
        for pat in claim_regexes:
            if not isinstance(pat, str) or not pat:
                continue
            try:
                rx = _re.compile(pat, _re.IGNORECASE)
            except _re.error as e:
                invalid.append(f"{pat!r} ({e})")
                continue
            if rx.search(claim_text):
                matched_pattern = pat
                break
        if not matched_pattern:
            fail_reasons = list(reasons)
            if invalid:
                fail_reasons.append(f"❌ Claim-Regex: {len(invalid)} ungültig — {invalid[0]}")
            else:
                fail_reasons.append(
                    f"❌ Claim-Regex: keine von {claim_regexes} matchte den Claim "
                    f"({claim_text[:60]!r}…)"
                )
            return False, fail_reasons
        reasons.append(f"✓ Claim-Regex {matched_pattern!r} matchte")

    topic_keywords = triggers.get("topic_keywords") or []
    if topic_keywords:
        matched_kw = None
        for kw in topic_keywords:
            if isinstance(kw, str) and kw and kw.lower() in combined_text:
                matched_kw = kw
                break
        if not matched_kw:
            fail_reasons = list(reasons)
            fail_reasons.append(
                f"❌ Topic-Keyword: keines von {topic_keywords} im Text "
                f"({len(combined_text)} Zeichen)"
            )
            return False, fail_reasons
        reasons.append(f"✓ Topic-Keyword '{matched_kw}' im Text")

    if not reasons:
        return False, []
    return True, reasons


def scan_capabilities(
    approaches: list[Approach],
    *,
    verdict: str,
    sentence_texts: list[str],
    claim_text: str,
) -> list[tuple[Approach, list[str], list[tuple[Approach, list[str]]]]]:
    """Reactive-Capability scanner.

    Walks all enabled, non-tombstoned approaches and returns the list
    of top-level capabilities (parent_capability == "") whose
    triggers match, alongside any matching sub-skills (their
    parent_capability == top.name AND their own triggers also match).

    Returns ``[(top_app, top_reasons, [(sub_app, sub_reasons), ...]), ...]``.
    """
    out: list[tuple[Approach, list[str], list[tuple[Approach, list[str]]]]] = []
    by_parent: dict[str, list[Approach]] = {}
    for a in approaches:
        if not a.enabled:
            continue
        if a.parent_capability:
            by_parent.setdefault(a.parent_capability, []).append(a)
    for top in approaches:
        if not top.enabled or top.parent_capability:
            continue
        ok, reasons = match_triggers(
            top.triggers,
            verdict=verdict,
            sentence_texts=sentence_texts,
            claim_text=claim_text,
        )
        if not ok:
            continue
        sub_matches: list[tuple[Approach, list[str]]] = []
        for sub in by_parent.get(top.name, []):
            sub_ok, sub_reasons = match_triggers(
                sub.triggers,
                verdict=verdict,
                sentence_texts=sentence_texts,
                claim_text=claim_text,
            )
            if sub_ok:
                sub_matches.append((sub, sub_reasons))
        out.append((top, reasons, sub_matches))
    return out


def auto_select_approaches(
    approaches: list[Approach],
    *,
    anchor_kind: str,
    anchor_text: str,
    goal: str,
) -> list[tuple[Approach, list[str]]]:
    """Filter *approaches* (caller pre-filters by step_kind + enabled)
    down to those auto-matching the current anchor + goal. Returns
    each with its match reasons.
    """
    out: list[tuple[Approach, list[str]]] = []
    for a in approaches:
        ok, reasons = auto_match_approach(
            a.selection_criteria,
            anchor_kind=anchor_kind,
            anchor_text=anchor_text,
            goal=goal,
        )
        if ok:
            out.append((a, reasons))
    return out
