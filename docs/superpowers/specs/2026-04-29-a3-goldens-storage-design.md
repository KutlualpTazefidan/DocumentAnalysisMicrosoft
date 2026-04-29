# Phase A.3 — `goldens/storage/` Design Spec

**Status:** Draft for review
**Date:** 2026-04-29
**Parent spec:** `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§4 Data Model, §5 Storage Design, §7 Phase A.3)

---

## 1. Scope

Build `goldens/storage/` — the event-sourced JSONL log and its
projection. This is the **datafsicherheits-kritisch** layer: a bug
here is data loss. The package consumes the schemas from A.2 and is
the foundation that A.4 (creation), A.5 (synthetic), A.6 (operations),
and A.7 (chunk-match rewire) depend on.

## 2. Goals & Non-Goals

### Goals

- Append-only JSONL event log with `fcntl.LOCK_EX` per write,
  `fsync` after each write.
- Idempotency: same `event_id` appended twice = no-op.
- Tolerant reader: malformed lines skipped with warning, not raised.
- Pure functions; no global state, no classes wrapping a path.
- Projection that reduces an event sequence into the current state
  (`dict[entry_id, RetrievalEntry]`) including refinement linkage
  and deprecation handling.
- Out-of-order tolerance — projection sorts events by
  `timestamp_utc` before reducing.
- Concurrent-safe across processes (verified by a multiprocessing
  test).
- 95 %+ coverage per `docs/evaluation/coverage-thresholds.md`.

### Non-Goals

- Streaming reads — `read_events` returns `list[Event]`. Move to
  iterator if a consumer needs >100k events.
- Sidecar idempotency index (bloom filter / on-disk hash set).
  Linear scan is the v1 contract; spec says it's acceptable up to
  ~100k events.
- Schema-version dispatch — v1 only. Future major bumps add a
  branch in `from_dict`-equivalent logic.
- `AnswerQualityEntry` / `ClassificationEntry` projection — Phase B
  / C respectively. v1 returns `dict[str, RetrievalEntry]` concrete.
- Server / HTTP layer — Phase A-Plus.

## 3. Package Layout

```
features/goldens/src/goldens/
└── storage/
    ├── __init__.py            ← public API re-exports
    ├── ids.py                 ← new_event_id, new_entry_id (UUID4)
    ├── log.py                 ← append_event, read_events
    └── projection.py          ← build_state, active_entries
```

No new `pyproject.toml`; `goldens` package already installed editable.
Tests live at `features/goldens/tests/` under `test_storage_*.py`.

## 4. API

```python
# goldens/storage/ids.py

def new_event_id() -> str:
    """UUID4 hex string. Idempotency key for events."""

def new_entry_id() -> str:
    """UUID4 hex string. Stable identity for an entry across refinements."""
```

```python
# goldens/storage/log.py

def append_event(path: Path, event: Event) -> None:
    """Append `event` to the JSONL log at `path`.

    Atomic w.r.t. concurrent writers (fcntl LOCK_EX).
    Idempotent on `event.event_id` — re-appending an existing id is a
    no-op (no exception, no duplicate line).

    Creates the file (and parent dirs) if missing.
    """

def read_events(path: Path) -> list[Event]:
    """Read all events from the JSONL log.

    Tolerant: malformed lines are skipped with a warning logged at
    WARNING level. Returns [] if the file does not exist.
    """
```

```python
# goldens/storage/projection.py

def build_state(events: Iterable[Event]) -> dict[str, RetrievalEntry]:
    """Reduce events into current state.

    Steps:
    1. Sort events by timestamp_utc ascending.
    2. For each `created` event with task_type=="retrieval",
       construct a RetrievalEntry with empty review_chain and
       deprecated=False, plus a Review entry derived from the
       created event's actor/action/notes/timestamp.
    3. For each `reviewed` event, append a Review to that entry's
       chain. Orphan reviewed events (entry_id never created) are
       skipped with a warning.
    4. For each `deprecated` event, set deprecated=True on the entry
       and append a Review with action="deprecated".

    Returns dict[entry_id, RetrievalEntry].
    """

def active_entries(state: dict[str, RetrievalEntry]) -> Iterator[RetrievalEntry]:
    """Yield entries from state where deprecated is False."""
```

## 5. Storage Format

One JSONL file per dataset. Each line is the JSON serialization of
one `Event` via `Event.to_dict()`. Path is supplied by the caller
(CLI / API), conventionally
`outputs/<doc-slug>/datasets/golden_events_v1.jsonl`.

The file is append-only at the protocol level. The storage layer
never rewrites or deletes lines. Compaction / archival are out of
scope for v1.

## 6. Locking & Durability

```python
def append_event(path: Path, event: Event) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            if _event_id_already_present(path, event.event_id):
                return                                           # idempotent no-op
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

