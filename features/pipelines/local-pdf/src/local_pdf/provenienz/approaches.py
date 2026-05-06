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
) -> Approach:
    """Create or bump-version an approach by *name*.

    First write at version=1. Subsequent writes copy the existing
    approach_id forward and increment version.
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
        )
    return append_approach_event(data_root, new)


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
    )


def delete_approach(data_root: Path, approach_id: str) -> bool:
    """Append a tombstone event so read_approaches no longer returns it.

    Idempotent: tombstoning an unknown id still succeeds (returns False
    only if the id has never been seen)."""
    current = get_approach(data_root, approach_id)
    if current is None:
        return False
    _append_record(data_root, {"_tombstone": True, "approach_id": approach_id})
    return True


def build_approach_id() -> str:
    """Re-export so callers don't need to import storage.new_id directly."""
    return new_id()
