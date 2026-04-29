# Phase A.3 — `goldens/storage/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Add the `goldens/storage/` subpackage — `ids.py` (UUID
helpers), `log.py` (`fcntl`-locked append + read + idempotency on
`event_id`), `projection.py` (`build_state`, `active_entries`).

**Architecture:** Append-only JSONL event log, one file per dataset.
Cross-process safe via `fcntl.LOCK_EX`. Pure functions. Tolerant
reader skips malformed lines. Projection sorts by `timestamp_utc`
before reducing.

**Tech Stack:** Python stdlib only (`fcntl`, `os`, `json`,
`uuid`, `logging`, `pathlib`). Tests use `pytest`,
`multiprocessing` for concurrent-append.

**Spec:** `docs/superpowers/specs/2026-04-29-a3-goldens-storage-design.md`

---

## File Structure

```
features/goldens/src/goldens/storage/
├── __init__.py
├── ids.py
├── log.py
└── projection.py

features/goldens/tests/
├── test_storage_ids.py
├── test_storage_log.py
└── test_storage_projection.py
```

No new repo-level config — `goldens` is already in `bootstrap.sh`,
and the boundary check has no `core/llm_clients`-style restriction
on `goldens/storage/`.

---

## Task 0: Pre-flight

- [ ] **Step 1: Confirm clean tree on main, sync if needed**

```bash
git status
git rev-parse --abbrev-ref HEAD
```

Expected: `On branch main`, only `test.ipynb` (and possibly
`docs/agent-teams-setup.md`) untracked.

- [ ] **Step 2: Create work branch**

```bash
git checkout -b feat/a3-goldens-storage
```

- [ ] **Step 3: Capture baseline**

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

Expected: 276 tests pass (post-A.2 baseline).

---

## Task 1: `ids.py` + tests

**Files:**
- Create: `features/goldens/src/goldens/storage/__init__.py`
- Create: `features/goldens/src/goldens/storage/ids.py`
- Create: `features/goldens/tests/test_storage_ids.py`

### Step 1: Create directory

```bash
mkdir -p features/goldens/src/goldens/storage
```

### Step 2: Write `storage/__init__.py` (placeholder; full re-export comes in Task 4)

```python
"""Event-sourced storage layer for goldens. Public re-exports added
as modules land."""
```

### Step 3: Write `storage/ids.py`

```python
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
```

### Step 4: Write `tests/test_storage_ids.py`

```python
"""Tests for goldens.storage.ids."""

from __future__ import annotations

import re

from goldens.storage.ids import new_entry_id, new_event_id

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_event_id_is_uuid4_hex():
    eid = new_event_id()
    assert _HEX32.match(eid)


def test_entry_id_is_uuid4_hex():
    rid = new_entry_id()
    assert _HEX32.match(rid)


def test_event_ids_are_unique_across_many_calls():
    """Probabilistic — UUID4 collision odds are vanishingly small.
    1k calls is more than enough to catch a broken implementation."""
    ids = {new_event_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_entry_ids_are_unique_across_many_calls():
    ids = {new_entry_id() for _ in range(1000)}
    assert len(ids) == 1000
```

### Step 5: Run tests

```bash
.venv/bin/pytest features/goldens/tests/test_storage_ids.py -q
```

Expected: 4 tests pass.

### Step 6: Run full goldens suite (verify the package still installs / coverage threshold not tripped)

```bash
.venv/bin/pytest features/goldens/tests -q
```

Expected: 43 + 4 = 47 tests pass; coverage 100 % maintained.

If coverage trips because the new `__init__.py` is empty/unused, add
a `from goldens.storage import ids  # noqa: F401` import there to
ensure it's imported during tests (or simply re-run after Task 4 when
the full re-export lands).

### Step 7: Commit

```bash
git add features/goldens/src/goldens/storage features/goldens/tests/test_storage_ids.py
git commit -m "feat(goldens): add storage/ids.py with UUID4 helpers for events and entries"
```

---

## Task 2: `log.py` — fcntl-locked append + tolerant read

**Files:**
- Create: `features/goldens/src/goldens/storage/log.py`
- Create: `features/goldens/tests/test_storage_log.py`

This is the **most safety-critical task** in Phase A. Read every
step carefully.

### Step 1: Write `storage/log.py`

