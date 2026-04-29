"""Tests for goldens.operations.deprecate."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from goldens.operations.deprecate import deprecate
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import Event, HumanActor
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import build_state


def _human() -> HumanActor:
    return HumanActor(pseudonym="alice", level="phd")


def _seed_created(path: Path, entry_id: str = "r1") -> None:
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


def test_deprecate_raises_entry_not_found_for_unknown_id(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    with pytest.raises(EntryNotFoundError):
        deprecate(p, "ghost", actor=_human())


def test_deprecate_raises_when_entry_already_deprecated(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    deprecate(p, "r1", actor=_human(), reason="first time")
    with pytest.raises(EntryDeprecatedError):
        deprecate(p, "r1", actor=_human(), reason="second time")


def test_deprecate_appends_event_and_flips_state(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    eid = deprecate(p, "r1", actor=_human(), reason="obsolete chunk hashes")
    events = read_events(p)
    state = build_state(events)
    assert state["r1"].deprecated is True
    last_ev = events[-1]
    assert last_ev.event_id == eid
    assert last_ev.event_type == "deprecated"
    assert last_ev.entry_id == "r1"
    assert last_ev.payload["reason"] == "obsolete chunk hashes"
    assert last_ev.payload["actor"] == _human().to_dict()


def test_deprecate_respects_explicit_timestamp(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    deprecate(p, "r1", actor=_human(), timestamp_utc="2030-06-01T00:00:00Z")
    events = read_events(p)
    assert events[-1].timestamp_utc == "2030-06-01T00:00:00Z"
