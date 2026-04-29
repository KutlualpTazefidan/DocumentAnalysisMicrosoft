# Phase A.7 — chunk_match Rewire onto goldens/storage/ Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewire `evaluators/chunk_match/` to consume `RetrievalEntry` projections from `goldens/storage/` instead of the old `EvalExample`-JSONL. Delete the obsolete `EvalExample`/`load_dataset` surface in the same PR.

**Architecture:** Add one canonical reader (`iter_active_retrieval_entries`) and one filename constant (`GOLDEN_EVENTS_V1_FILENAME`) to `goldens`. Reshape `run_eval` to take an `Iterable[RetrievalEntry]` so the runner is storage-format-agnostic; CLI does the path → entries glue. Rename `query_id` → `entry_id` everywhere it surfaces in metrics output. Drop the per-example `filter` field (Microsoft-OData-coupled, no curated data uses it).

**Tech Stack:** Python 3.12 · pytest · dataclasses (frozen) · fcntl-locked JSONL event log (existing) · ruff · mypy · pre-commit hooks.

**Spec:** `docs/superpowers/specs/2026-04-29-a7-chunk-match-rewire-design.md`

---

## File Structure

### Modified (goldens side)

| Path | Change |
|---|---|
| `features/goldens/src/goldens/storage/projection.py` | Add `iter_active_retrieval_entries(path)` (3-line composition). |
| `features/goldens/src/goldens/storage/__init__.py` | Export `iter_active_retrieval_entries` and `GOLDEN_EVENTS_V1_FILENAME` (source of truth). |
| `features/goldens/src/goldens/__init__.py` | Re-export both new symbols + extend `__all__`. |
| `features/goldens/tests/test_storage_projection.py` | Add 5 tests (3 for `iter_active_retrieval_entries` + 2 for filename constant + re-exports). |

### Modified (chunk_match side)

| Path | Change |
|---|---|
| `features/evaluators/chunk_match/src/query_index_eval/runner.py` | New `run_eval` signature: `Iterable[RetrievalEntry]` keyword-only; drop per-example filter; drop `EvalExample` import; rename to `entry_id` / `drifted_entry_ids`. |
| `features/evaluators/chunk_match/src/query_index_eval/cli.py` | Use `iter_active_retrieval_entries`; new `DEFAULT_DATASET` and `DEFAULT_REPORTS_DIR`; FileNotFound check returns exit code 2. |
| `features/evaluators/chunk_match/src/query_index_eval/schema.py` | Remove `EvalExample`; rename `QueryRecord.query_id → entry_id` and `RunMetadata.drifted_query_ids → drifted_entry_ids`. |
| `features/evaluators/chunk_match/src/query_index_eval/__init__.py` | Drop `EvalExample` and `load_dataset` from re-exports. |
| `features/evaluators/chunk_match/tests/test_runner.py` | Rewrite all surviving tests around `make_entry` fixture; drop the per-example filter test. |
| `features/evaluators/chunk_match/tests/test_cli.py` | Update path expectations to `outputs/datasets/golden_events_v1.jsonl`; new mock-patch path; new FileNotFound test. |
| `features/evaluators/chunk_match/tests/test_schema.py` | Drop `test_eval_example_*` (3 tests); rename `query_id` field references. |
| `features/evaluators/chunk_match/tests/test_public_api.py` | Drop `EvalExample`/`load_dataset` from expected set; add negative assertion. |
| `features/evaluators/chunk_match/tests/conftest.py` | Drop `sample_example_dict` and `tmp_dataset_path` fixtures; add `make_entry` fixture. |
| `features/evaluators/chunk_match/README.md` | Drop `EvalExample`/`load_dataset` mentions; update import example and dataset description. |

### Deleted

- `features/evaluators/chunk_match/src/query_index_eval/datasets.py`
- `features/evaluators/chunk_match/tests/test_datasets.py`

### Pre-A.7 baseline

`pytest features/evaluators/chunk_match/` reports **95.52 % coverage** with 68 passing tests as of `42bdbe8` (last commit on `main` at branch-off). Post-A.7 must reach ≥ 90 % (CI floor) and ≥ 95.52 % (baseline) without justification.

---

## Task 1: Add `iter_active_retrieval_entries` to `goldens.storage.projection`

**Files:**
- Modify: `features/goldens/src/goldens/storage/projection.py`
- Modify: `features/goldens/src/goldens/storage/__init__.py`
- Modify: `features/goldens/src/goldens/__init__.py`
- Test: `features/goldens/tests/test_storage_projection.py`

- [ ] **Step 1: Write the failing test (round-trip)**

Append to `features/goldens/tests/test_storage_projection.py` (at end of file):

```python
# --- iter_active_retrieval_entries (canonical evaluator read path) -----


def test_iter_active_retrieval_entries_returns_only_active_entries(tmp_path):
    """Round-trip: write 1 active + 1 deprecated entry via append_event,
    materialize the iterator, expect just the active entry."""
    from goldens.storage.log import append_event
    from goldens.storage.projection import iter_active_retrieval_entries

    p = tmp_path / "events.jsonl"
    append_event(p, _created(event_id="e1", entry_id="r-active", ts="2026-04-29T10:00:00Z"))
    append_event(p, _created(event_id="e2", entry_id="r-old", ts="2026-04-29T10:00:01Z"))
    append_event(p, _deprecated(event_id="e3", entry_id="r-old", ts="2026-04-29T10:00:02Z"))

    entries = list(iter_active_retrieval_entries(p))
    assert {e.entry_id for e in entries} == {"r-active"}
    assert entries[0].query == "What is X?"


def test_iter_active_retrieval_entries_returns_empty_when_file_missing(tmp_path):
    """Tolerant: missing file → empty iterator (read_events returns [])."""
    from goldens.storage.projection import iter_active_retrieval_entries

    p = tmp_path / "absent.jsonl"
    assert list(iter_active_retrieval_entries(p)) == []
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
cd /home/ktazefid/Documents/projects/DocumentAnalysisMicrosoft-a7-chunk-match
source .venv/bin/activate
pytest features/goldens/tests/test_storage_projection.py::test_iter_active_retrieval_entries_returns_only_active_entries -v
```

Expected: `ImportError: cannot import name 'iter_active_retrieval_entries' from 'goldens.storage.projection'`.

- [ ] **Step 3: Add the function**

Append to `features/goldens/src/goldens/storage/projection.py` (at end of file):

```python
def iter_active_retrieval_entries(path: Path) -> Iterator[RetrievalEntry]:
    """Canonical read path for evaluators: read events from `path`,
    project to state, yield active (non-deprecated) entries.

    Drop to read_events / build_state / active_entries if you need
    deprecated entries, the full state dict, or non-retrieval task types.
    """
    return active_entries(build_state(read_events(path)))
```

Also add `from pathlib import Path` to the runtime imports if not already present (currently only under `TYPE_CHECKING`). Move the `Path` import out of `TYPE_CHECKING` and the `read_events` import to module-level:

```python
# Replace the current TYPE_CHECKING block at the top of projection.py:
from pathlib import Path

from goldens.schemas.base import Event, Review, actor_from_dict
from goldens.schemas.retrieval import RetrievalEntry
from goldens.storage.log import read_events

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
```

- [ ] **Step 4: Re-export from `storage/__init__.py`**

Edit `features/goldens/src/goldens/storage/__init__.py`:

```python
"""Event-sourced storage layer for goldens."""

from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import (
    active_entries,
    build_state,
    iter_active_retrieval_entries,
)

__all__ = [
    "active_entries",
    "append_event",
    "build_state",
    "iter_active_retrieval_entries",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

- [ ] **Step 5: Re-export from `goldens/__init__.py`**

Edit `features/goldens/src/goldens/__init__.py`:

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
    iter_active_retrieval_entries,
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
    "iter_active_retrieval_entries",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

- [ ] **Step 6: Add the top-level re-export test**

Append to `features/goldens/tests/test_storage_projection.py`:

```python
def test_iter_active_retrieval_entries_re_exported_from_goldens_top_level():
    """Catch the most common refactor bug — symbol silently dropped from __init__."""
    from goldens import iter_active_retrieval_entries  # noqa: F401
```

- [ ] **Step 7: Run all goldens tests + coverage**

```bash
pytest features/goldens/ -v
```

Expected: all tests pass; coverage stays at 100 % (the new function is covered by the round-trip test).

- [ ] **Step 8: Commit**

```bash
git add features/goldens/src/goldens/storage/projection.py \
        features/goldens/src/goldens/storage/__init__.py \
        features/goldens/src/goldens/__init__.py \
        features/goldens/tests/test_storage_projection.py
git commit -m "$(cat <<'EOF'
feat(goldens): add iter_active_retrieval_entries canonical reader

