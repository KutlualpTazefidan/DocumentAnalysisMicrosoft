"""Tests for goldens.storage.log.append_events — bulk atomic append
with per-event idempotency, empty-list no-op, and cross-process
no-interleave guarantee."""

from __future__ import annotations

import multiprocessing as mp
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from goldens.schemas.base import Event
from goldens.storage.log import (
    _existing_event_ids,
    append_event,
    append_events,
    read_events,
)


def _make_event(eid: str, entry_id: str = "r1", ts: str = "2026-04-29T10:00:00Z") -> Event:
    return Event(
        event_id=eid,
        timestamp_utc=ts,
        event_type="created",
        entry_id=entry_id,
        schema_version=1,
        payload={"hello": "world"},
    )


def test_append_events_writes_all(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    a, b = _make_event("ea"), _make_event("eb")
    append_events(p, [a, b])
    assert [e.event_id for e in read_events(p)] == ["ea", "eb"]


def test_append_events_empty_is_noop(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    append_events(p, [])
    assert not p.exists()


def test_append_events_creates_parent_dirs(tmp_path: Path):
    p = tmp_path / "nested" / "deeper" / "log.jsonl"
    assert not p.parent.exists()
    append_events(p, [_make_event("ea")])
    assert p.exists()


def test_append_events_skips_event_already_in_log(tmp_path: Path):
    """An event whose id already exists is skipped; siblings with new ids land."""
    p = tmp_path / "log.jsonl"
    append_event(p, _make_event("ea"))
    append_events(p, [_make_event("ea"), _make_event("eb")])
    assert [e.event_id for e in read_events(p)] == ["ea", "eb"]


def test_append_events_skips_duplicate_within_batch(tmp_path: Path):
    """Two events in the same batch sharing one event_id → first wins, second skipped."""
    p = tmp_path / "log.jsonl"
    a1 = _make_event("ea", ts="2026-04-29T10:00:00Z")
    a2 = _make_event("ea", ts="2026-04-29T11:00:00Z")
    append_events(p, [a1, a2])
    events = read_events(p)
    assert [e.event_id for e in events] == ["ea"]
    assert events[0].timestamp_utc == "2026-04-29T10:00:00Z"


def test_append_events_all_duplicates_writes_nothing(tmp_path: Path):
    """If every event in the batch is already present, the wrote_any
    branch stays False — no flush/fsync, log is unchanged."""
    p = tmp_path / "log.jsonl"
    append_event(p, _make_event("ea"))
    before = p.read_bytes()
    append_events(p, [_make_event("ea"), _make_event("ea")])
    assert p.read_bytes() == before
    assert [e.event_id for e in read_events(p)] == ["ea"]


def test_existing_event_ids_returns_empty_set_for_missing_file(tmp_path: Path):
    """_existing_event_ids covers the path-does-not-exist branch."""
    p = tmp_path / "missing.jsonl"
    assert _existing_event_ids(p) == set()


def test_existing_event_ids_skips_blank_and_malformed_and_idless_lines(tmp_path: Path):
    """Cover the blank-line, malformed-JSON, and missing-event_id branches
    of _existing_event_ids."""
    p = tmp_path / "log.jsonl"
    append_event(p, _make_event("ea"))
    with p.open("a", encoding="utf-8") as f:
        f.write("\n")  # blank line
        f.write("THIS IS NOT JSON\n")  # malformed
        f.write('{"foo": "bar"}\n')  # valid JSON but no event_id
    assert _existing_event_ids(p) == {"ea"}


def _bulk_worker(path_str: str, prefix: str, n_pairs: int) -> None:
    """Top-level so it pickles. Each call writes a single 2-event batch."""
    from pathlib import Path

    from goldens.schemas.base import Event
    from goldens.storage.log import append_events

    p = Path(path_str)
    for i in range(n_pairs):
        a = Event(
            event_id=f"{prefix}-{i:04d}-A",
            timestamp_utc="2026-04-29T10:00:00Z",
            event_type="created",
            entry_id=f"{prefix}-r{i}",
            schema_version=1,
            payload={},
        )
        b = Event(
            event_id=f"{prefix}-{i:04d}-B",
            timestamp_utc="2026-04-29T10:00:00Z",
            event_type="deprecated",
            entry_id=f"{prefix}-r{i}",
            schema_version=1,
            payload={"reason": "test"},
        )
        append_events(p, [a, b])


@pytest.mark.skipif(sys.platform != "linux", reason="fcntl semantics tested on Linux only")
def test_append_events_concurrent_pairs_never_interleave(tmp_path: Path):
    """Two processes each write 50 two-event batches. Each batch must
    appear contiguously in the file (A immediately before its paired B),
    never interleaved with the other worker's pairs."""
    p = tmp_path / "log.jsonl"
    procs = [
        mp.Process(target=_bulk_worker, args=(str(p), "X", 50)),
        mp.Process(target=_bulk_worker, args=(str(p), "Y", 50)),
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=30)
        assert proc.exitcode == 0, "worker exited with an error"

    events = read_events(p)
    assert len(events) == 200
    # Walk in (A, B) pairs — each pair must share prefix+index.
    for i in range(0, len(events), 2):
        a, b = events[i], events[i + 1]
        assert a.event_id.endswith("-A"), f"expected A at index {i}, got {a.event_id}"
        assert b.event_id.endswith("-B"), f"expected B at index {i + 1}, got {b.event_id}"
        assert a.event_id[:-2] == b.event_id[:-2], (
            f"interleaved pair at index {i}: {a.event_id!r}, {b.event_id!r}"
        )
