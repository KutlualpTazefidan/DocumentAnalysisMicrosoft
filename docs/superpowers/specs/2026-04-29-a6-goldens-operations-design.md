# Phase A.6 — `goldens/operations/` Design Spec

**Status:** Draft for review
**Date:** 2026-04-29
**Parent spec:** `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§4.2 Event payloads, §7 Phase A.6)
**Depends on:** A.2 (`goldens/schemas/`), A.3 (`goldens/storage/`)

This fragment concretises the parent spec's Phase A.6 entry. It does
not supersede the parent — it adds the function signatures, exception
hierarchy, and one storage extension required to land the operations
layer.

---

## 1. Scope

Build `goldens/operations/` — the **semantic layer** between the dumb
storage pipe and the eventual CLI / HTTP consumers. Three operations:

- `add_review` — an actor signs off (or rejects) an existing entry.
- `refine` — a new entry replaces an existing one, atomically.
- `deprecate` — an entry is marked invalid.

Plus one storage extension required by `refine`'s atomicity contract:

- `append_events(path, events)` — atomic multi-event append under a
  single `flock`.

## 2. Goals & Non-Goals

### Goals

- Single source of truth for the **business rules** of the goldens
  workflow: "you cannot review a non-existent entry", "you cannot
  refine a deprecated entry", "deprecating twice is rejected".
- Synchronous, typed errors — `EntryNotFoundError`,
  `EntryDeprecatedError` — that future consumers (CLI exit codes,
  FastAPI 4xx mapping) can dispatch on directly.
- `refine`'s two events (`created` for the new entry, `deprecated`
  for the old) land **atomically** — readers either see both or
  neither, per parent spec §4.2.
- 90 %+ coverage per `docs/evaluation/coverage-thresholds.md`. In
  practice this layer hits 100 % because every branch is reachable
  from a small fixture.

### Non-Goals

- A `load_state(path)` convenience helper. Tempting (it would name
  the canonical `build_state(read_events(path))` composition), but
  Phase A.7 is concurrently extending `goldens/storage/projection.py`
  with `iter_active_retrieval_entries`. Both fragments would touch
  the same file and the same `__init__.py` re-exports. Avoiding the
  merge conflict is worth the 3× repeated inline call. A future
  phase can extract it.
- Read-then-append atomicity. Operations validate (read state) then
  write (append event); a microsecond race between the two is
  documented as a known limitation, not closed (see §7).
- HTTP exposure. Phase A.5 wraps these operations; this fragment
  builds the in-process Python API only.
- Bulk operations. A future `import_faq` or batched `synthesise`
  may want a single read + N validations + one `append_events`. Not
  in this fragment.
- Backwards-compatible "soft deprecate" — re-deprecation raises, it
  does not no-op. Callers who want idempotency catch the exception.

## 3. Package Layout

```
features/goldens/src/goldens/
├── operations/                       ← NEW
│   ├── __init__.py                   ← public API re-exports
│   ├── _time.py                      ← private now_utc_iso() helper
│   ├── errors.py                     ← EntryNotFoundError, EntryDeprecatedError
│   ├── add_review.py
│   ├── refine.py
│   └── deprecate.py
├── schemas/
│   └── base.py                       ← + CreateAction / ReviewAction Type-Aliases
└── storage/
    └── log.py                        ← + append_events()
```

No new `pyproject.toml`; `goldens` package is already installed
editable. Tests live at `features/goldens/tests/` under
`test_operations_*.py` and `test_storage_log_bulk.py`.

## 4. API

### 4.1 Storage extension — `append_events`

```python
# goldens/storage/log.py

def append_events(path: Path, events: list[Event]) -> None:
    """Append `events` atomically to the JSONL log at `path`.

    Atomic w.r.t. concurrent writers: a single `fcntl.LOCK_EX`
    covers the entire batch. Readers either see all events from
    this batch or none of them.

    Idempotent per event: events whose `event_id` already exists in
    the log are silently skipped; the rest are written. (Matches
    `append_event`'s single-event semantics.)

    Empty list → silent no-op (no lock acquired, no disk touch).

    `fsync` is called once after the batch is written.
    """
```

`append_event` (the existing single-event API) is retained
unchanged — `add_review` and `deprecate` use it.

### 4.2 Type aliases — `schemas/base.py`

```python
CreateAction = Literal["created_from_scratch", "synthesised", "imported_from_faq"]
ReviewAction = Literal["accepted_unchanged", "approved", "rejected"]
```

Three lines. Pulls the action enumeration out of the operation
signatures and into the schema layer. The existing `Review.action`
literal is left as-is to avoid touching A.2's frozen tests; the
aliases are additive.

### 4.3 Exceptions — `operations/errors.py`

```python
class EntryNotFoundError(LookupError):
    """Raised when an operation targets an entry_id that is not
    present in the projected state."""

