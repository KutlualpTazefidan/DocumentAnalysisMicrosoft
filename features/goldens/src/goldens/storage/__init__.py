"""Event-sourced storage layer for goldens."""

from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event, append_events, read_events
from goldens.storage.projection import (
    active_entries,
    build_state,
    iter_active_retrieval_entries,
)

__all__ = [
    "active_entries",
    "append_event",
    "append_events",
    "build_state",
    "iter_active_retrieval_entries",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
