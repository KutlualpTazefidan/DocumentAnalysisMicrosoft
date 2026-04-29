"""Tests for goldens.operations.add_review."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from goldens.operations.add_review import add_review
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import Event, HumanActor
from goldens.storage.log import append_event, read_events


def _human() -> HumanActor:
    return HumanActor(pseudonym="alice", level="phd")


def _seed_created(path: Path, entry_id: str = "r1") -> None:
    """Seed a `created` event so the entry exists in the projected state."""
    append_event(
        path,
        Event(
            event_id="seed-created",
            timestamp_utc="2024-01-01T00:00:00Z",
            event_type="created",
            entry_id=entry_id,
            schema_version=1,
            payload={
                "task_type": "retrieval",
                "actor": _human().to_dict(),
                "action": "created_from_scratch",
                "notes": None,
                "entry_data": {
                    "query": "What is X?",
                    "expected_chunk_ids": ["c1"],
                    "chunk_hashes": {"c1": "sha256:aaa"},
                    "refines": None,
                },
            },
        ),
    )


def _seed_deprecate(path: Path, entry_id: str = "r1") -> None:
    append_event(
        path,
        Event(
            event_id="seed-dep",
            timestamp_utc="2024-01-01T00:30:00Z",
            event_type="deprecated",
            entry_id=entry_id,
            schema_version=1,
            payload={"actor": _human().to_dict(), "reason": None},
        ),
    )


def test_add_review_raises_entry_not_found_for_unknown_id(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    with pytest.raises(EntryNotFoundError):
        add_review(p, "ghost", actor=_human(), action="approved")


def test_add_review_raises_entry_deprecated_when_already_deprecated(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    _seed_deprecate(p)
    with pytest.raises(EntryDeprecatedError):
        add_review(p, "r1", actor=_human(), action="approved")


def test_add_review_appends_reviewed_event_on_valid_entry(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    eid = add_review(p, "r1", actor=_human(), action="approved", notes="LGTM")
    events = read_events(p)
    assert len(events) == 2
    review_ev = events[-1]
    assert review_ev.event_id == eid
    assert review_ev.event_type == "reviewed"
    assert review_ev.entry_id == "r1"
    assert review_ev.payload["action"] == "approved"
    assert review_ev.payload["notes"] == "LGTM"
    assert review_ev.payload["actor"] == _human().to_dict()


def test_add_review_respects_explicit_timestamp(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    add_review(
        p,
        "r1",
        actor=_human(),
        action="accepted_unchanged",
        timestamp_utc="2030-01-01T00:00:00Z",
    )
    events = read_events(p)
    assert events[-1].timestamp_utc == "2030-01-01T00:00:00Z"
