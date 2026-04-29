"""deprecate — mark an existing entry as no-longer-valid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goldens.operations._time import now_utc_iso
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import Event, HumanActor, LLMActor
from goldens.storage.ids import new_event_id
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import build_state

if TYPE_CHECKING:
    from pathlib import Path


def deprecate(
    path: Path,
    entry_id: str,
    *,
    actor: HumanActor | LLMActor,
    reason: str | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Append a `deprecated` event for `entry_id`.

    Returns the new event_id.

    Raises:
        EntryNotFoundError: `entry_id` is not present in the projected state.
        EntryDeprecatedError: the entry is already deprecated. Re-deprecation
            is rejected; callers who want idempotent behaviour catch this.
    """
    state = build_state(read_events(path))
    if entry_id not in state:
        raise EntryNotFoundError(entry_id)
    if state[entry_id].deprecated:
        raise EntryDeprecatedError(entry_id)
    ts = timestamp_utc or now_utc_iso()
    eid: str = new_event_id()
    event = Event(
        event_id=eid,
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=entry_id,
        schema_version=1,
        payload={"actor": actor.to_dict(), "reason": reason},
    )
    append_event(path, event)
    return eid
