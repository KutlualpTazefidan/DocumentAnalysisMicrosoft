"""Build current state from an event sequence.

Sorts events by timestamp_utc ascending, then reduces:

- `created` event with task_type=="retrieval" → new RetrievalEntry
  with empty review_chain plus a Review derived from the event's
  actor/action/notes/timestamp.
- `reviewed` event → append Review to the entry's chain.
- `deprecated` event → set deprecated=True and append a "deprecated"
  Review to the chain.

Orphan reviewed/deprecated events (no preceding `created` for that
entry_id) are skipped with a WARNING log.

Out-of-order tolerance: events with non-monotonic timestamps are
handled by the up-front sort. File order acts as the tie-breaker for
identical timestamps (Python's sort is stable).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from goldens.schemas.base import Event, Review, SourceElement, actor_from_dict
from goldens.schemas.retrieval import RetrievalEntry
from goldens.storage.log import read_events

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

_log = logging.getLogger(__name__)


def build_state(events: Iterable[Event]) -> dict[str, RetrievalEntry]:
    """Reduce events to a `dict[entry_id, RetrievalEntry]` projection."""
    sorted_events = sorted(events, key=lambda e: e.timestamp_utc)
    state: dict[str, RetrievalEntry] = {}
    for ev in sorted_events:
        if ev.event_type == "created":
            _apply_created(state, ev)
        elif ev.event_type == "reviewed":
            _apply_reviewed(state, ev)
        elif ev.event_type == "deprecated":
            _apply_deprecated(state, ev)
        else:  # pragma: no cover
            # Unreachable: Event.__post_init__ rejects any other event_type.
            pass
    return state


def active_entries(state: dict[str, RetrievalEntry]) -> Iterator[RetrievalEntry]:
    """Yield entries from `state` where `deprecated` is False."""
    for entry in state.values():
        if not entry.deprecated:
            yield entry


# --- internal helpers --------------------------------------------


def _apply_created(state: dict[str, RetrievalEntry], ev: Event) -> None:
    if ev.payload.get("task_type") != "retrieval":
        # Other entry types (Phase B/C) are not handled here.
        return
    entry_data = ev.payload.get("entry_data", {})
    review = Review(
        timestamp_utc=ev.timestamp_utc,
        action=ev.payload["action"],
        actor=actor_from_dict(ev.payload["actor"]),
        notes=ev.payload.get("notes"),
    )
    src_raw = entry_data.get("source_element")
    source_element = SourceElement.from_dict(src_raw) if src_raw is not None else None
    state[ev.entry_id] = RetrievalEntry(
        entry_id=ev.entry_id,
        query=entry_data["query"],
        expected_chunk_ids=tuple(entry_data["expected_chunk_ids"]),
        chunk_hashes=dict(entry_data["chunk_hashes"]),
        review_chain=(review,),
        deprecated=False,
        refines=entry_data.get("refines"),
        source_element=source_element,
    )


def _apply_reviewed(state: dict[str, RetrievalEntry], ev: Event) -> None:
    entry = state.get(ev.entry_id)
    if entry is None:
        _log.warning(
            "skipping reviewed event for unknown entry_id %s (event_id=%s)",
            ev.entry_id,
            ev.event_id,
        )
        return
    review = Review(
        timestamp_utc=ev.timestamp_utc,
        action=ev.payload["action"],
        actor=actor_from_dict(ev.payload["actor"]),
        notes=ev.payload.get("notes"),
    )
    state[ev.entry_id] = replace(entry, review_chain=(*entry.review_chain, review))


def _apply_deprecated(state: dict[str, RetrievalEntry], ev: Event) -> None:
    entry = state.get(ev.entry_id)
    if entry is None:
        _log.warning(
            "skipping deprecated event for unknown entry_id %s (event_id=%s)",
            ev.entry_id,
            ev.event_id,
        )
        return
    review = Review(
        timestamp_utc=ev.timestamp_utc,
        action="deprecated",
        actor=actor_from_dict(ev.payload["actor"]),
        notes=ev.payload.get("reason"),
    )
    state[ev.entry_id] = replace(
        entry,
        review_chain=(*entry.review_chain, review),
        deprecated=True,
    )


def iter_active_retrieval_entries(path: Path) -> Iterator[RetrievalEntry]:
    """Canonical read path for evaluators: read events from `path`,
    project to state, yield active (non-deprecated) entries.

    Drop to read_events / build_state / active_entries if you need
    deprecated entries, the full state dict, or non-retrieval task types.
    """
    return active_entries(build_state(read_events(path)))
