"""Event-sourced storage layer for goldens. Public re-exports added
as modules land."""

from goldens.storage.ids import new_entry_id, new_event_id

__all__ = ["new_entry_id", "new_event_id"]
