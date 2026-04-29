"""Tests for goldens.storage.log — append, read, idempotency,
malformed-line tolerance, and cross-process concurrent append."""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from goldens.schemas.base import Event
from goldens.storage.log import _event_id_already_present, append_event, read_events


def _make_event(eid: str, entry_id: str = "r1", ts: str = "2026-04-29T10:00:00Z") -> Event:
    return Event(
        event_id=eid,
        timestamp_utc=ts,
        event_type="created",
        entry_id=entry_id,
        schema_version=1,
        payload={"hello": "world"},
    )


# --- Basic append + read -----------------------------------------


def test_append_writes_event_to_jsonl(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    e = _make_event("e1")
    append_event(p, e)
    assert p.exists()
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["event_id"] == "e1"


def test_append_creates_parent_dirs(tmp_path: Path):
    p = tmp_path / "nested" / "deeper" / "log.jsonl"
    assert not p.parent.exists()
    append_event(p, _make_event("e1"))
    assert p.exists()


def test_read_round_trips_events(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    a, b = _make_event("e1"), _make_event("e2")
    append_event(p, a)
    append_event(p, b)
    events = read_events(p)
    assert [e.event_id for e in events] == ["e1", "e2"]


def test_read_returns_empty_for_missing_file(tmp_path: Path):
    p = tmp_path / "does_not_exist.jsonl"
    assert read_events(p) == []


def test_read_skips_blank_lines(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    append_event(p, _make_event("e1"))
    # Inject a blank line manually
    with p.open("a", encoding="utf-8") as f:
        f.write("\n\n")
    append_event(p, _make_event("e2"))
    events = read_events(p)
    assert [e.event_id for e in events] == ["e1", "e2"]


def test_read_skips_malformed_line_with_warning(tmp_path: Path, caplog):
    p = tmp_path / "log.jsonl"
    append_event(p, _make_event("e1"))
    with p.open("a", encoding="utf-8") as f:
        f.write("THIS IS NOT JSON\n")
    append_event(p, _make_event("e2"))
    with caplog.at_level("WARNING"):
        events = read_events(p)
    assert [e.event_id for e in events] == ["e1", "e2"]
    assert any("malformed" in rec.message.lower() for rec in caplog.records)


# --- Idempotency -------------------------------------------------


def test_append_same_event_id_twice_is_noop(tmp_path: Path):
    p = tmp_path / "log.jsonl"
    e1 = _make_event("e1")
    e1_again = _make_event("e1", ts="2026-04-29T11:00:00Z")  # different ts, same id
    append_event(p, e1)
    append_event(p, e1_again)
    events = read_events(p)
    assert len(events) == 1
    assert events[0].timestamp_utc == "2026-04-29T10:00:00Z"  # first one wins


# --- Internal helper: file-not-found branch ----------------------


def test_event_id_already_present_returns_false_for_missing_file(tmp_path: Path):
    """_event_id_already_present returns False when the log file does not exist."""
    p = tmp_path / "nonexistent.jsonl"
    assert not _event_id_already_present(p, "e1")


# --- Cross-process concurrent append (Linux only) ---------------


def _worker_appends(path_str: str, prefix: str, n: int) -> None:
    """Helper for concurrent-append test. Top-level so it pickles."""
    from pathlib import Path

    from goldens.schemas.base import Event
    from goldens.storage.log import append_event

    p = Path(path_str)
    for i in range(n):
        e = Event(
            event_id=f"{prefix}-{i:04d}",
            timestamp_utc="2026-04-29T10:00:00Z",
            event_type="created",
            entry_id="r1",
            schema_version=1,
            payload={},
        )
        append_event(p, e)


@pytest.mark.skipif(sys.platform != "linux", reason="fcntl semantics tested on Linux only")
def test_concurrent_appends_from_two_processes_no_corruption(tmp_path: Path):
    """Two processes each write 50 unique events. Result must contain
    exactly 100 distinct events, no malformed lines."""
    p = tmp_path / "log.jsonl"

    procs = [
        mp.Process(target=_worker_appends, args=(str(p), "A", 50)),
        mp.Process(target=_worker_appends, args=(str(p), "B", 50)),
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=30)
        assert proc.exitcode == 0, "worker exited with an error"

    events = read_events(p)
    ids = sorted(e.event_id for e in events)
    expected = sorted([f"A-{i:04d}" for i in range(50)] + [f"B-{i:04d}" for i in range(50)])
    assert ids == expected
