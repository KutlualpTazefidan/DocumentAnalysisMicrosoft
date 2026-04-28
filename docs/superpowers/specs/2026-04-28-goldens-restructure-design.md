# Goldens Restructure — Design Spec

**Status:** Draft for review
**Date:** 2026-04-28
**Author:** ktazefid (with Claude as collaborator)
**Supersedes:** parts of `2026-04-27-query-index-evaluation-design.md`
(specifically the dataset-curation flow and `EvalExample` schema)

---

## 1. Motivation

Today the repository has three feature packages — `query-index`,
`query-index-eval`, `ingestion` — each shaped around a single concern.
The eval package can curate one type of golden example (`EvalExample`,
a retrieval task) and run one type of metric (chunk-id matching).

We need to grow in three orthogonal directions, and the current shape will
not absorb that growth cleanly:

1. **More golden-set types.** Today only retrieval. Soon: answer-quality
   (judge-style ratings on free-text answers) and classification
   (single-label / multi-label tags on chunks).
2. **More pipelines.** Today only the Microsoft Azure Search pipeline.
   Soon: a custom self-hosted pipeline. Both must be evaluated against
   the same goldens.
3. **More evaluators.** Today only `chunk_match`. Soon: `llm_judge`
   (single-LLM judge) and `multi_agent` (multiple LLM judges with
   aggregation).

A second pressure: **provenance and trust**. The current `EvalExample`
records only `source: "curated"` and a single `created_at` timestamp.
For Microsoft collaboration we need to record **who** signed off on each
golden, **with what authority**, and **in what order** — so that a
domain expert's approval has more weight than an LLM-suggested entry,
and so refinements are auditable.

Restructuring now (before we have meaningful curated data) is cheap;
restructuring later means migration scripts, dual-read periods, and
disrupting active reviewers.

## 2. Goals & Non-Goals

### Goals

- A four-layer architecture (`core/`, `goldens/`, `pipelines/`,
  `evaluators/`) that absorbs all three growth directions without
  cross-cutting changes.
- An event-sourced golden-set storage that records every create / review
  / refine / deprecate as an append-only event, with strong identity
  and idempotency guarantees.
- A single golden entry can be reviewed by multiple actors (humans and
  LLMs), with each review carrying actor identity, level, action, and
  notes. The "level" of a golden is derived from its review chain.
- Storage is **API-ready from day one** (cross-process locking, pure
  functions, idempotent appends) so that the later HTTP service is a
  thin wrapper, not a refactor.
- Multi-vendor LLM client abstraction (`core/llm_clients/`) supporting
  Azure OpenAI, OpenAI direct, Ollama (local), and Anthropic.
- Phased delivery: pure restructure first, behaviour preserved; then
  features added on the new shape.

### Non-Goals

- Web UI or HTTP API in this phase — designed for, not built in,
  Phase A. (Phase A.5 builds it.)
- Migration of existing golden data — none exists yet (a few test runs,
  no curated entries to preserve).
- AzureAD / SSO authentication — Phase A.5 starts with simple
  token-header auth; SSO later if needed.
- Production database — JSONL event log only in Phase A and A.5; DB is
  Phase B+.
- Backup / DR strategy — explicitly deferred (user accepted risk).

## 3. Architecture Overview

