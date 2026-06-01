from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from llm_clients.base import Message

from local_pdf.llm import get_default_model, get_llm_client
from local_pdf.provenienz.skills import Skill, SkillKind, read_skills

if TYPE_CHECKING:
    from pathlib import Path


_ENRICHMENT_SYSTEM_DEFAULT = (
    "Du bekommst N Eingaben und eine Liste von Fragen. Beantworte jede "
    "Frage für jede Eingabe — knapp, in 1-3 deutschen Sätzen pro Eingabe. "
    "Antworte ausschließlich als JSON-Array von Strings (selbe Länge wie "
    "Eingaben), kein Vor- oder Nachtext, kein Markdown."
)


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


def run_enrichment_skill(
    skill: Skill,
    inputs: list[str],
    *,
    chunk_text: str = "",
    data_root: Path | None = None,
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
    chunk_block = f"Quell-Textabschnitt:\n{truncated}\n\n" if truncated else ""
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(inputs))
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
        out = [""] * len(inputs)
        _append_skill_run_audit(skill, inputs, out, data_root)
        return out
    raw = (completion.text or "").strip()
    # Strip ``` fences if present
    if raw.startswith("```"):
        raw = raw.lstrip("`").lstrip("json").strip()
        if raw.endswith("```"):
            raw = raw[:-3].rstrip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        out = [""] * len(inputs)
        _append_skill_run_audit(skill, inputs, out, data_root)
        return out
    if not isinstance(parsed, list) or len(parsed) != len(inputs):
        out = [""] * len(inputs)
        _append_skill_run_audit(skill, inputs, out, data_root)
        return out
    out = [str(x).strip()[:1500] if isinstance(x, str) else "" for x in parsed]
    _append_skill_run_audit(skill, inputs, out, data_root)
    return out


def read_skill_runs(
    data_root: Path,
    *,
    skill_id: str | None = None,
    last_n: int = 50,
) -> list[dict]:
    """Read the per-run audit log at ``{data_root}/skills/skill_runs.jsonl``.

    Returns the most recent records first (reverse line order in the
    file), optionally filtered by ``skill_id``, capped at ``last_n``.
    Returns ``[]`` if the file does not exist or no records match.
    Malformed lines are skipped silently — the audit log is best-effort.
    """
    runs_path = data_root / "skills" / "skill_runs.jsonl"
    if not runs_path.exists():
        return []
    records: list[dict] = []
    try:
        with runs_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if skill_id is not None and rec.get("skill_id") != skill_id:
                    continue
                records.append(rec)
    except OSError:
        return []
    # Newest first (last appended line is most recent).
    records.reverse()
    return records[:last_n]


def _append_skill_run_audit(
    skill: Skill,
    inputs: list[str],
    outputs: list[str],
    data_root: Path | None,
) -> None:
    """Append one JSONL record to {data_root}/skills/skill_runs.jsonl.

    Best-effort: any exception is swallowed — audit failure must never
    break the skill run. Only the future SkillDetailPanel UI reads this
    file; it's never consumed by the dispatcher itself.
    """
    if data_root is None:
        return
    try:
        non_empty = sum(1 for x in outputs if x)
        record = {
            "skill_id": skill.skill_id,
            "skill_name": skill.name,
            "skill_version": skill.version,
            "n_inputs": len(inputs),
            "n_outputs": non_empty,
            "success": non_empty > 0,
            "ts": datetime.now(UTC).isoformat(),
        }
        skills_dir = data_root / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        with (skills_dir / "skill_runs.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass
