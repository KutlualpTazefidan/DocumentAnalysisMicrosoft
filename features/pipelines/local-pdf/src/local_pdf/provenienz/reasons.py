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
    r2 = Reason(**{**r.__dict__, "created_at": r.created_at or _now()})
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(r2.__dict__, ensure_ascii=False) + "\n")
    return r2


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


def build_reason_id() -> str:
    """Re-export so callers don't need to import storage.new_id directly."""
    return new_id()