```
features/
├── core/
│   └── llm_clients/                ← NEW — multi-vendor LLM abstraction
│       ├── base/                   ← LLMClient protocol
│       ├── azure_openai/
│       ├── openai_direct/
│       ├── ollama_local/
│       └── anthropic/
│
├── goldens/                        ← NEW — replaces query-index-eval/datasets + curate
│   ├── schemas/
│   │   ├── base.py                 ← Event, Review, HumanActor, LLMActor
│   │   ├── retrieval.py            ← RetrievalEntry (Phase A)
│   │   ├── answer_quality.py       ← AnswerQualityEntry (Phase B)
│   │   └── classification.py       ← ClassificationEntry (Phase C)
│   ├── storage/
│   │   ├── log.py                  ← append_event, read_events (fcntl-locked)
│   │   ├── projection.py           ← build_state(events) → entries
│   │   └── ids.py                  ← UUID4 helpers, idempotency
│   ├── creation/
│   │   ├── synthetic.py            ← LLM-generated entries (creates + LLM review)
│   │   ├── curate.py               ← interactive CLI (replaces old curate.py)
│   │   └── import_faq.py           ← bulk import from FAQ-style sources
│   ├── operations/
│   │   ├── add_review.py           ← human/LLM signs off on existing entry
│   │   ├── refine.py               ← edit existing entry → new entry + deprecate old
│   │   └── deprecate.py            ← mark entry deprecated
│   └── api/                        ← Phase A.5 — FastAPI wrapping the above
│
├── pipelines/                      ← NEW — replaces query-index/, ingestion/
│   ├── base/                       ← Pipeline protocol (search, ingest)
│   ├── microsoft/
│   │   ├── ingestion/              ← from features/ingestion/
│   │   ├── retrieval/              ← from features/query-index/
│   │   └── clients/                ← Azure-specific clients
│   └── custom/                     ← future self-hosted pipeline
│
└── evaluators/                     ← NEW — replaces query-index-eval/{metrics,runner}
    ├── base/                       ← Evaluator protocol
    ├── chunk_match/                ← Recall@k, MRR (today's metrics.py)
    ├── llm_judge/                  ← single-LLM rating (Phase B)
    └── multi_agent/                ← multi-LLM aggregation (Phase C)
```

### Layer responsibilities

- **`core/`** — cross-cutting infrastructure consumed by any other layer.
  Today: LLM clients only.
- **`goldens/`** — the source of truth for evaluation data. Knows nothing
  about pipelines or evaluators; only stores entries and reviews.
- **`pipelines/`** — implementations of search/ingest. Each pipeline knows
  its own infrastructure (Azure, custom). Pipelines do not know about
  goldens or evaluators.
- **`evaluators/`** — combines a pipeline's output with goldens to produce
  a metric. Pulls in goldens and pipelines, but neither pulls in
  evaluators.

### Import boundary direction

```
evaluators/  →  goldens/  ←  goldens/api/
evaluators/  →  pipelines/
goldens/     →  core/
pipelines/   →  core/
```

The existing `scripts/check_import_boundary.sh` is extended to enforce
these directions. No back-edges allowed.

## 4. Data Model

### 4.1 Events (storage layer)

Storage is append-only. Every state change is an event:

```python
@dataclass(frozen=True)
class Event:
    event_id: str            # UUID4 — idempotency key, dedup across machines
    timestamp_utc: str       # ISO-8601 with Z suffix
    event_type: Literal["created", "reviewed", "deprecated"]
    entry_id: str            # UUID4 — which entry this event acts on
    schema_version: int      # 1 today; bumped on breaking schema changes
    payload: dict            # event-type-specific (see §4.2)
```

Storage on disk: one JSONL file per dataset under
`outputs/<doc-slug>/datasets/golden_events_v1.jsonl`. One event per
line. Events appended with `fcntl.LOCK_EX` and `fsync` on every write.

### 4.2 Event payloads

**`created`** — first appearance of an entry:
```python
{
    "task_type": "retrieval",         # or "answer_quality" / "classification"
    "entry_data": {...},              # the typed entry payload (see §4.4)
    "actor": {...},                   # HumanActor or LLMActor (see §4.3)
    "action": "created_from_scratch", # or "synthesised", "imported_from_faq"
    "notes": str | None,
}
```

**`reviewed`** — an actor signs off (or rejects) an existing entry:
```python
{
    "actor": {...},
    "action": "accepted_unchanged" | "approved" | "rejected",
    "notes": str | None,
}
```

**Refinement** is not its own event type. It is implemented as a
`created` event for the refined entry (with `refines: <old_entry_id>`
in `entry_data`), followed by a `deprecated` event on the old entry.
Both events are written within a single `flock`-protected critical
section so the projection always sees them together or not at all.

**`deprecated`** — entry marked as no longer valid:
```python
{
    "actor": {...},
    "reason": str | None,
}
```

### 4.3 Actors

```python
@dataclass(frozen=True)
class HumanActor:
    kind: Literal["human"] = "human"
    pseudonym: str           # GDPR-safe identifier; mapped to real names externally
    level: Literal["expert", "phd", "masters", "bachelors", "other"]

@dataclass(frozen=True)
class LLMActor:
    kind: Literal["llm"] = "llm"
    model: str               # e.g. "gpt-4o", "claude-opus-4-7"
    model_version: str       # provider-reported version string
    prompt_template_version: str   # internal version of the prompt used
    temperature: float
```

