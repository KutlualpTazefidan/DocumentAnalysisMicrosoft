# Phase A.6 — `goldens/operations/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `goldens/operations/` semantic layer (`add_review`, `refine`, `deprecate`) on top of the existing event log, plus the `append_events` storage primitive that `refine` requires for atomicity.

**Architecture:** Three single-function modules under `goldens/operations/` validate against the projected state (`build_state(read_events(path))`) before appending. `refine` writes two events atomically through a new `append_events(path, events)` storage helper. Two custom exceptions (`EntryNotFoundError`, `EntryDeprecatedError`) front the layer for synchronous user feedback and future FastAPI mapping.

**Tech Stack:** Python 3.11+, dataclasses, `fcntl` advisory locking, `pytest` + `pytest-cov`, `multiprocessing` for the concurrent-append test.

**Spec:** `docs/superpowers/specs/2026-04-29-a6-goldens-operations-design.md`

**Branch:** `feat/a6-operations` (already checked out)

---

## File Structure

```
features/goldens/
├── src/goldens/
│   ├── operations/                              ← NEW package
│   │   ├── __init__.py
│   │   ├── _time.py                             ← private now_utc_iso()
│   │   ├── errors.py
│   │   ├── add_review.py
│   │   ├── refine.py
│   │   └── deprecate.py
│   ├── schemas/
│   │   ├── base.py                              ← + CreateAction / ReviewAction aliases
│   │   └── __init__.py                          ← + re-export aliases
│   └── storage/
│       ├── log.py                               ← + append_events()
│       └── __init__.py                          ← + re-export append_events
└── tests/
    ├── test_storage_log_bulk.py                 ← NEW
    ├── test_operations__time.py                 ← NEW
    ├── test_operations_errors.py                ← NEW
    ├── test_operations_add_review.py            ← NEW
    ├── test_operations_deprecate.py             ← NEW
    └── test_operations_refine.py                ← NEW
```

**Two commits on `feat/a6-operations`:**

1. **`feat(goldens/storage): add append_events for atomic multi-event writes`** — Tasks 1.
2. **`feat(goldens): add operations layer (add_review, refine, deprecate)`** — Tasks 2–8.

Then a PR (Task 9).

**Helper used in every task:**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft-a6-operations
source .venv/bin/activate
```

The `goldens` package is already installed editable; tests for `goldens` honour the per-package `pyproject.toml` (`--cov=goldens --cov-fail-under=100 --cov-branch`). Run them as:

```bash
pytest features/goldens/ -v
```

---

## Task 1: Storage extension — `append_events` (atomic multi-event append)

**Files:**
- Create: `features/goldens/tests/test_storage_log_bulk.py`
- Modify: `features/goldens/src/goldens/storage/log.py`
- Modify: `features/goldens/src/goldens/storage/__init__.py`

- [ ] **Step 1.1: Write the failing tests for `append_events`**

Create `features/goldens/tests/test_storage_log_bulk.py`:

```python
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
from goldens.storage.log import append_event, append_events, read_events


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
```

- [ ] **Step 1.2: Run the new tests, expect failure**

```bash
pytest features/goldens/tests/test_storage_log_bulk.py -v --no-cov
```

Expected: All tests FAIL with `ImportError: cannot import name 'append_events' from 'goldens.storage.log'`.

- [ ] **Step 1.3: Implement `append_events` in `storage/log.py`**

Add the following to `features/goldens/src/goldens/storage/log.py` — keep the existing `append_event`, `read_events`, and `_event_id_already_present` unchanged.

Add a new helper `_existing_event_ids` (faster than per-id linear scans for the bulk case) and the new public `append_events`:

```python
def append_events(path: Path, events: list[Event]) -> None:
    """Append `events` atomically to the JSONL log at `path`.

    Atomic w.r.t. concurrent writers: a single fcntl.LOCK_EX covers
    the entire batch. Readers see all events from the batch or none.

    Idempotent per event: events whose event_id already exists in the
    log are silently skipped; the rest are written. Duplicates within
    `events` are also handled — the first occurrence wins, later ones
    with the same event_id are skipped.

    Empty list is a silent no-op (no lock acquired, no disk touch).
    fsync is called once at the end if anything was written.
    """
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            seen = _existing_event_ids(path)
            wrote_any = False
            for event in events:
                if event.event_id in seen:
                    continue
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
                seen.add(event.event_id)
                wrote_any = True
            if wrote_any:
                f.flush()
                os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _existing_event_ids(path: Path) -> set[str]:
    """Set of all event_ids currently in the log. Caller must hold the lock."""
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                d = json.loads(stripped)
            except ValueError:
                # Malformed line; read_events will warn separately on read.
                continue
            eid = d.get("event_id")
            if eid:
                ids.add(eid)
    return ids