```python
"""Event log: append + read with cross-process locking and idempotency.

The log is a JSONL file. Each line is one Event serialized via
Event.to_dict(). Append is exclusive-locked (fcntl.LOCK_EX) and
fsync'd. Idempotency on event_id: re-appending the same id is a no-op.

Reading is tolerant: malformed lines are skipped with a WARNING log,
not raised. A missing file returns [].
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path

from goldens.schemas.base import Event

_log = logging.getLogger(__name__)


def append_event(path: Path, event: Event) -> None:
    """Append `event` to the JSONL log at `path`.

    Concurrency-safe across processes (fcntl.LOCK_EX). Idempotent on
    `event.event_id` — re-appending an existing id is a no-op.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # "a+" so we can read existing content under the lock to check
    # idempotency. Opening with "w" or "r+" risks truncation.
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            if _event_id_already_present(path, event.event_id):
                return
            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_events(path: Path) -> list[Event]:
    """Read all events from `path`. Tolerates malformed lines by
    skipping them with a warning. Returns [] if the file does not
    exist.
    """
    if not path.exists():
        return []
    out: list[Event] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(Event.from_dict(d))
            except (ValueError, KeyError) as e:
                _log.warning(
                    "skipping malformed event log line %d in %s: %s",
                    lineno, path, e,
                )
                continue
    return out


def _event_id_already_present(path: Path, event_id: str) -> bool:
    """Linear scan over the JSONL to check if event_id is recorded.
    Caller must hold the lock on `path`."""
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                # Malformed line — ignore for this check; read_events
                # will warn separately.
                continue
            if d.get("event_id") == event_id:
                return True
    return False
```

### Step 2: Write `tests/test_storage_log.py`

```python
"""Tests for goldens.storage.log — append, read, idempotency,
malformed-line tolerance, and cross-process concurrent append."""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
from pathlib import Path

import pytest

from goldens.schemas.base import Event
from goldens.storage.log import append_event, read_events


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


# --- Cross-process concurrent append (Linux only) ---------------


def _worker_appends(path_str: str, prefix: str, n: int) -> None:
    """Helper for concurrent-append test. Top-level so it pickles."""
    from pathlib import Path  # noqa: PLC0415  (worker re-imports)

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
```

### Step 3: Run tests

```bash
.venv/bin/pytest features/goldens/tests/test_storage_log.py -q
```

Expected: 8 tests pass (the concurrent-append test takes a few
seconds).

### Step 4: Run full goldens suite

```bash
.venv/bin/pytest features/goldens/tests -q
```

Expected: 47 + 8 = 55 tests pass; coverage on `storage/log.py` ≥ 95 %.

### Step 5: Commit

```bash
git add features/goldens/src/goldens/storage/log.py \
        features/goldens/tests/test_storage_log.py
git commit -m "feat(goldens): add storage/log.py with fcntl-locked append, idempotency, tolerant read"
```

If pre-commit fails, fix and re-stage. Do NOT use `--no-verify`.

---

## Task 3: `projection.py` — build_state + active_entries

**Files:**
- Create: `features/goldens/src/goldens/storage/projection.py`
- Create: `features/goldens/tests/test_storage_projection.py`

### Step 1: Write `storage/projection.py`

```python
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
from collections.abc import Iterable, Iterator

from goldens.schemas.base import Event, Review, actor_from_dict
from goldens.schemas.retrieval import RetrievalEntry

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
    state[ev.entry_id] = RetrievalEntry(
        entry_id=ev.entry_id,
        query=entry_data["query"],
        expected_chunk_ids=tuple(entry_data["expected_chunk_ids"]),
        chunk_hashes=dict(entry_data["chunk_hashes"]),
        review_chain=(review,),
        deprecated=False,
        refines=entry_data.get("refines"),
    )


def _apply_reviewed(state: dict[str, RetrievalEntry], ev: Event) -> None:
    entry = state.get(ev.entry_id)
    if entry is None:
        _log.warning(
            "skipping reviewed event for unknown entry_id %s (event_id=%s)",
            ev.entry_id, ev.event_id,
        )
        return
    review = Review(
        timestamp_utc=ev.timestamp_utc,
        action=ev.payload["action"],
        actor=actor_from_dict(ev.payload["actor"]),
        notes=ev.payload.get("notes"),
    )
    state[ev.entry_id] = _replace(entry, review_chain=entry.review_chain + (review,))


def _apply_deprecated(state: dict[str, RetrievalEntry], ev: Event) -> None:
    entry = state.get(ev.entry_id)
    if entry is None:
        _log.warning(
            "skipping deprecated event for unknown entry_id %s (event_id=%s)",
            ev.entry_id, ev.event_id,
        )
        return
    review = Review(
        timestamp_utc=ev.timestamp_utc,
        action="deprecated",
        actor=actor_from_dict(ev.payload["actor"]),
        notes=ev.payload.get("reason"),
    )
    state[ev.entry_id] = _replace(
        entry,
        review_chain=entry.review_chain + (review,),
        deprecated=True,
    )


def _replace(entry: RetrievalEntry, **changes) -> RetrievalEntry:
    """Frozen-dataclass replacement that preserves all other fields."""
    from dataclasses import replace  # noqa: PLC0415  (local import keeps top clean)

    return replace(entry, **changes)
```

