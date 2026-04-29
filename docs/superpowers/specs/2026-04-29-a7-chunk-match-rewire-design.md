# Phase A.7 — `evaluators/chunk_match/` Rewire onto `goldens/storage/` Design Spec

**Status:** Draft for review
**Date:** 2026-04-29
**Branch:** `feat/a7-chunk-match`
**Parent specs:**
- `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§3 Architecture, §7 Phase A.7)
- `docs/superpowers/specs/2026-04-29-a3-goldens-storage-design.md` (storage layer this PR consumes)

---

## 1. Scope

A.7 wires the existing `evaluators/chunk_match/` runner against the new
event-sourced golden-set storage built in A.3. Today the runner reads
`EvalExample` rows from a per-row JSONL via `query_index_eval.datasets.load_dataset`.
After A.7 it consumes `RetrievalEntry` projections from
`goldens/storage/`. The old `EvalExample` / `load_dataset` surface is
deleted in the same PR, since no external caller depends on it.

A.7 is the read-only consumer of the event log. Writers of the log
(`A.4 curate`, `A.6 operations`) are out of scope here.

## 2. Goals & Non-Goals

### Goals

- Replace `EvalExample`-backed dataset loading with the canonical
  `read_events → build_state → active_entries` projection from `goldens/storage/`.
- Introduce one named convenience reader in `goldens` for the
  default evaluator read path, plus the filename constant tying the
  events log to its schema version.
- Reshape `run_eval` to take an `Iterable[RetrievalEntry]` instead of a
  `Path`, so tests construct entries directly and the runner has no
  storage-format awareness.
- Rename `query_id` → `entry_id` across `QueryRecord` / `RunMetadata`
  to align report vocabulary with the new model.
- Drop the per-example `filter` field (Microsoft-OData-coupled, no
  curated data uses it). Per-run filtering via `run_eval(filter_default=...)` stays.
- Delete dead old-shape symbols (`EvalExample`, `load_dataset`, `datasets.py`,
  matching tests) in the same PR.
- Hold `goldens` coverage at **100 %** and `chunk_match` coverage at **≥ 90 %**
  (and not below the pre-A.7 baseline).

### Non-Goals

- No schema extension in `goldens` (no `filter`, no `scope` field). Future
  per-example pipeline-agnostic filtering would be additive (`scope: dict | None = None`,
  pipelines translate to their own syntax) — explicitly deferred.
- No re-introduction of the `query-eval curate` CLI. Phase 0 deleted it; A.4 builds it
  on the event log. A.7 is purely the read-side rewire.
- No migration of pre-A.7 reports. None exist in real datasets; the
  `--compare` subcommand operates on aggregate-level keys, which stay shape-stable.
- No directory creation for the events log. `outputs/<slug>/datasets/` must
  exist (created by A.4-curate or A.6-operations); if absent, reading falls
  through the FileNotFound UX. The report directory `outputs/<slug>/reports/`
  is still created on demand by `_write_report` — unchanged existing logic.
- No `goldens.api/` (FastAPI) — Phase A.5.
- No performance work. Projection over the full log is O(N), fast enough until
  N > 100k (per A.3-spec §7).

## 3. Architecture & Data Flow

### 3.1 Before vs. after

```
Before (today):
JSONL[EvalExample] ── load_dataset(path) ──► list[EvalExample] ──► run_eval ──► MetricsReport

After (A.7):
JSONL[Event] ── read_events ──► list[Event] ──► build_state ──► dict[entry_id, RetrievalEntry]
                                                                        │
                                                                        ▼
                                                              active_entries ──► Iterator[RetrievalEntry]
                                                                        │
       (all of the above wrapped as iter_active_retrieval_entries(path))
                                                                        │
                                                                        ▼
                                              run_eval(entries, dataset_path, ...)
                                                                        │
                                                                        ▼
                                                                 MetricsReport
```

### 3.2 Layer responsibilities

| Layer | Responsible for | Knows | Doesn't know |
|---|---|---|---|
| `goldens/storage` | event log + projection | storage format, locking, filename contract (`_v1`) | repo directory layout, pipelines, evaluators |
| `chunk_match.runner` | eval orchestration over entries | `RetrievalEntry`, `hybrid_search`, metrics | storage format, disk I/O |
| `chunk_match.cli` | glue: path → entries → runner | repo layout (`outputs/<slug>/datasets/`) | eval logic |

**Import direction:** `chunk_match.cli` → `chunk_match.runner` → `goldens` (schemas + storage). No back-edges.

**Read-only consumer:** A.7 reads from the event-log file but does not
write to it. Code in `goldens/` and `chunk_match/` is added/modified;
the event-log file itself is only read here. Writers of the log are A.4
(curate) and A.6 (operations) — see their specs for the write side.

## 4. API Surfaces

### 4.1 New in `goldens`

**Source-of-truth: `goldens/storage/__init__.py`** (filename = storage
contract, lives with the storage layer). Re-export from
`goldens/__init__.py` for top-level convenience.

```python
# goldens/storage/__init__.py — source of truth
GOLDEN_EVENTS_V1_FILENAME = "golden_events_v1.jsonl"

