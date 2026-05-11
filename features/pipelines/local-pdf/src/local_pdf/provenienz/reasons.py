"""Implicit guidance corpus: every override becomes a reason record.

Reasons are now persisted in the unified skill store as ``NOTE`` skills
in ``{LOCAL_PDF_DATA_ROOT}/provenienz/skills.jsonl``. This module is
the legacy translation surface that renders NOTE-flavoured Skills as
``Reason`` instances for callers that still walk the legacy shape
(the override-recording path on /decide and the reason-prompt-injector).

Read access is filtered + bounded — Stage 6.2's prompt injector calls
``read_reasons(step_kind=..., last_n=5)`` to fetch the most recent
relevant overrides for in-context examples.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

from local_pdf.provenienz.storage import _now, new_id

if TYPE_CHECKING:
    from local_pdf.provenienz.skills import Skill


@dataclass(frozen=True)
class Reason:
    reason_id: str
    step_kind: str
    session_id: str
    proposal_id: str
    proposal_summary: str  # one-liner of what the LLM recommended
    override_summary: str  # one-liner of what the human picked instead
    reason_text: str  # free-text from body.reason on /decide
    actor: str  # "human" — overrides only
    created_at: str = ""


def append_reason(data_root: Path, r: Reason) -> Reason:
    """Persist this reason as a NOTE skill in skills.jsonl.

    Auto-fills ``reason_id`` and ``created_at`` if the caller left them
    blank, then defers to ``_persist_reason_as_skill``.
    """
    r2 = Reason(
        **{
            **r.__dict__,
            "reason_id": r.reason_id or new_id(),
            "created_at": r.created_at or _now(),
        }
    )
    _persist_reason_as_skill(data_root, r2)
    return r2


def _persist_reason_as_skill(data_root: Path, r: Reason) -> None:
    """Write this reason to the unified skill store as a NOTE skill.

    The NOTE skill's ``skill_id`` is set to the reason's
    ``reason_id`` so that GuidanceRef.id (emitted by the prompt
    injector against the skill record) round-trips back to the original
    reason — keeping the legacy ref shape contract intact. Lazy import
    avoids a circular dependency at module load.
    """
    from local_pdf.provenienz.skills import (
        Skill,
        SkillKind,
        SkillPrompt,
        append_skill_event,
    )

    proposal = (r.proposal_summary or "").strip()
    override = (r.override_summary or "").strip()
    grund = (r.reason_text or "").strip()
    # Pack the legacy 3-line block into free_text so the prompt-injector
    # can render it under the "Frühere Korrekturen" header without
    # losing the proposal/override context.
    parts: list[str] = []
    if proposal:
        parts.append(f"Empfehlung: {proposal}")
    if override:
        parts.append(f"  Korrektur:  {override}")
    if grund:
        parts.append(f"  Grund:      {grund}")
    free_text = "\n".join(parts) if parts else grund

    skill = Skill(
        skill_id=r.reason_id,
        # Use the full reason_id in the name. ULIDs share a 10-char
        # timestamp prefix when generated in the same millisecond, so
        # truncating to 8 chars caused name-collisions in fast write
        # bursts (each NOTE skill is upsert-by-name in the unified
        # store, so collisions silently drop earlier reasons).
        name=f"note-{r.reason_id}",
        version=1,
        enabled=True,
        description=grund[:80],
        created_at=r.created_at,
        updated_at=r.created_at,
        skill_kind=SkillKind.NOTE,
        fires_on=[r.step_kind],
        prompt=SkillPrompt(free_text=free_text),
    )
    append_skill_event(data_root, skill)


def _unpack_free_text(free_text: str) -> tuple[str, str, str]:
    """Inverse of the 3-line packing in _write_through_to_skills.

    Returns ``(proposal_summary, override_summary, reason_text)``. If
    free_text doesn't carry the legacy markers (e.g. a NOTE skill
    authored directly through the skills API rather than via
    ``append_reason``), proposal/override come back empty and the full
    block is returned as ``reason_text``.
    """
    proposal = ""
    override = ""
    grund = ""
    matched_any = False
    for raw in free_text.splitlines():
        line = raw.strip()
        if line.startswith("Empfehlung:"):
            proposal = line[len("Empfehlung:") :].strip()
            matched_any = True
        elif line.startswith("Korrektur:"):
            override = line[len("Korrektur:") :].strip()
            matched_any = True
        elif line.startswith("Grund:"):
            grund = line[len("Grund:") :].strip()
            matched_any = True
    if not matched_any:
        return "", "", free_text
    return proposal, override, grund


def _skill_to_reason(s: Skill) -> Reason:
    """Render a NOTE Skill back to a legacy Reason instance for
    callers that still walk reasons (decide handler's optional
    reason recording, _gather_reason_guidance, etc.).

    Unpacks the legacy 3-line ``Empfehlung/Korrektur/Grund`` block from
    ``free_text`` so the original proposal_summary / override_summary
    / reason_text round-trip correctly.
    """
    step_kind = s.fires_on[0] if s.fires_on else "evaluate"
    proposal, override, grund = _unpack_free_text(s.prompt.free_text)
    return Reason(
        reason_id=s.skill_id,
        step_kind=step_kind,
        session_id="",
        proposal_id="",
        proposal_summary=proposal,
        override_summary=override,
        reason_text=grund,
        actor="human",
        created_at=s.created_at,
    )


def read_reasons(
    data_root: Path,
    *,
    step_kind: str | None = None,
    last_n: int = 5,
) -> list[Reason]:
    """Return the *last_n* NOTE-skill records matching ``step_kind`` (or
    all kinds if None), rendered as legacy Reason instances in
    chronological order (oldest first within the slice). Reads from
    skills.jsonl (the unified store).

    Uses ``read_skill_events`` rather than ``read_skills`` because NOTE
    skills are append-only (one record per override) and ``_now()`` has
    only second-level granularity — sorting by ``created_at`` would be
    unstable across fast bursts. File order is the canonical insertion
    order.
    """
    from local_pdf.provenienz.skills import SkillKind, read_skill_events

    events = read_skill_events(data_root, kind=SkillKind.NOTE)
    matched: list[Reason] = []
    for s in events:
        if not s.enabled:
            continue
        if step_kind is not None and step_kind not in s.fires_on:
            continue
        matched.append(_skill_to_reason(s))
    if last_n <= 0:
        return matched
    return matched[-last_n:]