### Step 2: Write `tests/test_storage_projection.py`

```python
"""Tests for goldens.storage.projection — build_state semantics,
out-of-order tolerance, refinement, orphan-event handling."""

from __future__ import annotations

import pytest

from goldens.schemas.base import Event, HumanActor, LLMActor
from goldens.storage.projection import active_entries, build_state


# --- helpers ------------------------------------------------------


def _human_actor_dict(level: str = "phd", name: str = "alice") -> dict:
    return {"kind": "human", "pseudonym": name, "level": level}


def _llm_actor_dict() -> dict:
    return {
        "kind": "llm",
        "model": "gpt-4o",
        "model_version": "2024-08-06",
        "prompt_template_version": "v1",
        "temperature": 0.0,
    }


def _created(
    *,
    event_id: str,
    entry_id: str = "r1",
    ts: str = "2026-04-29T10:00:00Z",
    actor: dict | None = None,
    action: str = "created_from_scratch",
    refines: str | None = None,
    query: str = "What is X?",
) -> Event:
    return Event(
        event_id=event_id,
        timestamp_utc=ts,
        event_type="created",
        entry_id=entry_id,
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor or _human_actor_dict(),
            "action": action,
            "notes": None,
            "entry_data": {
                "query": query,
                "expected_chunk_ids": ["c1", "c2"],
                "chunk_hashes": {"c1": "sha256:aaa", "c2": "sha256:bbb"},
                "refines": refines,
            },
        },
    )


def _reviewed(
    *,
    event_id: str,
    entry_id: str = "r1",
    ts: str = "2026-04-29T11:00:00Z",
    actor: dict | None = None,
    action: str = "approved",
) -> Event:
    return Event(
        event_id=event_id,
        timestamp_utc=ts,
        event_type="reviewed",
        entry_id=entry_id,
        schema_version=1,
        payload={
            "actor": actor or _human_actor_dict(level="expert", name="bob"),
            "action": action,
            "notes": "LGTM",
        },
    )


def _deprecated(
    *,
    event_id: str,
    entry_id: str = "r1",
    ts: str = "2026-04-29T12:00:00Z",
    actor: dict | None = None,
    reason: str | None = "obsolete",
) -> Event:
    return Event(
        event_id=event_id,
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=entry_id,
        schema_version=1,
        payload={
            "actor": actor or _human_actor_dict(),
            "reason": reason,
        },
    )


# --- tests --------------------------------------------------------


def test_created_event_yields_retrieval_entry():
    state = build_state([_created(event_id="e1")])
    assert "r1" in state
    entry = state["r1"]
    assert entry.query == "What is X?"
    assert entry.deprecated is False
    assert len(entry.review_chain) == 1
    assert entry.review_chain[0].action == "created_from_scratch"


def test_reviewed_appends_to_chain():
    state = build_state([
        _created(event_id="e1"),
        _reviewed(event_id="e2", action="approved"),
    ])
    chain = state["r1"].review_chain
    assert len(chain) == 2
    assert chain[0].action == "created_from_scratch"
    assert chain[1].action == "approved"
    assert isinstance(chain[1].actor, HumanActor)


def test_reviewed_with_llm_actor():
    state = build_state([
        _created(event_id="e1"),
        _reviewed(event_id="e2", actor=_llm_actor_dict(), action="rejected"),
    ])
    last = state["r1"].review_chain[-1]
    assert isinstance(last.actor, LLMActor)
    assert last.action == "rejected"


def test_deprecated_flips_flag_and_appends_review():
    state = build_state([
        _created(event_id="e1"),
        _deprecated(event_id="e2", reason="bad chunk hashes"),
    ])
    entry = state["r1"]
    assert entry.deprecated is True
    assert entry.review_chain[-1].action == "deprecated"
    assert entry.review_chain[-1].notes == "bad chunk hashes"


def test_orphan_reviewed_event_is_skipped_with_warning(caplog):
    with caplog.at_level("WARNING"):
        state = build_state([_reviewed(event_id="e1", entry_id="ghost")])
    assert state == {}
    assert any("ghost" in rec.message for rec in caplog.records)


def test_orphan_deprecated_event_is_skipped_with_warning(caplog):
    with caplog.at_level("WARNING"):
        state = build_state([_deprecated(event_id="e1", entry_id="ghost")])
    assert state == {}
    assert any("ghost" in rec.message for rec in caplog.records)


def test_out_of_order_events_are_sorted():
    """Reviewed event arrives BEFORE the created event in the input
    iterable. Projection must still apply created first."""
    state = build_state([
        _reviewed(event_id="e2", ts="2026-04-29T11:00:00Z"),
        _created(event_id="e1", ts="2026-04-29T10:00:00Z"),
    ])
    chain = state["r1"].review_chain
    assert [r.action for r in chain] == ["created_from_scratch", "approved"]


def test_refinement_creates_new_entry_and_deprecates_old():
    """Refinement contract: a created event for the new entry with
    `refines: <old>`, plus a deprecate event on the old."""
    state = build_state([
        _created(event_id="e1", entry_id="r-old", ts="2026-04-29T10:00:00Z"),
        _created(
            event_id="e2",
            entry_id="r-new",
            ts="2026-04-29T11:00:00Z",
            refines="r-old",
            query="What is X? (refined)",
        ),
        _deprecated(event_id="e3", entry_id="r-old", ts="2026-04-29T11:00:01Z"),
    ])
    assert state["r-old"].deprecated is True
    assert state["r-new"].deprecated is False
    assert state["r-new"].refines == "r-old"
    assert state["r-new"].query.endswith("(refined)")


def test_active_entries_filters_deprecated():
    state = build_state([
        _created(event_id="e1", entry_id="r1", ts="2026-04-29T10:00:00Z"),
        _created(event_id="e2", entry_id="r2", ts="2026-04-29T10:00:01Z"),
        _deprecated(event_id="e3", entry_id="r1", ts="2026-04-29T10:00:02Z"),
    ])
    actives = list(active_entries(state))
    assert {e.entry_id for e in actives} == {"r2"}


def test_non_retrieval_created_events_are_ignored():
    """Phase B/C entry types are silently skipped by this projection."""
    other = _created(event_id="e1")
    other.payload["task_type"] = "answer_quality"
    state = build_state([other])
    assert state == {}


def test_build_state_handles_empty_iterable():
    assert build_state([]) == {}
```