__all__ = [
    "GOLDEN_EVENTS_V1_FILENAME",
    "active_entries", "append_event", "build_state",
    "iter_active_retrieval_entries",
    "new_entry_id", "new_event_id", "read_events",
]
```

```python
# goldens/__init__.py — re-export (and __all__ update)
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, iter_active_retrieval_entries

__all__ = [
    # ... existing exports ...
    "GOLDEN_EVENTS_V1_FILENAME",
    "iter_active_retrieval_entries",
]
```

```python
# goldens/storage/projection.py — new function
def iter_active_retrieval_entries(path: Path) -> Iterator[RetrievalEntry]:
    """Canonical read path for evaluators: read events from `path`,
    project to state, yield active (non-deprecated) entries.

    Drop to read_events / build_state / active_entries if you need
    deprecated entries, the full state dict, or non-retrieval task types.
    """
    return active_entries(build_state(read_events(path)))
```

### 4.2 Modified in `chunk_match`

**`run_eval` signature** (entries-based, internal materialization,
keyword-only metadata):

```python
# query_index_eval/runner.py
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
    ...
```

The keyword-only marker (`*,`) prevents callers from passing
`dataset_path` positionally — it is metadata, not a data source.
The `hybrid_search` call drops `example.filter or filter_default`
in favor of plain `filter=filter_default`.

**Schema renames** (`query_index_eval/schema.py`):

```python
@dataclass(frozen=True)
class QueryRecord:
    entry_id: str           # ← was: query_id
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    ranks: list[int]
    hits: list[bool]
    latency_ms: float

@dataclass(frozen=True)
class RunMetadata:
    ...
    drifted_entry_ids: list[str] = ...   # ← was: drifted_query_ids
    drift_warning: bool = False
```

The `EvalExample` dataclass is removed from `schema.py`. Remaining
contents: `AggregateMetrics`, `OperationalMetrics`, `RunMetadata`,
`QueryRecord`, `MetricsReport`.

### 4.3 CLI (`query_index_eval/cli.py`)

```python
from goldens import GOLDEN_EVENTS_V1_FILENAME, iter_active_retrieval_entries

DEFAULT_DATASET = Path("outputs") / "datasets" / GOLDEN_EVENTS_V1_FILENAME

