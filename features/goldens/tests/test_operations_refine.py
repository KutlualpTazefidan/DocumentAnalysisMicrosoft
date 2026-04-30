"""Tests for goldens.operations.refine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.operations.refine import refine
from goldens.schemas.base import Event, HumanActor
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import build_state


def _human() -> HumanActor:
    return HumanActor(pseudonym="alice", level="phd")


def _seed_created(path: Path, entry_id: str = "r-old") -> None:
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
                "actor": _human().model_dump(mode="json"),
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


def _seed_deprecate(path: Path, entry_id: str = "r-old") -> None:
    append_event(
        path,
        Event(
            event_id="seed-dep",
            timestamp_utc="2024-01-01T00:30:00Z",
            event_type="deprecated",
            entry_id=entry_id,
            schema_version=1,
            payload={"actor": _human().model_dump(mode="json"), "reason": None},
        ),
    )


def test_refine_raises_entry_not_found_for_unknown_old(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    with pytest.raises(EntryNotFoundError):
        refine(
            p,
            "ghost",
            query="q",
            expected_chunk_ids=("c1",),
            chunk_hashes={"c1": "sha256:aaa"},
            actor=_human(),
        )


def test_refine_raises_entry_deprecated_when_old_is_deprecated(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    _seed_deprecate(p)
    with pytest.raises(EntryDeprecatedError):
        refine(
            p,
            "r-old",
            query="q (refined)",
            expected_chunk_ids=("c1",),
            chunk_hashes={"c1": "sha256:aaa"},
            actor=_human(),
        )


def test_refine_creates_new_entry_and_deprecates_old(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    new_id = refine(
        p,
        "r-old",
        query="What is X (refined)?",
        expected_chunk_ids=("c1", "c2"),
        chunk_hashes={"c1": "sha256:aaa", "c2": "sha256:bbb"},
        actor=_human(),
        notes="fixed missing chunk",
        deprecate_reason="superseded",
    )
    state = build_state(read_events(p))
    assert state["r-old"].deprecated is True
    new = state[new_id]
    assert new.deprecated is False
    assert new.refines == "r-old"
    assert new.query == "What is X (refined)?"
    assert new.expected_chunk_ids == ("c1", "c2")
    assert new.chunk_hashes == {"c1": "sha256:aaa", "c2": "sha256:bbb"}


def test_refine_writes_two_events_with_shared_timestamp(tmp_path: Path):
    """refine writes exactly 2 events, both carrying the same timestamp,
    one `created` (new entry, refines=old), one `deprecated` (old)."""
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    refine(
        p,
        "r-old",
        query="q'",
        expected_chunk_ids=("c1",),
        chunk_hashes={"c1": "sha256:aaa"},
        actor=_human(),
        timestamp_utc="2024-06-01T12:00:00Z",
        deprecate_reason="r",
    )
    events = read_events(p)
    # 1 seed + 2 from refine
    assert len(events) == 3
    refine_events = events[1:]
    assert {ev.event_type for ev in refine_events} == {"created", "deprecated"}
    assert all(ev.timestamp_utc == "2024-06-01T12:00:00Z" for ev in refine_events)
    created_ev = next(e for e in refine_events if e.event_type == "created")
    deprecated_ev = next(e for e in refine_events if e.event_type == "deprecated")
    assert created_ev.payload["entry_data"]["refines"] == "r-old"
    assert deprecated_ev.entry_id == "r-old"
    assert deprecated_ev.payload["reason"] == "r"


def test_refine_respects_synthesised_action(tmp_path: Path):
    """The `action` parameter on the new created event is configurable
    so LLM-driven refinement can record action='synthesised'."""
    p = tmp_path / "log.jsonl"
    _seed_created(p)
    refine(
        p,
        "r-old",
        query="q",
        expected_chunk_ids=("c1",),
        chunk_hashes={"c1": "sha256:aaa"},
        actor=_human(),
        action="synthesised",
    )
    events = read_events(p)
    created_ev = next(
        e for e in events if e.event_type == "created" and e.event_id != "seed-created"
    )
    assert created_ev.payload["action"] == "synthesised"