### Step 3: Run tests

```bash
.venv/bin/pytest features/goldens/tests/test_storage_projection.py -q
```

Expected: 11 tests pass.

### Step 4: Full goldens suite + coverage

```bash
.venv/bin/pytest features/goldens/tests -q
```

Expected: 55 + 11 = 66 tests pass; coverage ≥ 95 % on `storage/`.

### Step 5: Commit

```bash
git add features/goldens/src/goldens/storage/projection.py \
        features/goldens/tests/test_storage_projection.py
git commit -m "feat(goldens): add storage/projection.py with build_state and active_entries"
```

---

## Task 4: Wiring — public API exposure

**Files:**
- Modify: `features/goldens/src/goldens/storage/__init__.py`
- Modify: `features/goldens/src/goldens/__init__.py`

### Step 1: Replace `storage/__init__.py`

```python
"""Event-sourced storage layer for goldens."""

from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import active_entries, build_state

__all__ = [
    "active_entries",
    "append_event",
    "build_state",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

### Step 2: Update top-level `goldens/__init__.py`

Add the storage symbols to the existing schema re-exports:

```python
"""Event-sourced golden-set storage."""

from goldens.schemas import (
    Actor,
    Event,
    HumanActor,
    LLMActor,
    RetrievalEntry,
    Review,
    actor_from_dict,
)
from goldens.storage import (
    active_entries,
    append_event,
    build_state,
    new_entry_id,
    new_event_id,
    read_events,
)