def _cmd_eval(args: argparse.Namespace) -> int:
    if args.doc is not None:
        dataset_path = Path("outputs") / args.doc / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    else:
        dataset_path = Path(args.dataset)

    if not dataset_path.exists():
        print(f"ERROR: events log not found at {dataset_path}", file=sys.stderr)
        return 2

    out_dir = (
        Path(f"outputs/{args.doc}/reports") if args.doc is not None
        else DEFAULT_REPORTS_DIR
    )
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
```

Inlined path composition — no `_events_path_for_doc` helper (single
caller, inlining is cleaner). The argparse default string changes from
the old `features/query-index-eval/datasets/golden_v1.jsonl` to
`outputs/datasets/golden_events_v1.jsonl`:

```python
p_eval.add_argument("--dataset", default=str(DEFAULT_DATASET))  # default reflects new path
```

**Parallel cleanup:** `DEFAULT_REPORTS_DIR` (currently
`Path("features/query-index-eval/reports")`) is a Phase-0 leftover
pointing at a directory that no longer exists. Updated in the same PR to
`Path("outputs/reports")` so the no-`--doc` default is consistent with
the new layout. No functional change for `--doc <slug>` callers (their
out_dir is composed inline as today).

### 4.4 Removed from `chunk_match`

| Symbol | File |
|---|---|
| `EvalExample` (dataclass) | `schema.py` (kept: metric dataclasses) |
| `load_dataset`, `append_example`, `deprecate_example`, `DatasetMutationError` | `datasets.py` (file deleted) |
| `EvalExample`, `load_dataset` from re-exports | `__init__.py` |

`DatasetMutationError` was only used by `curate.py` (deleted in Phase 0),
by `append_example`/`deprecate_example` themselves (deleted with `datasets.py`),
and by `tests/test_datasets.py` (deleted in this PR). No production caller
survives. A.6 (operations) introduces its own goldens-side error hierarchy
(`EntryNotFoundError`, `EntryDeprecatedError`); the old type has no
structural place there.

### 4.5 Behavior diff after A.7

- Pre-A.7 reports vs. post-A.7 reports are not formally comparable per-record
  (`query_id` vs. `entry_id` field name; UUID4-hex vs. `g0001` content). The
  `--compare` subcommand operates on aggregate-level keys and stays shape-stable.
  No real curated reports exist that would break.
- CLI default path changes; old default did not exist in real data either.

## 5. Test Plan & Coverage

### 5.1 Coverage floors (binding)

| Package | Floor (`pyproject.toml`) | After A.7 |
|---|---|---|
| `goldens` | `--cov-fail-under=100` (branch) | stays **100 %** |
| `chunk_match` | `--cov-fail-under=90` | stays **≥ 90 %** and ≥ pre-A.7 baseline |

Pre-A.7 coverage baseline for `chunk_match` is measured before the
first implementation commit and recorded in the implementation plan.
Post-A.7 must not regress without justification.

### 5.2 Tests in `goldens` (new)

| Test | File | Asserts |
|---|---|---|
| `test_iter_active_retrieval_entries_returns_only_active` | `tests/test_storage_projection.py` | 1 active + 1 deprecated entry via `append_event` → materializing the iterator yields exactly the active entry with the correct `entry_id` and `query`. |
| `test_iter_active_retrieval_entries_empty_when_file_missing` | `tests/test_storage_projection.py` | Path doesn't exist → empty iterator (tolerant `read_events` semantics unchanged). |
| `test_golden_events_v1_filename_is_storage_contract` | `tests/test_storage_projection.py` | `assert GOLDEN_EVENTS_V1_FILENAME == "golden_events_v1.jsonl"` (documents contract). |
| `test_iter_active_retrieval_entries_re_exported_from_goldens_top_level` | `tests/test_storage_projection.py` | `from goldens import iter_active_retrieval_entries` succeeds. |
| `test_filename_constant_re_exported_from_goldens_top_level` | `tests/test_storage_projection.py` | `from goldens import GOLDEN_EVENTS_V1_FILENAME` succeeds and matches the storage-level value. |

The five tests cover the three glue lines and the constant, plus the
re-export edges that catch the most common refactor bug (symbol
silently dropped from `__init__.py`).

### 5.3 Tests in `chunk_match`

**Deleted in full:**

- `tests/test_datasets.py` (8 tests; targets removed `datasets.py`)
- Three `test_eval_example_*` tests from `tests/test_schema.py` (class removed)
- `test_run_eval_passes_filter_per_example_when_set` from `tests/test_runner.py` (feature removed)

**Rewritten** (table summarizes intent — actual diff produced during implementation):

| Test (before) | After |
|---|---|
| `test_run_eval_skips_deprecated_examples` | Replaced by a CLI-level test in `test_cli.py` that verifies the deprecated-filtering happens at the boundary (`iter_active_retrieval_entries`) — runner only ever sees active entries. The runner-level test is dropped because the contract no longer exists at that layer. |
| `test_run_eval_records_ranks_and_hits_per_query` | Builds entries via `make_entry()` fixture, passes them to `run_eval(entries=..., dataset_path="test")`. |
| `test_run_eval_records_minus_one_rank_when_expected_not_found` | dito |
| `test_run_eval_aggregates_metrics_across_queries` | dito |
| `test_run_eval_assigns_size_status_*` (3 tests) | dito; entry lists of varying length |
| `test_run_eval_metadata_includes_embedding_and_index_info` | dito; also asserts `dataset_path == "test"` (metadata pass-through) |
| `test_run_eval_detects_hash_drift_*` (2 tests) | Entries carry `chunk_hashes` directly; no JSONL setup. |

**`test_cli.py` updates:**

- `test_cli_eval_with_doc_uses_per_doc_dataset_default` — asserts `outputs/<slug>/datasets/golden_events_v1.jsonl`.
- `test_cli_eval_with_doc_writes_report_to_per_doc_reports_dir` — structurally unchanged.
- New: `test_cli_eval_returns_nonzero_when_dataset_missing` — `main(["eval", "--dataset", str(tmp_path / "absent.jsonl")])` without file → return code = 2; stderr mentions the path.
- Mock-Patch path: `query_index_eval.cli.iter_active_retrieval_entries` (Python mock convention: patch where the symbol is *looked up*, not where defined; see imports in §4.3).

**`test_public_api.py` updates:** `EvalExample`/`load_dataset` removed
from expected set. Add a negative assertion (`assert "EvalExample" not in dir(query_index_eval)`)
to catch accidental re-export regression.

**`tests/conftest.py` updates:** drop the `sample_example_dict` and
`tmp_dataset_path` fixtures (no longer used). Keep the autouse
`_patch_get_chunk` patch.

### 5.4 New test helper (`chunk_match/tests/conftest.py`)

```python
@pytest.fixture
def make_entry():
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