Composition of read_events → build_state → active_entries — the
default read path every evaluator needs. Re-exported from both
goldens.storage and goldens top-level for tab-complete discoverability.

Phase A.7 spec §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `GOLDEN_EVENTS_V1_FILENAME` constant to `goldens.storage`

**Files:**
- Modify: `features/goldens/src/goldens/storage/__init__.py`
- Modify: `features/goldens/src/goldens/__init__.py`
- Test: `features/goldens/tests/test_storage_projection.py`

- [ ] **Step 1: Write the failing tests**

Append to `features/goldens/tests/test_storage_projection.py`:

```python
def test_golden_events_v1_filename_is_storage_contract():
    """The filename ties the events log to its schema version (v1).
    A future _v2 schema would introduce GOLDEN_EVENTS_V2_FILENAME."""
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME

    assert GOLDEN_EVENTS_V1_FILENAME == "golden_events_v1.jsonl"


def test_golden_events_v1_filename_re_exported_from_goldens_top_level():
    from goldens import GOLDEN_EVENTS_V1_FILENAME as top_level
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME as storage_level

    assert top_level == storage_level
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
pytest features/goldens/tests/test_storage_projection.py::test_golden_events_v1_filename_is_storage_contract -v
```

Expected: `ImportError: cannot import name 'GOLDEN_EVENTS_V1_FILENAME' from 'goldens.storage'`.

- [ ] **Step 3: Define the constant in `storage/__init__.py`**

Edit `features/goldens/src/goldens/storage/__init__.py`:

```python
"""Event-sourced storage layer for goldens."""

from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event, read_events
from goldens.storage.projection import (
    active_entries,
    build_state,
    iter_active_retrieval_entries,
)

GOLDEN_EVENTS_V1_FILENAME = "golden_events_v1.jsonl"

__all__ = [
    "GOLDEN_EVENTS_V1_FILENAME",
    "active_entries",
    "append_event",
    "build_state",
    "iter_active_retrieval_entries",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

- [ ] **Step 4: Re-export from `goldens/__init__.py`**

Edit `features/goldens/src/goldens/__init__.py`:

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
    GOLDEN_EVENTS_V1_FILENAME,
    active_entries,
    append_event,
    build_state,
    iter_active_retrieval_entries,
    new_entry_id,
    new_event_id,
    read_events,
)

__all__ = [
    "Actor",
    "Event",
    "GOLDEN_EVENTS_V1_FILENAME",
    "HumanActor",
    "LLMActor",
    "RetrievalEntry",
    "Review",
    "active_entries",
    "actor_from_dict",
    "append_event",
    "build_state",
    "iter_active_retrieval_entries",
    "new_entry_id",
    "new_event_id",
    "read_events",
]
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
pytest features/goldens/ -v
```

Expected: all tests pass; coverage 100 %.

- [ ] **Step 6: Commit**

```bash
git add features/goldens/src/goldens/storage/__init__.py \
        features/goldens/src/goldens/__init__.py \
        features/goldens/tests/test_storage_projection.py
git commit -m "$(cat <<'EOF'
feat(goldens): add GOLDEN_EVENTS_V1_FILENAME storage contract

Filename = storage contract (ties to schema version v1); lives in
goldens.storage. Re-exported from goldens for top-level convenience.
Repo directory layout (outputs/<slug>/datasets/) stays with the caller.

Phase A.7 spec §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Verify pre-A.7 chunk_match coverage baseline

**Files:** none (informational task)

- [ ] **Step 1: Re-measure baseline on the current branch**

```bash
pytest features/evaluators/chunk_match/ -q --tb=no 2>&1 | tail -5
```

Expected: `Required test coverage of 90% reached. Total coverage: 95.52%` (or higher — the floor for post-A.7 is whichever is higher between this number and 90 %). Record the actual measured number; if it differs, use the measured number as the new baseline floor.

No commit; this is a verification step.

---

## Task 4: Add `make_entry` fixture to chunk_match conftest

**Files:**
- Modify: `features/evaluators/chunk_match/tests/conftest.py`

This is purely additive — does not break any existing test.

- [ ] **Step 1: Add fixture and required imports**

Edit `features/evaluators/chunk_match/tests/conftest.py`:

```python
"""Shared fixtures for query_index_eval tests.

The `query_index` package is patched at module level so that no test in this
suite ever touches Azure. Fixtures expose: a temporary JSONL path, sample
EvalExample objects, a sample MetricsReport, and a make_entry factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from goldens import RetrievalEntry, new_entry_id

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _patch_get_chunk():
    """Prevent any test from calling the real get_chunk (which hits Azure).

    Tests that need specific get_chunk behaviour override this by adding their
    own ``patch("query_index_eval.runner.get_chunk", ...)`` context manager,
    which takes precedence over this autouse patch.
    """
    with patch("query_index_eval.runner.get_chunk", return_value=MagicMock(chunk="")):
        yield


@pytest.fixture
def tmp_dataset_path(tmp_path: Path) -> Path:
    return tmp_path / "golden_v1.jsonl"


@pytest.fixture
def sample_example_dict() -> dict:
    return {
        "query_id": "g0001",
        "query": "Wo ist die Änderung des Tragkorbdurchmessers aufgeführt?",
        "expected_chunk_ids": ["c42"],
        "source": "curated",
        "chunk_hashes": {"c42": "sha256:abc"},
        "filter": None,
        "deprecated": False,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }


@pytest.fixture
def make_entry():
    """Factory for RetrievalEntry test instances. review_chain=() yields
    level='synthetic' (legal — see schemas.retrieval._highest_level)."""
    def _make(
        entry_id: str | None = None,
        query: str = "Q?",
        expected: tuple[str, ...] = ("c1",),
        chunk_hashes: dict[str, str] | None = None,
        deprecated: bool = False,
    ) -> RetrievalEntry:
        return RetrievalEntry(
            entry_id=entry_id or new_entry_id(),
            query=query,
            expected_chunk_ids=expected,
            chunk_hashes=chunk_hashes or {c: f"sha256:{c}" for c in expected},
            review_chain=(),
            deprecated=deprecated,
        )
    return _make
```

- [ ] **Step 2: Verify nothing broke**

```bash
pytest features/evaluators/chunk_match/ -q --tb=no
```

Expected: 68 tests pass, coverage unchanged from baseline.

- [ ] **Step 3: Commit**

```bash
git add features/evaluators/chunk_match/tests/conftest.py
git commit -m "$(cat <<'EOF'
test(chunk_match): add make_entry fixture for RetrievalEntry construction

Purely additive — used by the upcoming runner-test rewrite. Empty
review_chain is legal (level returns 'synthetic'); __post_init__ only
validates entry_id and query non-empty.

Phase A.7 spec §5.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Rename `QueryRecord.query_id` → `entry_id`

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/schema.py:62-69`
- Modify: `features/evaluators/chunk_match/src/query_index_eval/runner.py:142`
- Modify: `features/evaluators/chunk_match/tests/test_schema.py:71-79`
- Modify: `features/evaluators/chunk_match/tests/test_runner.py:78,98`

This is an atomic name change — production code and tests update together to keep CI green.

- [ ] **Step 1: Edit schema.py**

In `features/evaluators/chunk_match/src/query_index_eval/schema.py`, find the `QueryRecord` dataclass (lines 62-69) and rename:

```python
@dataclass(frozen=True)
class QueryRecord:
    entry_id: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    ranks: list[int]
    hits: list[bool]
    latency_ms: float
```

- [ ] **Step 2: Edit runner.py**

In `features/evaluators/chunk_match/src/query_index_eval/runner.py`, find line 142 (the `QueryRecord(query_id=...)` call) and rename the keyword:

```python
per_query.append(
    QueryRecord(
        entry_id=example.query_id,
        expected_chunk_ids=list(example.expected_chunk_ids),
        retrieved_chunk_ids=retrieved_ids,
        ranks=ranks,
        hits=hit_flags,
        latency_ms=latency_ms,
    )
)
```

(Reading from `example.query_id` is still correct here — `EvalExample` is still in use until Task 7. The `entry_id` keyword refers to `QueryRecord.entry_id`, not `EvalExample.query_id`.)

- [ ] **Step 3: Edit test_schema.py**

In `features/evaluators/chunk_match/tests/test_schema.py`, find `test_query_record_holds_per_query_data` (≈ line 68) and update both the constructor call and the test body:

```python
def test_query_record_holds_per_query_data() -> None:
    from query_index_eval.schema import QueryRecord

    r = QueryRecord(
        entry_id="g0001",
        expected_chunk_ids=["c42"],
        retrieved_chunk_ids=["c10", "c42", "c7"],
        ranks=[2],
        hits=[True],
        latency_ms=110.0,
    )
    assert r.ranks == [2]
    assert r.hits == [True]
    assert r.entry_id == "g0001"
```

Also find `test_metrics_report_composes_all_subobjects` and update the `QueryRecord` constructor call:

```python
record = QueryRecord("g0001", ["c42"], ["c42"], [1], [True], 110.0)
```

This is a positional-args call — first arg is `entry_id`. Stays as-is (the value `"g0001"` is bound to whatever the first field is named; only the field's *name* changed, not the position).

- [ ] **Step 4: Edit test_runner.py**

In `features/evaluators/chunk_match/tests/test_runner.py`, find lines around 78 and 98 referring to `query_id` on report records, and rename:

Line ≈ 78 — in `test_run_eval_skips_deprecated_examples`:

```python
assert report.per_query[0].entry_id == "g0001"
```

(Other references — search the file for `.query_id` on `report.per_query[*]` and rename. There may be additional ones in `test_run_eval_records_ranks_and_hits_per_query` if it asserts on it.)

Run `grep -n "query_id" features/evaluators/chunk_match/tests/test_runner.py` to enumerate all hits, then rename only those that refer to `QueryRecord` (the `_example_dict` rows have `"query_id": "g..."` strings — those refer to `EvalExample.query_id` and must stay as-is in this task; they go away in Task 7).

- [ ] **Step 5: Run tests**

```bash
pytest features/evaluators/chunk_match/ -q --tb=short
```

Expected: all 68 tests still pass. If a test fails because it accesses `.query_id` on a report record, fix that test in the same edit.

- [ ] **Step 6: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/schema.py \
        features/evaluators/chunk_match/src/query_index_eval/runner.py \
        features/evaluators/chunk_match/tests/test_schema.py \
        features/evaluators/chunk_match/tests/test_runner.py
git commit -m "$(cat <<'EOF'
refactor(chunk_match): rename QueryRecord.query_id → entry_id

Aligns report vocabulary with the new event-sourced model. The runner
still reads from EvalExample.query_id (input) until Task 7 swaps to
RetrievalEntry — the rename only affects the OUTPUT field name.

Phase A.7 spec §4.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Rename `RunMetadata.drifted_query_ids` → `drifted_entry_ids`

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/schema.py:57`
- Modify: `features/evaluators/chunk_match/src/query_index_eval/runner.py:191`
- Modify: `features/evaluators/chunk_match/tests/test_runner.py:299,345`

- [ ] **Step 1: Edit schema.py**

In `features/evaluators/chunk_match/src/query_index_eval/schema.py`, find `RunMetadata` and rename the field:

```python
@dataclass(frozen=True)
class RunMetadata:
    dataset_path: str
    dataset_size_active: int
    dataset_size_deprecated: int
    embedding_deployment_name: str
    embedding_model_version: str
    azure_openai_api_version: str
    search_index_name: str
    run_timestamp_utc: str
    size_status: str
    drifted_entry_ids: list[str] = field(default_factory=list)
    drift_warning: bool = False
```

- [ ] **Step 2: Edit runner.py**

In `features/evaluators/chunk_match/src/query_index_eval/runner.py`, around line 191, rename the keyword in the `RunMetadata(...)` constructor call:

```python
metadata = RunMetadata(
    dataset_path=str(dataset_path),
    dataset_size_active=len(active),
    dataset_size_deprecated=deprecated_count,
    embedding_deployment_name=cfg.embedding_deployment_name,
    embedding_model_version=cfg.embedding_model_version,
    azure_openai_api_version=cfg.azure_openai_api_version,
    search_index_name=cfg.ai_search_index_name,
    run_timestamp_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    size_status=_size_status(len(active)),
    drifted_entry_ids=drifted_ids,
    drift_warning=drift_warning,
)
```

- [ ] **Step 3: Edit test_runner.py**

In `features/evaluators/chunk_match/tests/test_runner.py`, find the two drift tests (around lines 299 and 345) and rename:

```python
assert "g0001" in report.metadata.drifted_entry_ids
# ...
assert report.metadata.drifted_entry_ids == []
```

- [ ] **Step 4: Run tests**

```bash
pytest features/evaluators/chunk_match/ -q --tb=short
```

Expected: all 68 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/schema.py \
        features/evaluators/chunk_match/src/query_index_eval/runner.py \
        features/evaluators/chunk_match/tests/test_runner.py
git commit -m "$(cat <<'EOF'
refactor(chunk_match): rename RunMetadata.drifted_query_ids → drifted_entry_ids

Same rename rationale as Task 5 — the IDs reported here will be UUID4
hex entry_ids once the runner consumes RetrievalEntry in Task 7.

Phase A.7 spec §4.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Switch `run_eval` to entries-based signature; drop per-example filter

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/runner.py` (whole file)
- Modify: `features/evaluators/chunk_match/tests/test_runner.py` (rewrite all surviving tests)

This is the largest task. The runner gives up storage-format awareness; tests gain `make_entry` and lose `_write_dataset` JSONL helpers.

- [ ] **Step 1: Replace `runner.py` with the new shape**

Overwrite `features/evaluators/chunk_match/src/query_index_eval/runner.py`:

```python
"""Evaluation orchestration.

