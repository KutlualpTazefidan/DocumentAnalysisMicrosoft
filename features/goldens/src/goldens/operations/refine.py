"""refine — atomic create-new-entry + deprecate-old."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goldens.operations._time import now_utc_iso
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import CreateAction, Event, HumanActor, LLMActor
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_events, read_events
from goldens.storage.projection import build_state

if TYPE_CHECKING:
    from pathlib import Path


def refine(
    path: Path,
    old_entry_id: str,
    *,
    query: str,
    expected_chunk_ids: tuple[str, ...],
    chunk_hashes: dict[str, str],
    actor: HumanActor | LLMActor,
    action: CreateAction = "created_from_scratch",
    notes: str | None = None,
    deprecate_reason: str | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Refine `old_entry_id` — atomically create a new entry that
    points at the old via `refines`, and deprecate the old.

    Returns the NEW entry_id.

    Both events share the same `timestamp_utc` (one user action = one
    logical timestamp). The two events land in the log under a single
    fcntl.LOCK_EX via `append_events`.

    Raises:
        EntryNotFoundError: `old_entry_id` is not present in the projected state.
        EntryDeprecatedError: the old entry is already deprecated.
    """
    state = build_state(read_events(path))
    if old_entry_id not in state:
        raise EntryNotFoundError(old_entry_id)
    if state[old_entry_id].deprecated:
        raise EntryDeprecatedError(old_entry_id)

    ts = timestamp_utc or now_utc_iso()
    new_id: str = new_entry_id()
    actor_dict = actor.to_dict()

    create_ev = Event(
        event_id=new_event_id(),
        timestamp_utc=ts,
        event_type="created",
        entry_id=new_id,
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor_dict,
            "action": action,
            "notes": notes,
            "entry_data": {
                "query": query,
                "expected_chunk_ids": list(expected_chunk_ids),
                "chunk_hashes": dict(chunk_hashes),
                "refines": old_entry_id,
            },
        },
    )
    deprecate_ev = Event(
        event_id=new_event_id(),
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=old_entry_id,
        schema_version=1,
        payload={"actor": actor_dict, "reason": deprecate_reason},
    )
    append_events(path, [create_ev, deprecate_ev])
    return new_id