`review_chain=()` is legal: `RetrievalEntry.level` returns `"synthetic"`
for an empty review chain (see `_highest_level` in `schemas/retrieval.py`);
`__post_init__` validates only `entry_id` and `query` non-empty.

### 5.5 FileNotFound UX

In `cli._cmd_eval`, immediately after path construction:

```python
if not dataset_path.exists():
    print(f"ERROR: events log not found at {dataset_path}", file=sys.stderr)
    return 2
```

`read_events` returns `[]` for a missing file (tolerant — correct for
the storage layer and for a future curate-CLI starting on an empty repo).
A silent empty eval would be confusing: 0 queries, zero aggregates, no
clear error. The CLI closes the UX gap with a hard fail and exit code 2.

## 6. Out-of-Scope, PR Strategy, Risks, Decision Log

### 6.1 Out-of-Scope

See §2. Notable explicit non-goals: no schema extension; no curate CLI;
no report migration; no events-log directory creation; no FastAPI; no
performance work.

### 6.2 PR strategy

- **One PR.** All changes hang on the data-source switch (`EvalExample`-JSONL → event log).
  Splitting forces artificial intermediate states with dead code paths next to live ones.
- **Branch:** `feat/a7-chunk-match` (current working branch).
- **Reviewer hint in PR body:** ~80 % of the diff is deletions. Mentally
  start with the deletion block, then read the four-file touch block
  (`runner.py`, `cli.py`, `schema.py`, plus tests).
- **Coordination with A.6:** both branches modify `goldens/__init__.py`
  and `goldens/storage/__init__.py`. The expected merge conflict is
  mechanical (both extend the same `__all__`); resolution is to keep both
  additions. Whoever merges second rebases on main and picks the union.

### 6.3 Risks & mitigation

| Risk | Mitigation |
|---|---|
| Coverage regression in `chunk_match` from test rewrite | Measure baseline before the first implementation commit; re-measure after; CI floor at ≥ 90 %. |
| `goldens` 100 % floor breaks because of `iter_active_retrieval_entries` | Three dedicated tests (round-trip, empty file, filename constant) cover the 3-line glue. |
| Symbol accidentally removed from `__init__.py` | Positive re-export assertions in `test_storage_projection.py`; negative assertion in `chunk_match.test_public_api.py`. |
| Mock patch path wrong in CLI tests | Patch `query_index_eval.cli.iter_active_retrieval_entries` (lookup site), not `goldens.iter_active_retrieval_entries` (definition site). |
| Silent empty run when events log absent | `_cmd_eval` FileNotFound check + exit code 2 + dedicated test (§5.5). |

### 6.4 Decision log (for PR body / posterity)

| Decision | Rationale (short) | Source |
|---|---|---|
| Convenience reader `iter_active_retrieval_entries` lives in `goldens` | Composition is canonical, not speculative; every evaluator needs it | Q1 |
| `filter` field dropped | Pipeline agnosticism (OData ≠ pipeline-neutral); no real use case | Q2 |
| Full `query_id` → `entry_id` rename | No pre-A.7 data/reports would break | Q3 |
| Filename constant in `goldens/storage/__init__.py`, repo layout in caller | Filename = storage contract, layout = repo convention | Q4 |
| Full deletion cut (`EvalExample`/`datasets.py`) | Phase-0 rule "delete when no real data" applies 1:1 | Q5 |
| `run_eval` entries-based | Test clarity, clean layer separation, future-trivial | Q6 |
| **Future _v2 migration:** schema bump introduces `GOLDEN_EVENTS_V2_FILENAME`; migration script v1→v2 with defaults for new fields | Documented for posterity | Q4 |
| **Future `scope` field:** if per-example filtering becomes a real need, add additively as `scope: dict | None = None` (pipelines translate to their own syntax) | Prevents OData-coupling re-entry | Q2 |

### 6.5 Success criteria

A.7 is done when all four hold:

1. `pytest features/goldens/` → green, coverage = 100 %.
2. `pytest features/evaluators/chunk_match/` → green, coverage ≥ 90 % and not below pre-A.7 baseline.
3. `query-eval eval --doc <slug>` (with an existing event log) produces a
   `MetricsReport` whose `per_query[*].entry_id` is a UUID4 hex value
   (form: `^[0-9a-f]{32}$`, not the old `g0001` schema).
4. `query-eval eval` without an events log → exit code 2 with a clear stderr message.