Consumes an iterable of RetrievalEntry (active, non-deprecated entries
as projected by goldens.iter_active_retrieval_entries), runs each
through query_index's hybrid search, computes per-query records and
aggregate metrics, and returns a MetricsReport ready for serialization.
"""

from __future__ import annotations

import hashlib
import statistics
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from goldens import RetrievalEntry
from query_index import Config, get_chunk, hybrid_search

from query_index_eval.metrics import (
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
)
from query_index_eval.schema import (
    AggregateMetrics,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


SIZE_THRESHOLD_INDICATIVE = 30
SIZE_THRESHOLD_REPORTABLE = 100


def _size_status(n: int) -> str:
    if n < SIZE_THRESHOLD_INDICATIVE:
        return "indicative"
    if n < SIZE_THRESHOLD_REPORTABLE:
        return "preliminary"
    return "reportable"


def _ranks_and_hits(expected: list[str], retrieved: list[str]) -> tuple[list[int], list[bool]]:
    """For each expected chunk_id, the 1-based rank in retrieved (or -1 if absent),
    and a parallel hits list."""
    ranks: list[int] = []
    hits: list[bool] = []
    for chunk_id in expected:
        if chunk_id in retrieved:
            ranks.append(retrieved.index(chunk_id) + 1)
            hits.append(True)
        else:
            ranks.append(-1)
            hits.append(False)
    return ranks, hits


def _mean(values: Iterable[float]) -> float:
    vs = list(values)
    return sum(vs) / len(vs) if vs else 0.0


def _p95(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    sorted_l = sorted(latencies)
    idx = int(0.95 * (len(sorted_l) - 1))
    return sorted_l[idx]


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _hash_chunk(text: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def _check_drift(
    entries: list[RetrievalEntry],
    cfg: Config,
) -> list[str]:
    """Return entry_ids whose expected chunks no longer match recorded hashes."""
    drifted: list[str] = []
    for entry in entries:
        if not entry.chunk_hashes:
            continue
        for chunk_id, expected_hash in entry.chunk_hashes.items():
            try:
                actual = get_chunk(chunk_id, cfg)
            except Exception:  # chunk not in index is also drift
                drifted.append(entry.entry_id)
                break
            actual_hash = _hash_chunk(actual.chunk)
            if actual_hash != expected_hash:
                drifted.append(entry.entry_id)
                break
    return drifted


def run_eval(
    entries: Iterable[RetrievalEntry],
    *,
    dataset_path: str,
    top_k_max: int = 20,
    filter_default: str | None = None,
    cfg: Config | None = None,
) -> MetricsReport:
    if cfg is None:
        cfg = Config.from_env()

    entries = list(entries)  # materialize: support iterator inputs, multi-pass logic

    drifted_ids = _check_drift(entries, cfg)
    drift_warning = len(drifted_ids) > max(1, len(entries) // 10)

    per_query: list[QueryRecord] = []
    latencies: list[float] = []
    failures = 0

    for entry in entries:
        try:
            t0 = time.perf_counter()
            hits = hybrid_search(
                entry.query,
                top=top_k_max,
                filter=filter_default,
                cfg=cfg,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            retrieved_ids = [h.chunk_id for h in hits]
            ranks, hit_flags = _ranks_and_hits(list(entry.expected_chunk_ids), retrieved_ids)
            per_query.append(
                QueryRecord(
                    entry_id=entry.entry_id,
                    expected_chunk_ids=list(entry.expected_chunk_ids),
                    retrieved_chunk_ids=retrieved_ids,
                    ranks=ranks,
                    hits=hit_flags,
                    latency_ms=latency_ms,
                )
            )
            latencies.append(latency_ms)
        except Exception:
            failures += 1

    pairs = [(set(r.expected_chunk_ids), r.retrieved_chunk_ids) for r in per_query]
    aggregate = AggregateMetrics(
        recall_at_5=_mean(
            recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 5) for r in per_query
        ),
        recall_at_10=_mean(
            recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 10) for r in per_query
        ),
        recall_at_20=_mean(
            recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 20) for r in per_query
        ),
        map_score=mean_average_precision(pairs),
        hit_rate_at_1=_mean(
            hit_rate_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 1) for r in per_query
        ),
        mrr=_mean(mrr(set(r.expected_chunk_ids), r.retrieved_chunk_ids) for r in per_query),
    )

    operational = OperationalMetrics(
        mean_latency_ms=statistics.fmean(latencies) if latencies else 0.0,
        p95_latency_ms=_p95(latencies),
        total_queries=len(per_query),
        total_embedding_calls=len(per_query),
        failure_count=failures,
    )

    metadata = RunMetadata(
        dataset_path=dataset_path,
        dataset_size_active=len(entries),
        # Boundary-filtered upstream (iter_active_retrieval_entries); the
        # runner sees only active entries and cannot count deprecateds.
        # Eval reports record what was *evaluated*; total/deprecated counts
        # belong to a future `goldens info <path>` summary tool.
        dataset_size_deprecated=0,
        embedding_deployment_name=cfg.embedding_deployment_name,
        embedding_model_version=cfg.embedding_model_version,
        azure_openai_api_version=cfg.azure_openai_api_version,
        search_index_name=cfg.ai_search_index_name,
        run_timestamp_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        size_status=_size_status(len(entries)),
        drifted_entry_ids=drifted_ids,
        drift_warning=drift_warning,
    )

    return MetricsReport(
        aggregate=aggregate,
        operational=operational,
        metadata=metadata,
        per_query=per_query,
    )
```

Key changes vs. previous: imports `RetrievalEntry` from `goldens` (no longer `EvalExample` from local schema); `dataset_path` is `str`, keyword-only; per-example `filter` resolution dropped (`filter=filter_default` flat); `dataset_size_deprecated=0` because filtering happens upstream at the boundary (the runner only ever sees active entries — see CLI in Task 8).

- [ ] **Step 2: Replace `test_runner.py` with the new shape**

Overwrite `features/evaluators/chunk_match/tests/test_runner.py`:

```python
"""Tests for query_index_eval.runner.run_eval()."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from goldens import RetrievalEntry