class EntryDeprecatedError(ValueError):
    """Raised when an operation targets an entry that is already
    deprecated. Re-deprecation, reviewing a deprecated entry, and
    refining a deprecated entry all raise this."""
```

`LookupError` / `ValueError` as base classes so a future FastAPI
mapping can pattern-match without importing `goldens.operations`:

| Exception                | base         | HTTP status (Phase A-Plus) |
|--------------------------|--------------|----------------------------|
| `EntryNotFoundError`     | `LookupError`| 404 Not Found              |
| `EntryDeprecatedError`   | `ValueError` | 409 Conflict               |

### 4.4 Time helper — `operations/_time.py`

```python
def now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with `Z` suffix.

    Format: 'YYYY-MM-DDTHH:MM:SSZ' (second precision; matches the
    parent spec's naming-conventions clause)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
```

Underscore-prefixed module — private to `operations/`. Tests
monkey-patch this when they need deterministic timestamps.

### 4.5 Operations

```python
# goldens/operations/add_review.py

def add_review(
    path: Path,
    entry_id: str,
    *,
    actor: HumanActor | LLMActor,
    action: ReviewAction,
    notes: str | None = None,
    timestamp_utc: str | None = None,   # default: now_utc_iso()
) -> str:
    """Append a `reviewed` event for `entry_id`. Returns the new
    event_id.

    Validates against the projected state:
    - `EntryNotFoundError` if `entry_id` is unknown.
    - `EntryDeprecatedError` if the entry is deprecated.

    See §7 for the documented read-then-write race window.
    """
```

```python
# goldens/operations/deprecate.py

def deprecate(
    path: Path,
    entry_id: str,
    *,
    actor: HumanActor | LLMActor,
    reason: str | None = None,
    timestamp_utc: str | None = None,
) -> str:
    """Append a `deprecated` event for `entry_id`. Returns the new
    event_id.

    Validates against the projected state:
    - `EntryNotFoundError` if `entry_id` is unknown.
    - `EntryDeprecatedError` if the entry is already deprecated.
      (Re-deprecation is rejected; callers who want idempotent
      behaviour catch the exception.)
    """
```

```python
# goldens/operations/refine.py

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
    """Refine an existing entry. Atomically writes:
      - a `created` event for the new entry, with refines=old_entry_id
      - a `deprecated` event for the old entry

    Both events share the same `timestamp_utc` (one user action =
    one logical timestamp). The projection's stable sort + file
    order keeps them ordered as written.

    Returns the **new** entry_id.

    Validates the OLD entry against the projected state:
    - `EntryNotFoundError` if `old_entry_id` is unknown.
    - `EntryDeprecatedError` if it is already deprecated.
    """
```

### 4.6 Public surface — `operations/__init__.py`

```python
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

`operations/_time.py` is intentionally not re-exported — it is an
internal implementation detail of the operations layer.

## 5. Validation Strategy

Every operation follows the same shape:

```python
state = build_state(read_events(path))    # canonical "current state"
if entry_id not in state:                 # for refine: old_entry_id
    raise EntryNotFoundError(entry_id)
if state[entry_id].deprecated:
    raise EntryDeprecatedError(entry_id)
event = Event(...)                        # construct
append_event(path, event)                 # or append_events for refine
return event.event_id                     # or new entry_id for refine
```

The composition `build_state(read_events(path))` repeats inline in
all three operations. This is intentional (see §2 Non-Goals); the
duplication is one line and the file-touch surface is kept off the
projection module to avoid the A.7 merge conflict.

## 6. Refinement: writing two events

```python
# inside refine():

now = timestamp_utc or now_utc_iso()
new_entry_id_ = new_entry_id()

create_ev = Event(
    event_id=new_event_id(),
    timestamp_utc=now,
    event_type="created",
    entry_id=new_entry_id_,
    schema_version=1,
    payload={
        "task_type": "retrieval",
        "actor": actor.to_dict(),
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
    timestamp_utc=now,
    event_type="deprecated",
    entry_id=old_entry_id,
    schema_version=1,
    payload={"actor": actor.to_dict(), "reason": deprecate_reason},
)
append_events(path, [create_ev, deprecate_ev])
return new_entry_id_
```

Both events carry the same `timestamp_utc` because they describe a
single user action. The projection sorts stably; events with equal
timestamps fall back to insertion order, which `append_events`
preserves.

## 7. Race window — documented, not closed

`add_review` / `refine` / `deprecate` read state, decide, then
append. A concurrent writer can deprecate the same entry between
the read and the append. The losing operation's event lands on a
now-deprecated entry. The projection then shows:

- For `add_review`: a Review chain ending in `..., deprecated, approved`
  on an entry where `deprecated=True`. The entry stays out of
  `active_entries()`; eval ignores it. Mildly misleading, not
  corrupting.
- For `deprecate`: two `deprecated` events on the same entry. The
  projection applies the second as a no-op flip (already True) and
  appends a second "deprecated" Review. Doubly redundant, harmless.
- For `refine`: a `created` event for a new entry whose `refines`
  pointer references an already-deprecated old. The new entry is
  active; the old is doubly-deprecated. Refinement chain stays
  intact.

Closing the race would require a new storage primitive
(`read_then_append(path, decide_fn)` that holds the lock across
read+decide+write). That is rejected because:

- The lock-hold time would scale with log size (linear scan per
  read), starving other writers.
- The single-machine FastAPI deployment in Phase A-Plus has
  effectively one writer (worker count ≤ 4) on a deployment with
  ≤ 20 trusted users; collision probability is microscopic.
- The failure modes above are operationally harmless (no data
  corruption, no lost work).

## 8. Test Plan

| Test                                                   | What it proves                                                                        |
|--------------------------------------------------------|---------------------------------------------------------------------------------------|
| `test_storage_log_bulk::append_events_writes_all`      | `append_events([a, b])` produces two JSONL lines                                      |
| `test_storage_log_bulk::append_events_empty_is_noop`   | `append_events([])` does not touch disk                                               |
| `test_storage_log_bulk::append_events_skips_duplicates`| One existing event_id + one new → only the new one is written                         |
| `test_storage_log_bulk::append_events_concurrent_no_interleave` | 2 procs, each writing 50 pairs → 100 pairs, never interleaved (Linux only)   |
| `test_operations_add_review::raises_on_unknown_entry`  | `EntryNotFoundError`                                                                  |
| `test_operations_add_review::raises_on_deprecated`     | `EntryDeprecatedError`                                                                |
| `test_operations_add_review::happy_path`               | Event appended, return value = event_id, projection picks up the review               |
| `test_operations_add_review::respects_timestamp_override` | `timestamp_utc` arg used verbatim                                                  |
| `test_operations_deprecate::raises_on_unknown_entry`   | `EntryNotFoundError`                                                                  |
| `test_operations_deprecate::raises_on_already_deprecated` | `EntryDeprecatedError`                                                             |
| `test_operations_deprecate::happy_path`                | `deprecated=True` after, Review with action="deprecated" appended                     |
| `test_operations_refine::raises_on_unknown_old`        | `EntryNotFoundError`                                                                  |
| `test_operations_refine::raises_on_deprecated_old`     | `EntryDeprecatedError`                                                                |
| `test_operations_refine::happy_path`                   | new entry exists with `refines=<old>`, old is deprecated, both events share timestamp |
| `test_operations_refine::atomic_write`                 | Both events present in the JSONL after a single call                                  |
| `test_operations__time::now_utc_iso_format`            | Z-suffix, UTC, second precision                                                       |
| `test_operations_errors::exception_hierarchy`          | `EntryNotFoundError` is a `LookupError`; `EntryDeprecatedError` is a `ValueError`     |

Coverage target: **90 %+** per `docs/evaluation/coverage-thresholds.md`.
The package-wide `--cov-fail-under=100` in `pyproject.toml` stays —
this layer is thin enough to hit it without contortions.

The `append_events_concurrent_no_interleave` test is
`@pytest.mark.skipif(sys.platform != "linux", ...)` — `fcntl`
semantics differ on macOS / Windows.

## 9. Commit / Plan Granularity

The implementation lands as **two distinct commits** on the A.6
branch, in order:

1. **`feat(goldens/storage): add append_events for atomic multi-event writes`**
   — touches only `storage/log.py`, `storage/__init__.py`,
   `tests/test_storage_log_bulk.py`. Lets the reviewer audit the
   safety-critical `fcntl` change in isolation.
2. **`feat(goldens): add operations layer (add_review, refine, deprecate)`**
   — adds `operations/`, the type aliases in `schemas/base.py`,
   and the operations tests. Depends on commit 1.

PR description names both, with explicit pointers so the reviewer
knows why `storage/` is touched in an `operations`-themed PR.

## 10. Open Questions

None. Two design questions resolved during brainstorming and locked:

1. Refinement atomicity → storage extension `append_events`
   (vs. two single appends, vs. fcntl in operations). Rationale:
   parent spec wording, real future use (synthetic / import_faq),
   small cost.
2. Operations validate state vs. blind append → validate, with the
   read-then-write race documented as known limitation. Rationale:
   business rules belong here, not in N consumers; race window
   harmless and closing it is expensive.

## 11. Out of Scope

- `load_state(path)` helper — deferred to avoid the A.7 merge
  conflict (see §2).
- Bulk-validating operations — write a `bulk_*` family in a future
  phase if `import_faq` needs them.
- An `OperationError` umbrella exception — current two-class
  hierarchy is enough; collapsing would lose the 404/409
  granularity for FastAPI.
- Timestamps with sub-second precision — second precision matches
  the existing log format and the parent spec's conventions.
