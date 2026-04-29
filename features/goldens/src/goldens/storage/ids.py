"""UUID4 helpers for event/entry identity.

Both event_id and entry_id are UUID4 hex strings (no dashes) — short,
URL-safe, and large enough to make collision negligible. UUID4 is
chosen over UUID1/3/5 because it does not leak host or time
information.
"""

from __future__ import annotations

import uuid


def new_event_id() -> str:
    """Generate a new UUID4 event_id (idempotency key for events)."""
    return uuid.uuid4().hex


def new_entry_id() -> str:
    """Generate a new UUID4 entry_id (stable identity for an entry
    across refinements)."""
    return uuid.uuid4().hex