def _hit(chunk_id: str, score: float = 0.5):
    """Build a minimal SearchHit-like object."""
    from query_index.types import SearchHit

    return SearchHit(chunk_id=chunk_id, title="t", chunk="x", score=score)


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replicate query-index env-var fixture (conftest scopes don't cross packages)."""
    values = {
        "AI_FOUNDRY_KEY": "test-foundry-key",
        "AI_FOUNDRY_ENDPOINT": "https://test-foundry.example.com",
        "AI_SEARCH_KEY": "test-search-key",
        "AI_SEARCH_ENDPOINT": "https://test-search.example.com",
        "AI_SEARCH_INDEX_NAME": "test-index",
        "EMBEDDING_DEPLOYMENT_NAME": "test-embedding-deployment",
        "EMBEDDING_MODEL_VERSION": "1",
        "EMBEDDING_DIMENSIONS": "3072",
        "AZURE_OPENAI_API_VERSION": "2024-02-01",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


def test_run_eval_records_entry_id_in_per_query(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entry = make_entry(query="What is X?", expected=("c1",))

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=[entry], dataset_path="test")

    assert len(report.per_query) == 1
    assert report.per_query[0].entry_id == entry.entry_id


def test_run_eval_records_ranks_and_hits_per_query(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entry = make_entry(expected=("c2", "c4"))

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3, 4, 5]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=[entry], dataset_path="test")

    record = report.per_query[0]
    assert record.expected_chunk_ids == ["c2", "c4"]
    assert record.retrieved_chunk_ids == ["c1", "c2", "c3", "c4", "c5"]
    assert record.ranks == [2, 4]
    assert record.hits == [True, True]


def test_run_eval_records_minus_one_rank_when_expected_not_found(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entry = make_entry(expected=("c99",))

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=[entry], dataset_path="test")

    record = report.per_query[0]
    assert record.ranks == [-1]
    assert record.hits == [False]


def test_run_eval_aggregates_metrics_across_queries(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [
        make_entry(entry_id="e1", query="Q1", expected=("c1",)),
        make_entry(entry_id="e2", query="Q2", expected=("c2",)),
        make_entry(entry_id="e3", query="Q3", expected=("c99",)),
    ]
    call_to_results = {
        "Q1": [_hit("c1"), _hit("c5"), _hit("c6")],
        "Q2": [_hit("c4"), _hit("c2"), _hit("c6")],
        "Q3": [_hit("c4"), _hit("c5"), _hit("c6")],
    }

    def fake_search(query, top, filter=None, cfg=None):
        return call_to_results[query]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    # Hit rate@1: only e1 has rank 1 -> 1/3
    assert report.aggregate.hit_rate_at_1 == pytest.approx(1 / 3)
    # MRR: (1 + 1/2 + 0) / 3 = 0.5
    assert report.aggregate.mrr == pytest.approx(0.5)
    # Recall@5: e1 1.0, e2 1.0, e3 0.0; mean = 2/3
    assert report.aggregate.recall_at_5 == pytest.approx(2 / 3)


def test_run_eval_assigns_size_status_indicative_for_small_n(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [make_entry() for _ in range(5)]

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    assert report.metadata.size_status == "indicative"


def test_run_eval_assigns_size_status_preliminary_in_30_to_99(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [make_entry() for _ in range(50)]

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    assert report.metadata.size_status == "preliminary"


def test_run_eval_assigns_size_status_reportable_at_100(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [make_entry() for _ in range(100)]

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    assert report.metadata.size_status == "reportable"


def test_run_eval_metadata_includes_embedding_index_and_dataset_path(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(
            entries=[make_entry()],
            dataset_path="outputs/test/datasets/golden_events_v1.jsonl",
        )

    md = report.metadata
    assert md.dataset_path == "outputs/test/datasets/golden_events_v1.jsonl"
    assert md.embedding_deployment_name == env_vars["EMBEDDING_DEPLOYMENT_NAME"]
    assert md.embedding_model_version == env_vars["EMBEDDING_MODEL_VERSION"]
    assert md.azure_openai_api_version == env_vars["AZURE_OPENAI_API_VERSION"]
    assert md.search_index_name == env_vars["AI_SEARCH_INDEX_NAME"]
    assert md.run_timestamp_utc.endswith("Z")


def test_run_eval_passes_filter_default_to_hybrid_search(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """Per-example filter is gone (Microsoft-OData-coupled); per-run
    filter via filter_default still passes through to hybrid_search."""
    from query_index_eval.runner import run_eval

    captured: dict = {}

    def fake_search(query, top, filter=None, cfg=None):
        captured["filter"] = filter
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        run_eval(
            entries=[make_entry()],
            dataset_path="test",
            filter_default="category eq 'manual'",
        )

    assert captured["filter"] == "category eq 'manual'"


def test_run_eval_detects_hash_drift_when_chunk_content_changed(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """If an expected chunk's hash no longer matches what is in the index,
    runner records the entry's entry_id in drifted_entry_ids."""
    from query_index_eval.runner import run_eval

    entry = make_entry(
        entry_id="e1",
        expected=("c1",),
        chunk_hashes={"c1": "sha256:expected-hash-from-curation-time"},
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk

        return Chunk(chunk_id="c1", title="T", chunk="DIFFERENT CONTENT NOW")

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(entries=[entry], dataset_path="test")

    assert "e1" in report.metadata.drifted_entry_ids


def test_run_eval_no_drift_when_hash_matches(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """If the chunk's hash matches, drifted_entry_ids stays empty."""
    import hashlib

    from query_index_eval.runner import run_eval

    chunk_text = "exact same content"
    expected_hash = (
        "sha256:" + hashlib.sha256(" ".join(chunk_text.split()).encode("utf-8")).hexdigest()
    )

    entry = make_entry(
        entry_id="e1",
        expected=("c1",),
        chunk_hashes={"c1": expected_hash},
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk

        return Chunk(chunk_id="c1", title="T", chunk=chunk_text)

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(entries=[entry], dataset_path="test")

    assert report.metadata.drifted_entry_ids == []


def test_run_eval_accepts_iterator_input_and_materializes_internally(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """run_eval accepts any Iterable[RetrievalEntry], including a single-use
    iterator. Internal `list(entries)` enables drift-then-eval multi-pass."""
    from query_index_eval.runner import run_eval

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(
            entries=iter([make_entry(), make_entry()]),
            dataset_path="test",
        )

    assert len(report.per_query) == 2
```

Notes on what changed vs. the old file:

- `_write_dataset` and `_example_dict` helpers gone — entries built via `make_entry` fixture from conftest.
- `test_run_eval_skips_deprecated_examples` deleted (the contract moved to the CLI boundary; the corresponding CLI test is added in Task 8).
- `test_run_eval_passes_filter_per_example_when_set` deleted (per-example filter removed; see spec §4.2). Replaced by `test_run_eval_passes_filter_default_to_hybrid_search` which exercises the per-run filter.
- New `test_run_eval_accepts_iterator_input_and_materializes_internally` covers the `list(entries)` materialization branch.
- `tmp_dataset_path` fixture no longer used by any test in this file.

- [ ] **Step 3: Run tests**

```bash
pytest features/evaluators/chunk_match/tests/test_runner.py -v
```

Expected: all 12 tests pass (1 new entry_id test, 1 new iterator test, replacing the dropped per-example-filter and skips-deprecated tests).

```bash
pytest features/evaluators/chunk_match/ -q --tb=short
```

Expected: full suite still passes (other test files use old-style EvalExample paths but those are still valid until Task 9).

- [ ] **Step 4: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/runner.py \
        features/evaluators/chunk_match/tests/test_runner.py
git commit -m "$(cat <<'EOF'
refactor(chunk_match): switch run_eval to entries-based signature

run_eval now takes Iterable[RetrievalEntry] keyword-only with
dataset_path metadata as a string. Internal list() materialization
supports iterator inputs. Per-example filter dropped (Microsoft-OData
coupled, no curated data uses it); filter_default per-run still passes
through to hybrid_search.

The runner is now storage-format-agnostic — boundary filtering of
deprecated entries moves to the CLI in Task 8.

Phase A.7 spec §4.2, §5.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Switch CLI to `iter_active_retrieval_entries`; add FileNotFound UX

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/cli.py`
- Modify: `features/evaluators/chunk_match/tests/test_cli.py`

- [ ] **Step 1: Edit `cli.py`**

Replace the contents of `features/evaluators/chunk_match/src/query_index_eval/cli.py`:

```python
"""query-eval CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv
from goldens import GOLDEN_EVENTS_V1_FILENAME, iter_active_retrieval_entries
from query_index import Config
from query_index.schema_discovery import print_index_schema

from query_index_eval.runner import run_eval

if TYPE_CHECKING:
    from query_index_eval.schema import MetricsReport


DEFAULT_DATASET = Path("outputs") / "datasets" / GOLDEN_EVENTS_V1_FILENAME
DEFAULT_REPORTS_DIR = Path("outputs") / "reports"


def _write_report(
    report: MetricsReport,
    out_dir: Path,
    strategy: str = "unspecified",
) -> Path:  # pragma: no cover
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{timestamp}-{strategy}.json"
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    return out_path


def _print_summary(report: MetricsReport, out_path: Path) -> None:  # pragma: no cover
    a = report.aggregate
    md = report.metadata
    if md.size_status == "indicative":
        banner = "INDICATIVE — n < 30, results NOT statistically reliable"
    elif md.size_status == "preliminary":
        banner = "PRELIMINARY — 30 ≤ n < 100, treat with caution"
    else:
        banner = "REPORTABLE — n ≥ 100"
    print()
    print(f"=== {banner} ===")
    print(f"dataset:      {md.dataset_path}")
    print(f"active:       {md.dataset_size_active}    deprecated: {md.dataset_size_deprecated}")
    print(f"index:        {md.search_index_name}")
    print(f"embedding:    {md.embedding_deployment_name} v{md.embedding_model_version}")
    print(f"timestamp:    {md.run_timestamp_utc}")
    print()
    print(f"Recall@5:     {a.recall_at_5:.3f}")
    print(f"Recall@10:    {a.recall_at_10:.3f}")
    print(f"Recall@20:    {a.recall_at_20:.3f}")
    print(f"MAP:          {a.map_score:.3f}")
    print(f"Hit Rate@1:   {a.hit_rate_at_1:.3f}")
    print(f"MRR:          {a.mrr:.3f}")
    print()
    print(f"report file:  {out_path}")


def _load_env() -> None:
    """Load .env from repo root once. Walk up from this file to find it."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()  # fallback to default search


def _cmd_eval(args: argparse.Namespace) -> int:
    if args.doc is not None:
        dataset_path = Path("outputs") / args.doc / "datasets" / GOLDEN_EVENTS_V1_FILENAME
        out_dir = Path("outputs") / args.doc / "reports"
    else:
        dataset_path = Path(args.dataset)
        out_dir = DEFAULT_REPORTS_DIR

    if not dataset_path.exists():
        print(f"ERROR: events log not found at {dataset_path}", file=sys.stderr)
        return 2

    cfg = Config.from_env()
    entries = iter_active_retrieval_entries(dataset_path)
    report = run_eval(
        entries=entries,
        dataset_path=str(dataset_path),
        top_k_max=args.top,
        cfg=cfg,
    )
    out_path = _write_report(report, out_dir, strategy=args.strategy)
    _print_summary(report, out_path)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:  # pragma: no cover
    a = json.loads(Path(args.compare[0]).read_text())
    b = json.loads(Path(args.compare[1]).read_text())
    a_md = a["metadata"]
    b_md = b["metadata"]
    drift = []
    for key in (
        "embedding_deployment_name",
        "embedding_model_version",
        "azure_openai_api_version",
        "search_index_name",
    ):
        if a_md[key] != b_md[key]:
            drift.append(f"{key}: A={a_md[key]!r}  B={b_md[key]!r}")
    if drift:
        print("WARNING: reports differ in run-defining metadata; comparison may be misleading:")
        for d in drift:
            print(f"  {d}")
        print()
    print(f"{'metric':<14} {'A':>10} {'B':>10} {'B-A':>10}")
    for key in ("recall_at_5", "recall_at_10", "recall_at_20", "map_score", "hit_rate_at_1", "mrr"):
        av = a["aggregate"][key]
        bv = b["aggregate"][key]
        print(f"{key:<14} {av:>10.3f} {bv:>10.3f} {bv - av:>+10.3f}")
    return 0


def _cmd_schema_discovery(args: argparse.Namespace) -> int:  # pragma: no cover
    cfg = Config.from_env()
    print_index_schema(args.index_name or cfg.ai_search_index_name, cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(prog="query-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_eval = sub.add_parser("eval", help="Run evaluation, write report")
    p_eval.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p_eval.add_argument("--top", type=int, default=20)
    p_eval.add_argument(
        "--doc",
        default=None,
        help="Per-doc slug; if given, defaults --dataset and --out under outputs/<slug>/",
    )
    p_eval.add_argument(
        "--strategy",
        default="unspecified",
        help="Chunker strategy name; used in the report filename",
    )
    p_eval.set_defaults(func=_cmd_eval)

    p_report = sub.add_parser("report", help="Compare two metric reports")
    p_report.add_argument("--compare", nargs=2, required=True, metavar=("A", "B"))
    p_report.set_defaults(func=_cmd_report)

    p_schema = sub.add_parser("schema-discovery", help="Print the configured index schema")
    p_schema.add_argument("--index-name", default=None)
    p_schema.set_defaults(func=_cmd_schema_discovery)

    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return int(e.code or 2)
    try:
        return int(args.func(args) or 0)
    except Exception as e:  # pragma: no cover
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Key changes vs. previous:
- Imports `GOLDEN_EVENTS_V1_FILENAME` and `iter_active_retrieval_entries` from `goldens`.
- `DEFAULT_DATASET = Path("outputs") / "datasets" / GOLDEN_EVENTS_V1_FILENAME` (new layout).
- `DEFAULT_REPORTS_DIR = Path("outputs") / "reports"` (Phase-0 leftover fixed).
- `_cmd_eval` builds the dataset path inline, fails hard with exit code 2 if missing, calls `iter_active_retrieval_entries(dataset_path)`, passes entries to `run_eval`.

- [ ] **Step 2: Edit `test_cli.py`**

Overwrite `features/evaluators/chunk_match/tests/test_cli.py`:

```python
"""Tests for the query-eval CLI dispatcher."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    pass


def test_cli_dispatches_eval_with_default_top_k(tmp_path: Path) -> None:
    from query_index_eval.cli import main

    dataset = tmp_path / "events.jsonl"
    dataset.write_text("")  # empty but exists

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        rc = main(["eval", "--dataset", str(dataset)])
    assert rc == 0
    _args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 20


def test_cli_dispatches_eval_passes_top_argument(tmp_path: Path) -> None:
    from query_index_eval.cli import main

    dataset = tmp_path / "events.jsonl"
    dataset.write_text("")

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--dataset", str(dataset), "--top", "10"])
    _args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 10


def test_cli_dispatches_schema_discovery() -> None:
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.print_index_schema") as mock_schema,
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        mock_cfg.ai_search_index_name = "test-idx"
        rc = main(["schema-discovery"])
    assert rc == 0
    mock_schema.assert_called_once()


def test_cli_unknown_subcommand_returns_nonzero() -> None:
    from query_index_eval.cli import main

    rc = main(["unknown-thing"])
    assert rc != 0


def test_cli_eval_with_doc_uses_per_doc_dataset_default(tmp_path: Path, monkeypatch) -> None:
    """query-eval eval --doc foo defaults --dataset to outputs/foo/datasets/golden_events_v1.jsonl."""
    from query_index_eval.cli import main

    monkeypatch.chdir(tmp_path)
    expected = tmp_path / "outputs" / "myslug" / "datasets" / "golden_events_v1.jsonl"
    expected.parent.mkdir(parents=True)
    expected.write_text("")

    captured: dict = {}

    def fake_iter(path):
        captured["path"] = path
        return iter([])

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli.iter_active_retrieval_entries", side_effect=fake_iter),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    assert captured["path"] == Path("outputs") / "myslug" / "datasets" / "golden_events_v1.jsonl"


def test_cli_eval_with_doc_writes_report_to_per_doc_reports_dir(tmp_path: Path, monkeypatch) -> None:
    """query-eval eval --doc foo writes report under outputs/foo/reports/."""
    from query_index_eval.cli import main

    monkeypatch.chdir(tmp_path)
    expected = tmp_path / "outputs" / "myslug" / "datasets" / "golden_events_v1.jsonl"
    expected.parent.mkdir(parents=True)
    expected.write_text("")

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug", "--strategy", "section"])

    args_call, kwargs_call = mock_write.call_args
    out_dir = args_call[1] if len(args_call) > 1 else kwargs_call.get("out_dir")
    strategy = kwargs_call.get("strategy") or (args_call[2] if len(args_call) > 2 else None)
    assert "outputs/myslug/reports" in str(out_dir).replace("\\", "/")
    assert strategy == "section"


def test_cli_eval_strategy_default_is_unspecified(tmp_path: Path, monkeypatch) -> None:
    """When --strategy is not passed, the default is 'unspecified'."""
    from query_index_eval.cli import main

    monkeypatch.chdir(tmp_path)
    expected = tmp_path / "outputs" / "myslug" / "datasets" / "golden_events_v1.jsonl"
    expected.parent.mkdir(parents=True)
    expected.write_text("")

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([])),
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    _, kwargs_call = mock_write.call_args
    args_call = mock_write.call_args.args
    strategy = kwargs_call.get("strategy") or (args_call[2] if len(args_call) > 2 else None)
    assert strategy == "unspecified"


def test_cli_eval_returns_2_when_dataset_missing(tmp_path: Path, capsys) -> None:
    """If the events log file does not exist, the CLI fails hard with
    exit code 2 and a clear stderr message — preventing a silent
    empty-eval that produces zero-aggregate reports."""
    from query_index_eval.cli import main

    absent = tmp_path / "absent.jsonl"
    rc = main(["eval", "--dataset", str(absent)])
    captured = capsys.readouterr()
    assert rc == 2
    assert "events log not found" in captured.err
    assert str(absent) in captured.err


def test_cli_eval_only_passes_active_entries_to_run_eval(
    tmp_path: Path,
    make_entry,
) -> None:
    """The deprecated-filtering happens at the boundary
    (iter_active_retrieval_entries). Even if the events log contains
    deprecated entries, run_eval only ever sees active ones."""
    from query_index_eval.cli import main

    dataset = tmp_path / "events.jsonl"
    dataset.write_text("")

    active = make_entry(query="active query")
    deprecated = make_entry(query="deprecated query", deprecated=True)

    captured_entries: list = []

    def fake_run_eval(*, entries, **_):
        captured_entries.extend(entries)
        from query_index_eval.schema import (
            AggregateMetrics,
            MetricsReport,
            OperationalMetrics,
            RunMetadata,
        )

        return MetricsReport(
            aggregate=AggregateMetrics(0, 0, 0, 0, 0, 0),
            operational=OperationalMetrics(0, 0, 0, 0, 0),
            metadata=RunMetadata(
                "x", 0, 0, "", "", "", "", "2026-04-29T00:00:00Z", "indicative"
            ),
            per_query=[],
        )

    # iter_active_retrieval_entries is the boundary that filters deprecated;
    # we simulate it returning only the active entry.
    with (
        patch("query_index_eval.cli.run_eval", side_effect=fake_run_eval),
        patch("query_index_eval.cli.iter_active_retrieval_entries", return_value=iter([active])),
        patch("query_index_eval.cli._write_report"),
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--dataset", str(dataset)])

    assert len(captured_entries) == 1
    assert captured_entries[0].query == "active query"
```

Key changes vs. previous:
- All `--dataset` based tests now pass an existing tmp file (FileNotFound check would otherwise return 2).
- `iter_active_retrieval_entries` is patched at `query_index_eval.cli` (lookup site).
- New tests: `test_cli_eval_returns_2_when_dataset_missing`; `test_cli_eval_only_passes_active_entries_to_run_eval` (replaces the boundary contract from the dropped `test_run_eval_skips_deprecated_examples`).
- `test_cli_eval_with_doc_*` tests use `monkeypatch.chdir(tmp_path)` because the CLI now resolves a relative path; the events log file is created inside that pwd.

- [ ] **Step 3: Run tests**

```bash
pytest features/evaluators/chunk_match/tests/test_cli.py -v
```

Expected: all 9 tests pass.

```bash
pytest features/evaluators/chunk_match/ -q --tb=short
```

Expected: full suite still green; baseline coverage maintained.

- [ ] **Step 4: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/cli.py \
        features/evaluators/chunk_match/tests/test_cli.py
git commit -m "$(cat <<'EOF'
feat(chunk_match): wire CLI to goldens iter_active_retrieval_entries

DEFAULT_DATASET points at outputs/datasets/golden_events_v1.jsonl;
DEFAULT_REPORTS_DIR cleaned up from Phase-0 leftover. _cmd_eval fails
with exit code 2 when the events log is missing (prevents silent
empty-eval). Boundary filtering of deprecated entries lives in
iter_active_retrieval_entries — runner only ever sees active entries.

Phase A.7 spec §4.3, §5.5.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Delete `datasets.py` and remove `load_dataset` from public surface

**Files:**
- Delete: `features/evaluators/chunk_match/src/query_index_eval/datasets.py`
- Delete: `features/evaluators/chunk_match/tests/test_datasets.py`
- Modify: `features/evaluators/chunk_match/src/query_index_eval/__init__.py`
- Modify: `features/evaluators/chunk_match/tests/test_public_api.py`

- [ ] **Step 1: Delete the production file**

```bash
git rm features/evaluators/chunk_match/src/query_index_eval/datasets.py
```

- [ ] **Step 2: Delete the test file**

```bash
git rm features/evaluators/chunk_match/tests/test_datasets.py
```

- [ ] **Step 3: Edit `__init__.py`**

Edit `features/evaluators/chunk_match/src/query_index_eval/__init__.py`:

```python
"""Public API for the query_index_eval package."""

from query_index_eval.metrics import (
    average_precision,
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
)
from query_index_eval.runner import run_eval
from query_index_eval.schema import (
    AggregateMetrics,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
)

__all__ = [
    "AggregateMetrics",
    "MetricsReport",
    "OperationalMetrics",
    "QueryRecord",
    "RunMetadata",
    "average_precision",
    "hit_rate_at_k",
    "mean_average_precision",
    "mrr",
    "recall_at_k",
    "run_eval",
]
```

- [ ] **Step 4: Edit `test_public_api.py`**

Edit `features/evaluators/chunk_match/tests/test_public_api.py`:

```python
"""Tests for the re-exported public API at query_index_eval.__init__."""

from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index_eval

    expected = {
        "AggregateMetrics",
        "MetricsReport",
        "OperationalMetrics",
        "QueryRecord",
        "RunMetadata",
        "average_precision",
        "hit_rate_at_k",
        "mean_average_precision",
        "mrr",
        "recall_at_k",
        "run_eval",
    }
    missing = expected - set(dir(query_index_eval))
    assert not missing, f"Missing public exports: {missing}"


def test_public_api_does_not_re_export_load_dataset() -> None:
    """Catches accidental re-introduction of the old EvalExample-JSONL surface."""
    import query_index_eval

    assert "load_dataset" not in dir(query_index_eval)
```

(EvalExample is still in the namespace at this point because Task 10 hasn't deleted it yet — the negative assertion for EvalExample is added in Task 10.)

- [ ] **Step 5: Run tests**

```bash
pytest features/evaluators/chunk_match/ -q --tb=short
```

Expected: full suite green; coverage stays ≥ 95.52 %.

- [ ] **Step 6: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/datasets.py \
        features/evaluators/chunk_match/tests/test_datasets.py \
        features/evaluators/chunk_match/src/query_index_eval/__init__.py \
        features/evaluators/chunk_match/tests/test_public_api.py
git commit -m "$(cat <<'EOF'
chore(chunk_match): delete datasets.py and load_dataset re-export

datasets.py held load_dataset / append_example / deprecate_example /
DatasetMutationError — all dead code after the runner switched to
goldens.iter_active_retrieval_entries in Tasks 7 and 8. Phase 0 had
already deleted the only production caller (curate.py); A.6 introduces
its own goldens-side error hierarchy so DatasetMutationError has no
structural place to migrate to.

Phase A.7 spec §4.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Delete `EvalExample` from `schema.py` and clean up tests/conftest

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/schema.py`
- Modify: `features/evaluators/chunk_match/tests/test_schema.py`
- Modify: `features/evaluators/chunk_match/tests/conftest.py`
- Modify: `features/evaluators/chunk_match/tests/test_public_api.py`

- [ ] **Step 1: Remove `EvalExample` from `schema.py`**

Overwrite `features/evaluators/chunk_match/src/query_index_eval/schema.py`:

```python
"""Frozen dataclasses for the eval pipeline.

Designed so that `dataclasses.asdict` produces a JSON-serialisable structure.
The metric/report dataclasses compose into a single MetricsReport that the CLI
serialises to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AggregateMetrics:
    recall_at_5: float
    recall_at_10: float
    recall_at_20: float
    map_score: float
    hit_rate_at_1: float
    mrr: float


@dataclass(frozen=True)
class OperationalMetrics:
    mean_latency_ms: float
    p95_latency_ms: float
    total_queries: int
    total_embedding_calls: int
    failure_count: int


@dataclass(frozen=True)
class RunMetadata:
    dataset_path: str
    dataset_size_active: int
    dataset_size_deprecated: int
    embedding_deployment_name: str
    embedding_model_version: str
    azure_openai_api_version: str
    search_index_name: str
    run_timestamp_utc: str
    size_status: str
    drifted_entry_ids: list[str] = field(default_factory=list)
    drift_warning: bool = False


@dataclass(frozen=True)
class QueryRecord:
    entry_id: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    ranks: list[int]
    hits: list[bool]
    latency_ms: float


@dataclass(frozen=True)
class MetricsReport:
    aggregate: AggregateMetrics
    operational: OperationalMetrics
    metadata: RunMetadata
    per_query: list[QueryRecord] = field(default_factory=list)
```

- [ ] **Step 2: Remove `EvalExample` tests from `test_schema.py`**

Overwrite `features/evaluators/chunk_match/tests/test_schema.py`:

```python
"""Tests for query_index_eval.schema dataclasses."""

from __future__ import annotations


def test_aggregate_metrics_holds_all_metric_fields() -> None:
    from query_index_eval.schema import AggregateMetrics

    m = AggregateMetrics(
        recall_at_5=0.7,
        recall_at_10=0.85,
        recall_at_20=0.95,
        map_score=0.65,
        hit_rate_at_1=0.8,
        mrr=0.72,
    )
    assert m.recall_at_10 == 0.85
    assert m.mrr == 0.72


def test_operational_metrics_holds_counts_and_latency() -> None:
    from query_index_eval.schema import OperationalMetrics

    m = OperationalMetrics(
        mean_latency_ms=120.0,
        p95_latency_ms=350.0,
        total_queries=42,
        total_embedding_calls=42,
        failure_count=1,
    )
    assert m.total_queries == 42


def test_query_record_holds_per_query_data() -> None:
    from query_index_eval.schema import QueryRecord

    r = QueryRecord(
        entry_id="g0001",
        expected_chunk_ids=["c42"],
        retrieved_chunk_ids=["c10", "c42", "c7"],
        ranks=[2],
        hits=[True],
        latency_ms=110.0,
    )
    assert r.ranks == [2]
    assert r.hits == [True]
    assert r.entry_id == "g0001"


def test_run_metadata_includes_embedding_and_size_status() -> None:
    from query_index_eval.schema import RunMetadata

    md = RunMetadata(
        dataset_path="outputs/test/datasets/golden_events_v1.jsonl",
        dataset_size_active=42,
        dataset_size_deprecated=3,
        embedding_deployment_name="text-embedding-3-large",
        embedding_model_version="1",
        azure_openai_api_version="2024-02-01",
        search_index_name="wizard-1",
        run_timestamp_utc="2026-04-27T10:00:00Z",
        size_status="preliminary",
    )
    assert md.size_status == "preliminary"
    assert md.drifted_entry_ids == []


def test_metrics_report_composes_all_subobjects() -> None:
    from query_index_eval.schema import (
        AggregateMetrics,
        MetricsReport,
        OperationalMetrics,
        QueryRecord,
        RunMetadata,
    )

    aggregate = AggregateMetrics(0.7, 0.85, 0.95, 0.65, 0.8, 0.72)
    operational = OperationalMetrics(120.0, 350.0, 42, 42, 1)
    metadata = RunMetadata(
        "outputs/test/datasets/golden_events_v1.jsonl",
        42,
        3,
        "text-embedding-3-large",
        "1",
        "2024-02-01",
        "wizard-1",
        "2026-04-27T10:00:00Z",
        "preliminary",
    )
    record = QueryRecord("g0001", ["c42"], ["c42"], [1], [True], 110.0)
    report = MetricsReport(
        aggregate=aggregate,
        operational=operational,
        metadata=metadata,
        per_query=[record],
    )
    assert report.aggregate is aggregate
    assert len(report.per_query) == 1
```

- [ ] **Step 3: Drop unused fixtures from `conftest.py`**

Edit `features/evaluators/chunk_match/tests/conftest.py`:

```python
"""Shared fixtures for query_index_eval tests.

The `query_index` package is patched at module level so that no test in this
suite ever touches Azure. Fixtures expose: a make_entry factory for
RetrievalEntry construction.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from goldens import RetrievalEntry, new_entry_id


@pytest.fixture(autouse=True)
def _patch_get_chunk():
    """Prevent any test from calling the real get_chunk (which hits Azure).

    Tests that need specific get_chunk behaviour override this by adding their
    own ``patch("query_index_eval.runner.get_chunk", ...)`` context manager,
    which takes precedence over this autouse patch.
    """
    with patch("query_index_eval.runner.get_chunk", return_value=MagicMock(chunk="")):
        yield


@pytest.fixture
def make_entry():
    """Factory for RetrievalEntry test instances. review_chain=() yields
    level='synthetic' (legal — see schemas.retrieval._highest_level)."""
    def _make(
        entry_id: str | None = None,
        query: str = "Q?",
        expected: tuple[str, ...] = ("c1",),
        chunk_hashes: dict[str, str] | None = None,
        deprecated: bool = False,
    ) -> RetrievalEntry:
        return RetrievalEntry(
            entry_id=entry_id or new_entry_id(),
            query=query,
            expected_chunk_ids=expected,
            chunk_hashes=chunk_hashes or {c: f"sha256:{c}" for c in expected},
            review_chain=(),
            deprecated=deprecated,
        )
    return _make
```

(Removes `tmp_dataset_path`, `sample_example_dict` fixtures plus the now-unused `Path` and `TYPE_CHECKING` imports.)

- [ ] **Step 4: Add the negative assertion for `EvalExample` in `test_public_api.py`**

Edit `features/evaluators/chunk_match/tests/test_public_api.py`:

```python
"""Tests for the re-exported public API at query_index_eval.__init__."""

from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index_eval

    expected = {
        "AggregateMetrics",
        "MetricsReport",
        "OperationalMetrics",
        "QueryRecord",
        "RunMetadata",
        "average_precision",
        "hit_rate_at_k",
        "mean_average_precision",
        "mrr",
        "recall_at_k",
        "run_eval",
    }
    missing = expected - set(dir(query_index_eval))
    assert not missing, f"Missing public exports: {missing}"


def test_public_api_does_not_re_export_load_dataset() -> None:
    """Catches accidental re-introduction of the old EvalExample-JSONL surface."""
    import query_index_eval

    assert "load_dataset" not in dir(query_index_eval)


def test_public_api_does_not_re_export_eval_example() -> None:
    """Catches accidental re-introduction of the deleted EvalExample dataclass."""
    import query_index_eval

    assert "EvalExample" not in dir(query_index_eval)
```

- [ ] **Step 5: Run tests**

```bash
pytest features/evaluators/chunk_match/ -q --tb=short
```

Expected: full suite green; coverage stays ≥ 95.52 %.

- [ ] **Step 6: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/schema.py \
        features/evaluators/chunk_match/tests/test_schema.py \
        features/evaluators/chunk_match/tests/conftest.py \
        features/evaluators/chunk_match/tests/test_public_api.py
git commit -m "$(cat <<'EOF'
chore(chunk_match): delete EvalExample dataclass and dead fixtures

Removes EvalExample from schema.py (and three corresponding tests) plus
tmp_dataset_path / sample_example_dict fixtures from conftest.py. Adds
a negative public-API assertion to catch accidental re-introduction.

The schema module now holds only metric / report dataclasses. All
dataset-shape concerns live in goldens.

Phase A.7 spec §4.4, §5.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Update `chunk_match/README.md`

**Files:**
- Modify: `features/evaluators/chunk_match/README.md`

- [ ] **Step 1: Edit README.md**

Overwrite `features/evaluators/chunk_match/README.md`:

```markdown
# query-index-eval

Retrieval-quality evaluation pipeline for the `query-index` search library.
Consumes `RetrievalEntry` projections from `goldens/storage/`.

## Public API

```python
from query_index_eval import (
    AggregateMetrics,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
    average_precision,
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
    run_eval,
)

# Goldens are loaded from the event-sourced store:
from goldens import iter_active_retrieval_entries

entries = iter_active_retrieval_entries(Path("outputs/<doc>/datasets/golden_events_v1.jsonl"))
report = run_eval(entries=entries, dataset_path=str(path))
```

## CLI

```bash
query-eval eval --top 20                 # run evaluation, write report
query-eval eval --doc <doc-slug>         # uses outputs/<slug>/datasets/golden_events_v1.jsonl
query-eval report --compare A.json B.json
query-eval schema-discovery              # dump current index schema
```

## Datasets

Golden retrieval entries live in `outputs/<doc-slug>/datasets/golden_events_v1.jsonl`
as an append-only event log written by `goldens` curation tools (Phase A.4 +).
This package is a read-only consumer of that log.

## Reports

Produced under `outputs/<doc-slug>/reports/<utc-timestamp>-<strategy>.json`
(or `outputs/reports/...` if `--doc` is not given). Gitignored.

## Tests

```bash
pytest features/evaluators/chunk_match/
```

All tests are mocked — `query_index` calls are patched at the import boundary;
`goldens` data is constructed in-memory via the `make_entry` fixture.
```

- [ ] **Step 2: Verify**

No tests for README. Visual sanity check:

```bash
cat features/evaluators/chunk_match/README.md
```

Expected: no remaining `EvalExample` / `load_dataset` / `golden_v1.jsonl` references.

```bash
grep -E "EvalExample|load_dataset|golden_v1\.jsonl" features/evaluators/chunk_match/README.md && echo "STALE" || echo "clean"
```

Expected: `clean`.

- [ ] **Step 3: Commit**

```bash
git add features/evaluators/chunk_match/README.md
git commit -m "$(cat <<'EOF'
docs(chunk_match): update README for goldens-backed read path

Reflects the new public API (no EvalExample / load_dataset), the
event-log dataset path (golden_events_v1.jsonl under outputs/<slug>/),
and the read-only-consumer relationship to goldens.

Phase A.7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Final coverage verification

**Files:** none (verification task)

- [ ] **Step 1: Run goldens suite**

```bash
pytest features/goldens/ -q --tb=no 2>&1 | tail -10
```

Expected: all tests pass, coverage = **100 %** (per `--cov-fail-under=100`).

- [ ] **Step 2: Run chunk_match suite**

```bash
pytest features/evaluators/chunk_match/ -q --tb=no 2>&1 | tail -10
```

Expected: all tests pass, coverage **≥ 95.52 %** (pre-A.7 baseline) and ≥ 90 % (CI floor). If below baseline, investigate which line(s) lost coverage and either add a test or document the regression.

- [ ] **Step 3: Run the entire suite**

```bash
pytest features/ -q --tb=no 2>&1 | tail -10
```

Expected: all tests across all features pass.

- [ ] **Step 4: Lint & type check**

```bash
ruff check features/evaluators/chunk_match/ features/goldens/
ruff format --check features/evaluators/chunk_match/ features/goldens/
mypy features/evaluators/chunk_match/ features/goldens/
```

Expected: clean output.

- [ ] **Step 5: Smoke-check the CLI argparse default**

```bash
python -c "from query_index_eval.cli import DEFAULT_DATASET, DEFAULT_REPORTS_DIR; print(DEFAULT_DATASET); print(DEFAULT_REPORTS_DIR)"
```

Expected:
```
outputs/datasets/golden_events_v1.jsonl
outputs/reports
```

No commit; this is a verification gate before opening the PR.

---

## PR Body Template

After Task 12, before opening the PR, draft the body. Pull from spec §6.4 (Decision log) and §6.5 (Success criteria):

```markdown
## Phase A.7 — `evaluators/chunk_match/` rewire onto `goldens/storage/`

Switches the evaluator from the old `EvalExample`-JSONL to the
event-sourced golden-set storage built in A.3. ~80 % of the diff is
deletions; reviewers should mentally start with the deletion block.

### Changes

- New: `goldens.iter_active_retrieval_entries(path)` — canonical evaluator read path.
- New: `goldens.GOLDEN_EVENTS_V1_FILENAME` — storage-contract filename constant.
- Reshaped: `run_eval(entries: Iterable[RetrievalEntry], *, dataset_path: str, ...)` — entries-based, keyword-only metadata.
- Renamed: `QueryRecord.query_id → entry_id`; `RunMetadata.drifted_query_ids → drifted_entry_ids`.
- Removed: per-example `filter` field (Microsoft-OData-coupled, pipeline-specific).
- Removed: `EvalExample`, `load_dataset`, `datasets.py`, `DatasetMutationError`, the `query-eval` re-exports thereof.
- New CLI behavior: exit code 2 with stderr message when the events log is missing.
- New CLI defaults: `outputs/datasets/golden_events_v1.jsonl` (no-`--doc`), `outputs/<slug>/datasets/golden_events_v1.jsonl` (with `--doc`).

### Coordination with A.6

Both branches modify `goldens/__init__.py` and `goldens/storage/__init__.py`.
The expected merge conflict is mechanical (both extend the same `__all__`);
resolution is to keep both additions. Whoever merges second rebases on main.

### Decision log

- Convenience reader lives in `goldens` (canonical composition, not speculative).
- `filter` field dropped (pipeline-agnosticism over OData-coupling).
- Full `query_id → entry_id` rename (no pre-A.7 data/reports break).
- Filename constant in `goldens/storage/`, repo layout in caller.
- Full deletion of `EvalExample`/`datasets.py` (Phase-0 rule "delete when no real data").
- `run_eval` entries-based (test clarity, layer separation).
- Future: `_v2` schema bump introduces `GOLDEN_EVENTS_V2_FILENAME` + migration script.
- Future: per-example pipeline-agnostic filtering would be additive `scope: dict | None`.

### Test plan

- [x] `pytest features/goldens/` green, 100 % coverage
- [x] `pytest features/evaluators/chunk_match/` green, coverage ≥ baseline (95.52 %)
- [x] `query-eval eval --doc <slug>` produces report with UUID4 hex `entry_id` (`^[0-9a-f]{32}$`)
- [x] `query-eval eval` without events log → exit code 2 + clear stderr message
- [x] ruff / mypy / pre-commit hooks clean
```

---

## Self-Review Checklist

Run these checks against the spec one final time before declaring the plan complete.

| Spec section | Plan task |
|---|---|
| §4.1 — `iter_active_retrieval_entries`, `GOLDEN_EVENTS_V1_FILENAME` | Tasks 1, 2 |
| §4.2 — `run_eval` signature, `query_id → entry_id`, drift rename, `filter` drop | Tasks 5, 6, 7 |
| §4.3 — CLI `iter_active_retrieval_entries`, defaults, FileNotFound, argparse default | Task 8 |
| §4.4 — Removed symbols (EvalExample, load_dataset, datasets.py, DatasetMutationError) | Tasks 9, 10 |
| §5.1 — Coverage floors | Tasks 3, 12 |
| §5.2 — Goldens tests (5 new) | Tasks 1, 2 |
| §5.3 — chunk_match deletions, rewrites, public-api updates | Tasks 7, 8, 9, 10 |
| §5.4 — `make_entry` fixture | Task 4 |
| §5.5 — FileNotFound UX | Task 8 |
| §6.4 — Decision log | PR body template |
| §6.5 — Success criteria | Task 12 |

All spec sections are covered. No placeholders, no "TBD"s, no "similar to Task N" references — every step contains the actual code and commands the engineer needs.
