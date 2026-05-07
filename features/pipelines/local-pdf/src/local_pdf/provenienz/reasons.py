"""Implicit guidance corpus: every override becomes a reason record.

Stored at ``{LOCAL_PDF_DATA_ROOT}/provenienz/reasons.jsonl`` (global, not
per-session) so cross-session learning works. Append-only; one JSON
record per line.

Read access is filtered + bounded — Stage 6.2's prompt injector calls
``read_reasons(step_kind=..., last_n=5)`` to fetch the most recent
relevant overrides for in-context examples.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path  # noqa: TC003

from local_pdf.provenienz.storage import _now, new_id


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


def _reasons_path(data_root: Path) -> Path:
    return data_root / "provenienz" / "reasons.jsonl"


def append_reason(data_root: Path, r: Reason) -> Reason:
    path = _reasons_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    r2 = Reason(
        **{
            **r.__dict__,
            "reason_id": r.reason_id or new_id(),
            "created_at": r.created_at or _now(),
        }
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(r2.__dict__, ensure_ascii=False) + "\n")
    # Write-through to the unified skill store so the new
    # apply_skills() reader picks up reasons via fires_on filtering.
    # Kept alongside the legacy file path while _gather_guidance_split
    # (multi-agent next_step) still reads from reasons.jsonl directly.
    _write_through_to_skills(data_root, r2)
    return r2


def _write_through_to_skills(data_root: Path, r: Reason) -> None:
    """Mirror this reason as a NOTE skill in skills.jsonl.

    Lazy import keeps the legacy reason path standalone for tests that
    only exercise reasons.jsonl (test_provenienz_reasons.py).

    The NOTE skill's ``skill_id`` is set to the reason's
    ``reason_id`` so that GuidanceRef.id (emitted by the prompt
    injector against the skill record) round-trips back to the original
    reason — keeping the legacy ref shape contract intact.
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
        name=f"note-{r.reason_id[:8]}",
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


def read_reasons(
    data_root: Path,
    *,
    step_kind: str | None = None,
    last_n: int = 5,
) -> list[Reason]:
    """Return the *last_n* reasons matching ``step_kind`` (or all kinds if
    None), in chronological order (oldest first within the slice)."""
    path = _reasons_path(data_root)
    if not path.exists():
        return []
    matched: list[Reason] = []
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if step_kind is not None and rec.get("step_kind") != step_kind:
                continue
            matched.append(Reason(**rec))
    if last_n <= 0:
        return matched
    return matched[-last_n:]