Actor identity goes into every event. The set of actors that have ever
reviewed an entry forms its **review chain**.

### 4.4 RetrievalEntry (Phase A)

```python
@dataclass(frozen=True)
class RetrievalEntry:
    entry_id: str
    task_type: Literal["retrieval"]
    query: str
    expected_chunk_ids: list[str]
    chunk_hashes: dict[str, str]        # chunk_id → sha256:... at curation time
    review_chain: list[Review]          # derived from events on this entry_id
    deprecated: bool                    # derived
    refines: str | None                 # entry_id of predecessor, if refined

    @property
    def level(self) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
        """Highest human level in review_chain; 'synthetic' if only LLM actors."""
```

`Review` is the projection of a `reviewed` (or `created`) event:

```python
@dataclass(frozen=True)
class Review:
    timestamp_utc: str
    action: Literal[
        "created_from_scratch", "synthesised", "imported_from_faq",
        "accepted_unchanged", "approved", "rejected",
        "deprecated",
    ]
    actor: HumanActor | LLMActor
    notes: str | None
```

### 4.5 Future entry types (sketch only — Phase B/C)

`AnswerQualityEntry`: query + reference answer + scoring rubric.
`ClassificationEntry`: chunk_id + expected labels.

Both will share `entry_id`, `review_chain`, `deprecated`, `refines`.
Only the typed payload differs.

## 5. Storage Design

### 5.1 Cross-process locking

Every append to the JSONL takes an exclusive lock for the duration of
the write:

```python
def append_event(path: Path, event: Event) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            if _event_id_already_present(path, event.event_id):
                return  # idempotent no-op
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

This works correctly for the CLI today (single process, lock is no-op
overhead) and the FastAPI service in Phase A.5 (multiple workers can
share the file).

### 5.2 Idempotency

Every event has a UUID4 `event_id` generated by the producer. The
storage layer checks for prior occurrences before appending. This means
HTTP retries in Phase A.5 are safe: the same `event_id` posted twice
results in one stored event.

`_event_id_already_present` is implemented as a linear scan in v1
(acceptable up to ~100k events). A bloom filter or sidecar index can
be added if the file grows beyond that.

### 5.3 Pure functions, no shared state

`append_event(path, event)`, `read_events(path) -> list[Event]`, and
`build_state(events) -> dict[entry_id, Entry]` are all pure functions
of their inputs. No singletons, no module-level state. This makes the
API wrapper in Phase A.5 trivial and keeps tests deterministic.

### 5.4 Projection

`build_state` reduces the event list to a dict of current entries,
sorting events by `timestamp_utc` first to tolerate out-of-order writes
(possible if events are produced on different machines with skewed
clocks; less critical in the single-machine A.5 deployment but
preserved for B+). It applies events in order and produces:

- `dict[entry_id, Entry]` — current state, including deprecated ones
- An iteration helper `active_entries()` filtering out `deprecated=True`

## 6. Schema Versioning Rules

Three rules, enforced from day one:

1. **Additive only.** New fields must be optional with a default.
   Field renames and semantic changes are forbidden within a major
   version.
2. **Loader is tolerant.** Unknown fields are logged and ignored, not
   rejected. Missing optional fields are filled with their declared
   defaults at read time.
3. **Breaking changes require a `schema_version` major bump.** Going
   from `schema_version: 1` to `2` is an explicit, documented decision
   and ships with a migration script. The loader dispatches on major
   version.

Naming conventions, locked from day one:

- `snake_case` for all field names.
- ISO-8601 timestamps with `Z` suffix (UTC only).
- UUID4 for all IDs.
- Lowercase string literals for enum-like fields.

These conventions live in `docs/conventions/data-format.md` (to be
written as part of Phase 0).

## 7. Phasing

### Phase 0 — Pure restructure (no behaviour change)

One PR. Moves files into the new layout, renames packages, updates
imports, extends the boundary check. After Phase 0 the test suite must
pass with the same coverage as before.

Concretely:

- `features/query-index/` → `features/pipelines/microsoft/retrieval/`
  (whole package preserved; the internal split into a separate
  `clients/` sub-package is deferred to Phase A.1, when
  `core/llm_clients/` arrives and the natural co-location pattern
  becomes concrete)
- `features/ingestion/` → `features/pipelines/microsoft/ingestion/`
- `features/query-index-eval/src/query_index_eval/metrics.py` →
  `features/evaluators/chunk_match/metrics.py`
- `features/query-index-eval/src/query_index_eval/runner.py` →
  `features/evaluators/runner.py` (or split if needed)
- `features/query-index-eval/src/query_index_eval/curate.py` →
  **deleted** in Phase 0 (no curated data exists yet, user-confirmed;
  replaced by event-sourced equivalent in Phase A.4).
- `features/query-index-eval/src/query_index_eval/datasets.py` and
  `schema.py` → **kept intact in Phase 0**. They contain dataset I/O
  (`load_dataset`) and metrics types (`MetricsReport`, `AggregateMetrics`,
  `RunMetadata`, etc.) still required by `runner.py`. In Phase A these
  files are split: `EvalExample` and `load_dataset` are replaced by
  `goldens/`; the metrics types stay with `evaluators/chunk_match/` as
  they belong to the evaluator's output, not to goldens.

The `query-eval` CLI temporarily loses its `curate` subcommand at the
end of Phase 0 and regains it in Phase A.4 (now backed by the event
log). The `run-eval` and `report` subcommands continue to work
throughout, wired against `evaluators/` instead of the old
`query_index_eval` module. Makefile targets are updated in the same
PR; no wrapper-module shims are needed because there is no external
caller relying on the old import paths. Python import names
(`query_index`, `ingestion`, `query_index_eval`) remain stable in
Phase 0; only directory paths change. Internal module renames happen
opportunistically in Phase A.

### Phase A — Build the new `goldens/` (event-sourced)

One PR per package boundary, in order:

A.1. `core/llm_clients/` with the four backend implementations and a
shared `LLMClient` protocol. Test with mocked HTTP transports; one
manual integration smoke test per backend.

A.2. `goldens/schemas/` — `Event`, `Review`, `HumanActor`,
`LLMActor`, `RetrievalEntry`. 100 % coverage (per
`docs/evaluation/coverage-thresholds.md`).

A.3. `goldens/storage/` — `log.py`, `projection.py`, `ids.py`. 95 %+
coverage. Includes the multiprocess concurrent-append test.

A.4. `goldens/creation/curate.py` — interactive CLI built on the
event log. Preserves the TTY-required guard and anti-paste warning
from the previous `curate.py`. Adds an identity prompt: on first run
it asks the curator for their pseudonym and level, then caches the
answer in `~/.config/goldens/identity.toml` for subsequent runs.
Re-instates the `query-eval curate` subcommand removed in Phase 0.

A.5. `goldens/creation/synthetic.py` — generates entries via an LLM
client, records both a `created` event (action `synthesised`,
LLMActor) and any post-generation human review separately.

A.6. `goldens/operations/` — `add_review`, `refine`, `deprecate`.
90 %+ coverage.

A.7. `evaluators/chunk_match/` is wired against the new goldens
projection. Existing eval CLI (`query-eval run-eval`) keeps working.

After Phase A, the user can curate, synthesise, review, and refine
golden retrieval entries entirely from the CLI, on a single machine.

### Phase A.5 — HTTP API + frontend

A.5.1. `goldens/api/` — FastAPI app. Endpoints:

- `POST /entries` — create from scratch
- `POST /entries/{entry_id}/reviews` — add a review
- `POST /entries/{entry_id}/refine` — refine
- `POST /entries/{entry_id}/deprecate` — deprecate
- `GET /entries` — list (filterable)
- `GET /entries/{entry_id}` — detail with review chain
- `POST /synthesise` — request synthetic generation

Pydantic mirror schemas for HTTP I/O; conversion to/from the
dataclass schemas at the boundary. Auth via `X-Auth-Token` header
checked against a server-local token map.

A.5.2. `frontend/` — separate top-level directory, separate package
manager (npm). Built artifacts served as static files by FastAPI via
`app.mount("/", StaticFiles(directory="frontend/dist", html=True))`.
Simple SPA; consumes the HTTP API; no business logic.

A.5.3. Deployment: single FastAPI process on the user's local machine,
exposed on the company network. IT clearance required (open issue,
tracked separately). Single point of failure accepted.

### Phase B — Answer-quality goldens + LLM-judge

B.1. `goldens/schemas/answer_quality.py` — new entry type.

B.2. `evaluators/llm_judge/` — single-LLM rating evaluator, using
`core/llm_clients/`.

B.3. Frontend extended for answer-quality review.

### Phase C — Classification goldens + multi-agent evaluator

C.1. `goldens/schemas/classification.py`.

C.2. `evaluators/multi_agent/` — multiple LLM judges with
aggregation rules.

## 8. Testing Strategy

Coverage targets per `docs/evaluation/coverage-thresholds.md`:

- `goldens/schemas/` — 100 %
- `goldens/storage/` — 95 %+
- `goldens/creation/` — 70 % (LLM mocked; integration tests separate)
- `goldens/operations/` — 90 %+
- `core/llm_clients/` — 85 %+ (HTTP mocked; one manual smoke per backend)
- `pipelines/microsoft/` — coverage preserved from current packages
- `evaluators/` — 90 %+ for `chunk_match`; LLM-based evaluators 70 %+

Three additional test classes added in Phase A.3 (storage):

1. **Concurrent-append test.** Two `multiprocessing.Process` workers
   each append 50 events to the same file. Result must contain 100
   distinct events with unique `event_id`s, no malformed lines.
2. **Idempotency test.** Same `event_id` appended twice → file has
   one event.
3. **Out-of-order projection test.** Events with non-monotonic
   timestamps → `build_state` produces correct final state.

Linux-only tests (`fcntl.flock` semantics) are marked
`@pytest.mark.skipif(sys.platform != "linux", ...)`. CI runs on Linux;
local development on macOS / WSL is not blocked.

LLM integration tests live under `tests/integration/` and are
opt-in via `pytest -m integration`. Not part of the default suite.

## 9. Decision Log (kreuzverhör outcomes)

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| R1 | Storage shape | Event-sourced JSONL | Append-only fits multi-reviewer workflow; trivial concurrency in single-writer deployment. |
| R2 | Review UI in CLI | None — CLI stays simple | Future web UI handles checkbox-style sign-off; CLI does single curate / single review. |
| R3 | LLM clients | `core/llm_clients/` as 4th layer (option iii) | Multiple endpoints (Azure / OpenAI direct / Ollama / Anthropic) need shared abstraction. |
| R4 | Phase ordering | Phase 0 (pure restructure) → A → A.5 → B → C | Pure restructure first lets us land features on a clean shape. |
| R5 | API readiness | Storage built API-ready in Phase A; service in A.5 | ~30–50 LOC extra now (fcntl, pure functions, idempotency) saves a 200-LOC refactor later. Submodule `goldens/api/` with optional FastAPI dependency. Frontend separate. Auth via token header. |
| R6 | Migration | None — fresh start | No curated data to preserve (only test runs). |
| R7 | Schema versioning | Additive-only + tolerant loader + `schema_version` major bumps | Simplest forward-compatible rule that survives unforeseen field additions. |
| R8 | Testing strategy | Per-module coverage thresholds | Reflects determinism: 100 % schemas, 95 % storage, 70 % LLM-touching code. Documented in `docs/evaluation/coverage-thresholds.md`. |

## 10. Open Questions

1. **IT clearance for network exposure.** Phase A.5 depends on opening
   a port on the user's VDI to the company network. Discussion
   ongoing. Phase A is not blocked by this.
2. **Curator identity persistence.** First proposal:
   `~/.config/goldens/identity.toml` with `pseudonym` and `level`. Open
   to a per-repo override. To be finalised when implementing
   `goldens/creation/curate.py`.

## 11. Out of Scope (to keep this spec focused)

- Backup / disaster recovery strategy — deferred per user decision.
- Production database (Postgres etc.) — Phase B+ at earliest.
- AzureAD / SSO authentication — token-header auth is sufficient for
  ≤20 users.
- High-availability deployment — not needed (single VDI accepted).
- Rate limiting on the HTTP API — only ≤20 trusted users on a
  closed network.
- Frontend internationalisation, accessibility audit, design system —
  in-scope for the frontend project itself, not for this spec.