Key points:

- `LOCK_EX` covers read-then-write — the idempotency check runs
  inside the lock to prevent a TOCTOU race.
- `fsync` after every write. Crash between `write` and `fsync` would
  lose the event; fsync turns it into "either fully written or not
  written".
- `path.open("a+")` for read-then-append. The idempotency check
  re-reads the file to look for the event_id; cheap up to ~100k
  events.

## 7. Idempotency

`_event_id_already_present(path, event_id)` performs a linear scan
over the JSONL, parsing only enough of each line to extract
`event_id`. Returns True if any existing line matches.

Trade-off documented:

- O(N) per append, O(N²) for a fresh ingest of N events.
- N = 1000: ~500K comparisons total, sub-second.
- N = 100K: ~5G comparisons total, several minutes total ingest.
  Acceptable for v1; revisit with a sidecar index when N > 100K
  becomes routine.
- The cost is paid once during ingest. Routine reads
  (`read_events` → `build_state`) are O(N), not O(N²).

## 8. Projection Semantics

### 8.1 Event-to-Review mapping

| event_type | payload action | Review.action |
|---|---|---|
| created | created_from_scratch / synthesised / imported_from_faq | same as payload |
| reviewed | accepted_unchanged / approved / rejected | same as payload |
| deprecated | (n/a) | "deprecated" |

The Review's `actor`, `notes`, `timestamp_utc` come from the event
payload (or top-level `event.timestamp_utc` for the timestamp).

### 8.2 Refinement

Refinement = create event for a new entry with `refines: <old_id>`
in payload, plus a deprecate event for the old entry. The projection
treats them as two independent events:

- The new entry shows up in `state` with `refines=<old_id>` set.
- The old entry's `deprecated` flag flips True via the deprecate
  event.

No cross-entry mutation in the projection. Consumers that want a
"chain" can walk `refines` themselves.

### 8.3 Out-of-order events

Events may arrive with non-monotonic timestamps (e.g. machine clock
skew, manual file editing). Projection sorts by `timestamp_utc`
before reducing. The sort is stable for identical timestamps; the
file order is preserved as the tie-breaker.

### 8.4 Orphan reviewed / deprecated events

Reviewed or deprecated events whose `entry_id` has no preceding
`created` event are **skipped with a WARNING log**, not raised. This
matches the "tolerant reader" stance of `read_events`. The motivation
is robustness: a corrupted partial sync should not block reading the
rest of the data.

## 9. Test Plan

| Test | What it proves |
|---|---|
| `test_ids.py::test_uuids_unique` | `new_*_id()` returns UUID4 hex, low collision |
| `test_log_append_writes_event` | Single append produces one JSONL line |
| `test_log_append_creates_parent_dirs` | Caller can pass nested path |
| `test_log_append_idempotent` | Same event_id twice → 1 line |
| `test_log_read_returns_events` | Round-trip via `Event.from_dict` |
| `test_log_read_returns_empty_when_missing` | No file → `[]` |
| `test_log_read_skips_malformed_line` | Bad JSON in middle → others returned, warning logged |
| `test_log_concurrent_append` | 2 `multiprocessing.Process` × 50 events each → 100 unique events, no malformed lines |
| `test_projection_created_event_yields_entry` | minimal happy path |
| `test_projection_reviewed_appends_to_chain` | reviewed event extends chain |
| `test_projection_deprecated_flips_flag` | deprecated event flips `deprecated=True` and appends Review |
| `test_projection_orphan_reviewed_event_logs_warning_and_skips` | tolerance |
| `test_projection_orphan_deprecated_event_logs_warning_and_skips` | tolerance |
| `test_projection_out_of_order_events_sorted` | non-monotonic timestamps → correct final state |
| `test_projection_refinement_creates_new_entry_and_deprecates_old` | the refinement contract |
| `test_active_entries_filters_deprecated` | helper works |

Coverage target: **95 %+** per `docs/evaluation/coverage-thresholds.md`.

The concurrent-append test is `@pytest.mark.skipif(sys.platform != "linux", ...)` — `fcntl` semantics differ on macOS / Windows.

## 10. Open Questions

None — design is a direct projection of the parent spec §5 onto the
file structure decided in §3.

## 11. Out of Scope

- Lock-aware retry on `BlockingIOError` — `LOCK_EX` blocks by
  default, so we never see this.
- Compaction (rewriting old events into a snapshot file) — separate
  tool, future phase.
- Snapshot/replay optimization — projection over the full log is
  O(N), fast enough until N > 100K.
- Async API — sync only, consistent with rest of codebase.