__all__ = [
    "Actor",
    "Event",
    "HumanActor",
    "LLMActor",
    "RetrievalEntry",
    "Review",
    "active_entries",
    "actor_from_dict",
    "append_event",
    "build_state",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

### Step 3: Verify the public API

```bash
.venv/bin/python -c "from goldens import append_event, read_events, build_state, active_entries, new_event_id, new_entry_id; print('ok')"
```

Expected: `ok`.

### Step 4: Run full repo suite

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

Expected: 276 + 23 = 299 tests pass (276 baseline + 4 ids + 8 log + 11 projection).

### Step 5: Lint + pre-commit

```bash
.venv/bin/ruff check features/ scripts/
.venv/bin/mypy features/
.venv/bin/pre-commit run --all-files
```

Expected: all clean.

### Step 6: Commit

```bash
git add features/goldens/src/goldens/storage/__init__.py \
        features/goldens/src/goldens/__init__.py
git commit -m "feat(goldens): expose storage public API alongside schemas"
```

---

## Task 5: Final verification

- [ ] **Step 1: Coverage report on goldens**

```bash
.venv/bin/pytest features/goldens/tests --cov=goldens --cov-report=term 2>&1 | tail -15
```

Expected: ≥ 95 % overall on the goldens package; near-100 % on
`storage/log.py` and `storage/projection.py`.

- [ ] **Step 2: Full repo suite**

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

Expected: 299 tests pass.

- [ ] **Step 3: Lint + pre-commit**

```bash
.venv/bin/ruff check features/ scripts/
.venv/bin/mypy features/
.venv/bin/pre-commit run --all-files
```

- [ ] **Step 4: Inspect history**

```bash
git log --oneline main..HEAD
```

Expected: 5 commits (1 docs + 4 feat).

- [ ] **Step 5: Push + PR (only after explicit user approval)**

```bash
git push -u origin feat/a3-goldens-storage
gh pr create --title "Phase A.3: goldens/storage/ — event log, projection, idempotency" \
  --body "$(cat <<'EOF'
## Summary

Phase A.3 of the goldens restructure: the `goldens/storage/` package
per `docs/superpowers/specs/2026-04-29-a3-goldens-storage-design.md`.

- `ids.py` — UUID4 helpers (`new_event_id`, `new_entry_id`)
- `log.py` — `append_event` with `fcntl.LOCK_EX` and per-event
  idempotency on `event_id`; `read_events` tolerant of malformed
  lines
- `projection.py` — `build_state` reduces an event sequence to
  `dict[entry_id, RetrievalEntry]`, `active_entries` filters
  deprecated; orphan reviewed/deprecated events skipped with
  warning; out-of-order events sorted before reduction; refinement
  contract honoured (`refines` set on new entry, old marked
  deprecated)
- Cross-process safety verified by a `multiprocessing` test that
  appends 100 events from two processes and asserts no corruption

## Test plan

- [x] `pytest features/goldens/tests` — coverage ≥ 95 %
- [x] `pytest features/` — full suite 299 passed
- [x] Concurrent-append test: 2 processes × 50 events → 100 unique
      events, no malformed lines
- [x] Idempotency: same event_id twice → 1 line on disk
- [x] Out-of-order: timestamps not monotonic → projection still
      correct
- [x] `ruff`, `mypy`, `pre-commit` — clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Pause here for explicit user approval before pushing or creating the PR.**

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §3 Package layout | Task 1 (Steps 1-2) |
| §4 API | Tasks 1, 2, 3 |
| §5 Storage format | Task 2 (log.py append/read) |
| §6 Locking & durability | Task 2 (`fcntl.LOCK_EX`, fsync) |
| §7 Idempotency | Task 2 (`_event_id_already_present`, idempotency test) |
| §8 Projection semantics | Task 3 (build_state + tests for each branch) |
| §9 Test plan | Tasks 1, 2, 3 (each test row mapped) |

**Placeholder scan:** Clean — every step has the actual code and
exact commands.

**Type-consistency:** `Event`, `Review`, `RetrievalEntry`,
`HumanActor`, `LLMActor`, `actor_from_dict` are imported from
`goldens.schemas.base` / `goldens.schemas.retrieval` (Phase A.2's
public surface) — naming consistent across all tasks.

**Scope:** Self-contained — produces a fully working storage layer
that A.4 / A.5 / A.6 / A.7 can build against in parallel.