```

- [ ] **Step 1.4: Re-export `append_events` from `storage/__init__.py`**

Replace the contents of `features/goldens/src/goldens/storage/__init__.py` with:

```python
"""Event-sourced storage layer for goldens."""

from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event, append_events, read_events
from goldens.storage.projection import active_entries, build_state

__all__ = [
    "active_entries",
    "append_event",
    "append_events",
    "build_state",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

- [ ] **Step 1.5: Run all goldens tests, expect pass**

```bash
pytest features/goldens/ -v
```

Expected: All tests PASS, coverage stays at 100%.

- [ ] **Step 1.6: Commit the storage extension**

```bash
git add features/goldens/src/goldens/storage/log.py \
        features/goldens/src/goldens/storage/__init__.py \
        features/goldens/tests/test_storage_log_bulk.py
git commit -m "$(cat <<'EOF'
feat(goldens/storage): add append_events for atomic multi-event writes

Single fcntl.LOCK_EX covers the whole batch — readers either see
all events from the batch or none. Per-event idempotency: any event
whose event_id already exists in the log is silently skipped (also
handles duplicates within the batch). Empty list is a silent no-op.

Used by goldens.operations.refine to write the new-entry-created and
old-entry-deprecated events under a single lock, preserving the
"all-or-nothing visibility" guarantee from the parent restructure
spec §4.2. Will also be the basis for batch-create flows in A.5
(synthetic generation, import_faq).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `CreateAction` / `ReviewAction` type aliases to `schemas/base.py`

**Files:**
- Modify: `features/goldens/src/goldens/schemas/base.py`
- Modify: `features/goldens/src/goldens/schemas/__init__.py`

The aliases are pure type definitions; no runtime semantics, no separate test needed. They are exercised when `add_review` and `refine` import them in later tasks.

- [ ] **Step 2.1: Add the aliases to `schemas/base.py`**

In `features/goldens/src/goldens/schemas/base.py`, add the two `Literal` aliases immediately after the `Actor = HumanActor | LLMActor` line:

```python
Actor = HumanActor | LLMActor


CreateAction = Literal["created_from_scratch", "synthesised", "imported_from_faq"]
ReviewAction = Literal["accepted_unchanged", "approved", "rejected"]


def actor_from_dict(d: dict) -> Actor:
```

(The `def actor_from_dict` line is the existing line that follows; the diff is the two `Action` lines plus a blank line above and below.)

- [ ] **Step 2.2: Re-export from `schemas/__init__.py`**

Replace the contents of `features/goldens/src/goldens/schemas/__init__.py` with:

```python
from goldens.schemas.base import (
    Actor,
    CreateAction,
    Event,
    HumanActor,
    LLMActor,
    Review,
    ReviewAction,
    actor_from_dict,
)
from goldens.schemas.retrieval import RetrievalEntry

__all__ = [
    "Actor",
    "CreateAction",
    "Event",
    "HumanActor",
    "LLMActor",
    "RetrievalEntry",
    "Review",
    "ReviewAction",
    "actor_from_dict",
]
```

- [ ] **Step 2.3: Run all goldens tests, expect pass (no regression)**

```bash
pytest features/goldens/ -v
```

Expected: All tests still PASS, coverage stays at 100%.

(No commit yet — this change is bundled with the operations layer in Task 8's commit.)

---

## Task 3: `operations/_time.py` — `now_utc_iso()` helper

**Files:**
- Create: `features/goldens/src/goldens/operations/__init__.py` (placeholder, finalised in Task 8)
- Create: `features/goldens/src/goldens/operations/_time.py`
- Create: `features/goldens/tests/test_operations__time.py`

- [ ] **Step 3.1: Create the operations package directory with an empty `__init__.py`**

Create `features/goldens/src/goldens/operations/__init__.py` containing only a single newline (it will be finalised in Task 8 after all submodules exist):

```python
```

- [ ] **Step 3.2: Write the failing test for `now_utc_iso`**

Create `features/goldens/tests/test_operations__time.py`:

```python
"""Tests for goldens.operations._time."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from goldens.operations._time import now_utc_iso


def test_now_utc_iso_format_is_iso8601_z():
    s = now_utc_iso()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s) is not None, s


def test_now_utc_iso_is_close_to_real_now():
    """The returned string should round-trip to a datetime within ~5s of `now`."""
    s = now_utc_iso()
    parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    diff = abs((datetime.now(UTC) - parsed).total_seconds())
    assert diff < 5
```

- [ ] **Step 3.3: Run the new tests, expect failure**

```bash
pytest features/goldens/tests/test_operations__time.py -v --no-cov
```

Expected: FAIL with `ModuleNotFoundError: No module named 'goldens.operations._time'`.

- [ ] **Step 3.4: Implement `_time.py`**

Create `features/goldens/src/goldens/operations/_time.py`:

```python
"""Internal time helper used by the operations layer."""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc_iso() -> str:
    """Current UTC time formatted as 'YYYY-MM-DDTHH:MM:SSZ'.

    Matches the parent spec's ISO-8601-with-Z naming convention. Tests
    that need deterministic timestamps should monkeypatch this function
    in the module that imports it (each operation imports it once)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 3.5: Run the tests, expect pass**

```bash
pytest features/goldens/tests/test_operations__time.py -v --no-cov
```

Expected: 2 PASS.

(No commit yet.)

---

## Task 4: `operations/errors.py` — exception classes

**Files:**
- Create: `features/goldens/src/goldens/operations/errors.py`
- Create: `features/goldens/tests/test_operations_errors.py`

- [ ] **Step 4.1: Write the failing test**

Create `features/goldens/tests/test_operations_errors.py`:

```python
"""Tests for goldens.operations.errors — exception hierarchy."""

from __future__ import annotations

from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError


def test_entry_not_found_is_lookup_error():
    """LookupError base lets a future FastAPI handler map to 404."""
    assert issubclass(EntryNotFoundError, LookupError)


def test_entry_deprecated_is_value_error():
    """ValueError base lets a future FastAPI handler map to 409."""
    assert issubclass(EntryDeprecatedError, ValueError)


def test_entry_not_found_message_carries_entry_id():
    err = EntryNotFoundError("r-missing")
    assert "r-missing" in str(err)


def test_entry_deprecated_message_carries_entry_id():
    err = EntryDeprecatedError("r-already-dep")
    assert "r-already-dep" in str(err)
```

- [ ] **Step 4.2: Run the test, expect failure**

```bash
pytest features/goldens/tests/test_operations_errors.py -v --no-cov
```

Expected: FAIL with `ModuleNotFoundError: No module named 'goldens.operations.errors'`.

- [ ] **Step 4.3: Implement `errors.py`**

Create `features/goldens/src/goldens/operations/errors.py`:

```python
"""Operations-layer exceptions.

Mapped to HTTP statuses by the future FastAPI layer (Phase A-Plus):
- EntryNotFoundError    → 404 Not Found
- EntryDeprecatedError  → 409 Conflict

The base classes (LookupError / ValueError) let consumers dispatch on
standard Python exceptions without importing this module directly."""


class EntryNotFoundError(LookupError):
    """Raised when an operation targets an entry_id that is not present
    in the projected state."""


class EntryDeprecatedError(ValueError):
    """Raised when an operation targets an entry that is already
    deprecated. Re-deprecation, reviewing a deprecated entry, and
    refining a deprecated entry all raise this."""
```

- [ ] **Step 4.4: Run the tests, expect pass**

```bash
pytest features/goldens/tests/test_operations_errors.py -v --no-cov
```

Expected: 4 PASS.

(No commit yet.)

---

## Task 5: `operations/add_review.py`

**Files:**
- Create: `features/goldens/src/goldens/operations/add_review.py`
- Create: `features/goldens/tests/test_operations_add_review.py`

- [ ] **Step 5.1: Write the failing tests**

Create `features/goldens/tests/test_operations_add_review.py`:

```python
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
            timestamp_utc="2026-04-29T09:00:00Z",
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
            timestamp_utc="2026-04-29T09:30:00Z",
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
```

- [ ] **Step 5.2: Run the tests, expect failure**

```bash
pytest features/goldens/tests/test_operations_add_review.py -v --no-cov
```

Expected: FAIL with `ModuleNotFoundError: No module named 'goldens.operations.add_review'`.

- [ ] **Step 5.3: Implement `add_review.py`**

Create `features/goldens/src/goldens/operations/add_review.py`:

```python
"""add_review — append a `reviewed` event to an existing entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goldens.operations._time import now_utc_iso
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import Event, HumanActor, LLMActor, ReviewAction
from goldens.storage.ids import new_event_id
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import build_state

if TYPE_CHECKING:
    from pathlib import Path


def add_review(
    path: Path,
    entry_id: str,
    *,
    actor: HumanActor | LLMActor,
    action: ReviewAction,
    notes: str | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Append a `reviewed` event for `entry_id`.

    Returns the new event_id.

    Raises:
        EntryNotFoundError: `entry_id` is not present in the projected state.
        EntryDeprecatedError: the entry is already deprecated.
    """
    state = build_state(read_events(path))
    if entry_id not in state:
        raise EntryNotFoundError(entry_id)
    if state[entry_id].deprecated:
        raise EntryDeprecatedError(entry_id)
    ts = timestamp_utc or now_utc_iso()
    eid = new_event_id()
    event = Event(
        event_id=eid,
        timestamp_utc=ts,
        event_type="reviewed",
        entry_id=entry_id,
        schema_version=1,
        payload={"actor": actor.to_dict(), "action": action, "notes": notes},
    )
    append_event(path, event)
    return eid
```

- [ ] **Step 5.4: Run the tests, expect pass**

```bash
pytest features/goldens/tests/test_operations_add_review.py -v --no-cov
```

Expected: 4 PASS.

(No commit yet.)

---

## Task 6: `operations/deprecate.py`

**Files:**
- Create: `features/goldens/src/goldens/operations/deprecate.py`
- Create: `features/goldens/tests/test_operations_deprecate.py`

- [ ] **Step 6.1: Write the failing tests**

Create `features/goldens/tests/test_operations_deprecate.py`:

```python
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
            timestamp_utc="2026-04-29T09:00:00Z",
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
```

- [ ] **Step 6.2: Run the tests, expect failure**

```bash
pytest features/goldens/tests/test_operations_deprecate.py -v --no-cov
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 6.3: Implement `deprecate.py`**

Create `features/goldens/src/goldens/operations/deprecate.py`:

```python
"""deprecate — mark an existing entry as no-longer-valid."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goldens.operations._time import now_utc_iso
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import Event, HumanActor, LLMActor
from goldens.storage.ids import new_event_id
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import build_state

if TYPE_CHECKING:
    from pathlib import Path


def deprecate(
    path: Path,
    entry_id: str,
    *,
    actor: HumanActor | LLMActor,
    reason: str | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Append a `deprecated` event for `entry_id`.

    Returns the new event_id.

    Raises:
        EntryNotFoundError: `entry_id` is not present in the projected state.
        EntryDeprecatedError: the entry is already deprecated. Re-deprecation
            is rejected; callers who want idempotent behaviour catch this.
    """
    state = build_state(read_events(path))
    if entry_id not in state:
        raise EntryNotFoundError(entry_id)
    if state[entry_id].deprecated:
        raise EntryDeprecatedError(entry_id)
    ts = timestamp_utc or now_utc_iso()
    eid = new_event_id()
    event = Event(
        event_id=eid,
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=entry_id,
        schema_version=1,
        payload={"actor": actor.to_dict(), "reason": reason},
    )
    append_event(path, event)
    return eid
```

- [ ] **Step 6.4: Run the tests, expect pass**

```bash
pytest features/goldens/tests/test_operations_deprecate.py -v --no-cov
```

Expected: 4 PASS.

(No commit yet.)

---

## Task 7: `operations/refine.py`

**Files:**
- Create: `features/goldens/src/goldens/operations/refine.py`
- Create: `features/goldens/tests/test_operations_refine.py`

- [ ] **Step 7.1: Write the failing tests**

Create `features/goldens/tests/test_operations_refine.py`:

```python
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
            timestamp_utc="2026-04-29T09:00:00Z",
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


def _seed_deprecate(path: Path, entry_id: str = "r-old") -> None:
    append_event(
        path,
        Event(
            event_id="seed-dep",
            timestamp_utc="2026-04-29T09:30:00Z",
            event_type="deprecated",
            entry_id=entry_id,
            schema_version=1,
            payload={"actor": _human().to_dict(), "reason": None},
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
        timestamp_utc="2026-04-29T12:00:00Z",
        deprecate_reason="r",
    )
    events = read_events(p)
    # 1 seed + 2 from refine
    assert len(events) == 3
    refine_events = events[1:]
    assert {ev.event_type for ev in refine_events} == {"created", "deprecated"}
    assert all(ev.timestamp_utc == "2026-04-29T12:00:00Z" for ev in refine_events)
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
    created_ev = next(e for e in events if e.event_type == "created" and e.event_id != "seed-created")
    assert created_ev.payload["action"] == "synthesised"
```

- [ ] **Step 7.2: Run the tests, expect failure**

```bash
pytest features/goldens/tests/test_operations_refine.py -v --no-cov
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 7.3: Implement `refine.py`**

Create `features/goldens/src/goldens/operations/refine.py`:

```python
"""refine — atomic create-new-entry + deprecate-old."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goldens.operations._time import now_utc_iso
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.schemas.base import CreateAction, Event, HumanActor, LLMActor
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_events, read_events
from goldens.storage.projection import build_state

if TYPE_CHECKING:
    from pathlib import Path


def refine(
    path: Path,
    old_entry_id: str,
    *,
    query: str,
    expected_chunk_ids: tuple[str, ...],
    chunk_hashes: dict[str, str],
    actor: HumanActor | LLMActor,
    action: CreateAction = "created_from_scratch",
    notes: str | None = None,
    deprecate_reason: str | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Refine `old_entry_id` — atomically create a new entry that
    points at the old via `refines`, and deprecate the old.

    Returns the NEW entry_id.

    Both events share the same `timestamp_utc` (one user action = one
    logical timestamp). The two events land in the log under a single
    fcntl.LOCK_EX via `append_events`.

    Raises:
        EntryNotFoundError: `old_entry_id` is not present in the projected state.
        EntryDeprecatedError: the old entry is already deprecated.
    """
    state = build_state(read_events(path))
    if old_entry_id not in state:
        raise EntryNotFoundError(old_entry_id)
    if state[old_entry_id].deprecated:
        raise EntryDeprecatedError(old_entry_id)

    ts = timestamp_utc or now_utc_iso()
    new_id = new_entry_id()
    actor_dict = actor.to_dict()

    create_ev = Event(
        event_id=new_event_id(),
        timestamp_utc=ts,
        event_type="created",
        entry_id=new_id,
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor_dict,
            "action": action,
            "notes": notes,
            "entry_data": {
                "query": query,
                "expected_chunk_ids": list(expected_chunk_ids),
                "chunk_hashes": dict(chunk_hashes),
                "refines": old_entry_id,
            },
        },
    )
    deprecate_ev = Event(
        event_id=new_event_id(),
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=old_entry_id,
        schema_version=1,
        payload={"actor": actor_dict, "reason": deprecate_reason},
    )
    append_events(path, [create_ev, deprecate_ev])
    return new_id
```

- [ ] **Step 7.4: Run the tests, expect pass**

```bash
pytest features/goldens/tests/test_operations_refine.py -v --no-cov
```

Expected: 5 PASS.

(No commit yet.)

---

## Task 8: Finalise `operations/__init__.py`, full-suite verification, commit 2

**Files:**
- Modify: `features/goldens/src/goldens/operations/__init__.py`

- [ ] **Step 8.1: Replace the placeholder `operations/__init__.py` with the public API**

Replace the contents of `features/goldens/src/goldens/operations/__init__.py` with:

```python
"""Operations layer — semantic API on top of the event log."""

from goldens.operations.add_review import add_review
from goldens.operations.deprecate import deprecate
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.operations.refine import refine

__all__ = [
    "EntryDeprecatedError",
    "EntryNotFoundError",
    "add_review",
    "deprecate",
    "refine",
]
```

- [ ] **Step 8.2: Run the full goldens suite, verify everything passes at 100% coverage**

```bash
pytest features/goldens/ -v
```

Expected output (last lines):

```
=== passed ===
TOTAL ... 100%
Required test coverage of 100% reached. Total coverage: 100.00%
```

If coverage < 100%, inspect the missing lines reported in `term-missing` and add a targeted test that covers them. Do not lower the threshold — operations is thin enough to hit 100% as designed.

- [ ] **Step 8.3: Run lint + type-check on the new code**

```bash
ruff check features/goldens/src/goldens/operations/ features/goldens/tests/
ruff format --check features/goldens/src/goldens/operations/ features/goldens/tests/
mypy features/goldens/ || [ $? -eq 2 ]
```

Expected: ruff clean. mypy may exit 2 (workspace tolerance per Makefile); inspect output and fix any new errors that mention `goldens/operations/`.

- [ ] **Step 8.4: Run the boundary check**

```bash
./scripts/check_import_boundary.sh
```

Expected: no violations. (Operations only imports from `goldens.schemas` and `goldens.storage`; no Azure / OpenAI / Anthropic touch points.)

- [ ] **Step 8.5: Commit the operations layer**

```bash
git add features/goldens/src/goldens/operations/ \
        features/goldens/src/goldens/schemas/base.py \
        features/goldens/src/goldens/schemas/__init__.py \
        features/goldens/tests/test_operations__time.py \
        features/goldens/tests/test_operations_errors.py \
        features/goldens/tests/test_operations_add_review.py \
        features/goldens/tests/test_operations_deprecate.py \
        features/goldens/tests/test_operations_refine.py
git commit -m "$(cat <<'EOF'
feat(goldens): add operations layer (add_review, refine, deprecate)

Three single-function modules under goldens/operations/ form the
semantic layer between the dumb storage pipe and the future CLI /
HTTP consumers:

  - add_review : append a `reviewed` event to an existing active entry
  - deprecate  : mark an entry as no-longer-valid (re-deprecate raises)
  - refine     : atomically create a new entry that supersedes an
                 existing active entry (uses storage.append_events)

Each operation reads events + projects state, validates that the
target entry exists and is not deprecated, then appends. Two custom
exceptions front the layer: EntryNotFoundError (LookupError) and
EntryDeprecatedError (ValueError) — base classes chosen so a future
FastAPI handler maps cleanly to 404 / 409.

Also adds CreateAction / ReviewAction Literal aliases to
goldens.schemas.base for typed action parameters, and a private
operations._time.now_utc_iso() helper used by all three operations.

Coverage stays at 100%.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8.6: Verify branch state**

```bash
git log --oneline -5
git status
```

Expected: two new commits on top of `42bdbe8` (the merge of A.3), working tree clean.

---

## Task 9: Push branch and open PR

**Files:** none (git-only).

- [ ] **Step 9.1: Push the branch to origin**

```bash
git push -u origin feat/a6-operations
```

- [ ] **Step 9.2: Open the PR**

Use `gh pr create` with the body referencing the spec fragment and naming both commits explicitly.

```bash
gh pr create --title "feat(goldens): A.6 operations layer (add_review, refine, deprecate)" --body "$(cat <<'EOF'
## Summary

Implements Phase A.6 from the goldens-restructure design — the semantic
operations layer on top of the event log, plus one storage primitive
(`append_events`) that `refine` requires for atomicity.

Spec fragment: `docs/superpowers/specs/2026-04-29-a6-goldens-operations-design.md`
Parent spec: `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` §4.2, §7 Phase A.6.

## Commits

1. **`feat(goldens/storage): add append_events for atomic multi-event writes`**
   Bulk append under a single `fcntl.LOCK_EX`; per-event idempotency;
   empty-list no-op. Concurrent-pairs-never-interleave test included.
   Reviewable in isolation as a safety-critical storage change.

2. **`feat(goldens): add operations layer (add_review, refine, deprecate)`**
   Three single-function modules + `EntryNotFoundError` /
   `EntryDeprecatedError`, `CreateAction` / `ReviewAction` type
   aliases in `schemas/base.py`, private `now_utc_iso()` helper.

## Notable design decisions (locked in spec fragment)

- `refine` writes its two events through `append_events` so readers see
  both or neither — matching the parent spec's atomicity wording.
- Operations validate the projected state before appending; a
  microsecond read-then-write race is documented as a known limitation
  (§7 of the spec fragment) — closing it is rejected as too costly for
  the operationally-harmless failure modes.
- `load_state(path)` deferred to avoid a merge conflict with Phase A.7
  (which is concurrently extending `storage/projection.py`). The
  `build_state(read_events(path))` composition is repeated inline three
  times instead.

## Test plan

- [x] `features/goldens/tests/test_storage_log_bulk.py` (5 tests, incl. concurrent on Linux)
- [x] `features/goldens/tests/test_operations__time.py` (2 tests)
- [x] `features/goldens/tests/test_operations_errors.py` (4 tests)
- [x] `features/goldens/tests/test_operations_add_review.py` (4 tests)
- [x] `features/goldens/tests/test_operations_deprecate.py` (4 tests)
- [x] `features/goldens/tests/test_operations_refine.py` (5 tests)
- [x] `pytest features/goldens/ -v` → all PASS, coverage 100%
- [x] `ruff check`, `ruff format --check` clean
- [x] `./scripts/check_import_boundary.sh` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 9.3: Print PR URL**

The previous command prints the PR URL on success; relay it to the user.

---

## Coverage Decision Note

`pyproject.toml` keeps `--cov-fail-under=100`. Spec sets `goldens/operations/` floor at 90%, but the actual implementation reaches 100% because every branch is covered by the tests above:

- `EntryNotFoundError` branch covered by `*_raises_entry_not_found_for_unknown_id` tests
- `EntryDeprecatedError` branch covered by `*_raises_entry_deprecated_when_already_deprecated` tests
- happy-path branch covered by `*_appends_event_*` / `*_creates_new_entry_*` tests
- `timestamp_utc` default-vs-override covered by `*_respects_explicit_timestamp` tests
- `append_events` empty-list / file-missing / dup-in-batch / dup-in-file / concurrent branches all have dedicated tests

If a coverage gap surfaces, prefer adding a focused test over lowering the threshold.
