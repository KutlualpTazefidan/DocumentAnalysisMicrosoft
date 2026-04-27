# Query Index Evaluation — Design

**Date:** 2026-04-27
**Status:** Approved through brainstorming. Implementation pending.

## Goal

Build a professional retrieval-quality evaluation pipeline for the `query-index` feature against an Azure AI Search index. The pipeline measures whether the index returns the chunks that should be returned for a given query, using IR metrics. The repository structure is set up so that future small features in this monorepo follow the same conventions.

## Out of scope

- End-to-end answer quality (RAGAS / LLM-as-judge). Separate future feature.
- Synthetic test-set generation. Designed-for but not built in this iteration. Deferred until the hand-curated golden set is large enough that synthetic ceiling effects become observable.
- Continuous integration (GitHub Actions or similar). Deferred until a forcing function exists (second contributor, scheduled live runs, or PR gating).
- Pipeline-grade ingestion at scale. `ingest.py` is included as a small helper; production ingestion is its own concern.

## Workspace model

This repository follows a **workspace separation** pattern.

- This workspace is for development. Sample / non-sensitive data lives in `data/` here. Claude has full access.
- Production runs happen in a separate cloned workspace maintained by the user, with real data populated into `data/` and real credentials in `.env`.

Both workspaces share the same code via git. The following are gitignored so each workspace has its own copy: `data/`, `data_dummy/`, `.env`, `datasets/golden_*.jsonl`, `reports/`, `.venv/`, caches.

## Repository layout

```
DocumentAnalysisMicrosoft/
├── .gitignore
├── README.md                    # explains the clone-to-deploy workflow
├── bootstrap.sh                 # creates .venv and editable installs
├── Makefile                     # eval, curate, ingest, schema-discovery, test, lint
├── requirements-dev.txt         # ruff, mypy, pytest, pytest-cov, pre-commit
├── pyproject.toml               # repo-level lint/test config
├── .pre-commit-config.yaml
│
├── archive/
│   └── query_index_v0.py        # original prototype, preserved unchanged
├── data/                        # gitignored; sample data here, real data in user workspace
├── data_dummy/                  # gitignored; not part of this design
│
├── docs/
│   ├── superpowers/specs/       # this design document
│   └── evaluation/
│       └── metrics-rationale.md # already exists; metric choice and stats thresholds
│
└── features/
    ├── query-index/             # search library
    └── query-index-eval/        # this evaluation pipeline
```

## Boundary rules

1. **Only `features/query-index` may import `azure.*` or `openai`.** Enforced by a small pre-commit hook that greps for those imports outside that package.
2. `archive/query_index_v0.py` is preserved byte-for-byte. No code in the repository imports from `archive/`. The original is referenced from the repo `README.md` as a historical artefact.
3. `.env` lives at repo root and is loaded once by the CLI entry-point. Each package's `.env.example` documents the variables it needs.
4. **Logs and reports never contain chunk text.** Enforced by `repr=False` on `SearchHit.chunk` plus a lint check that forbids `hit.chunk` references inside `query-index-eval` (the evaluation pipeline never needs the chunk content — only chunk_ids).

## Stack and tooling

- **Python ≥ 3.11**
- **Package management:** `pip` + `venv` with editable installs across the monorepo. No `uv` (Microsoft tooling compatibility unverified; `pip` is the safest baseline).
- **Lint and format:** `ruff` (replaces black, isort, flake8).
- **Type checking:** `mypy`, non-strict initially, tightenable later.
- **Testing:** `pytest` with `pytest-cov`. Mocked unit tests only — no live tests in CI/local. The user verifies live behavior in their separate workspace.
- **Pre-commit:** `pre-commit` running ruff and mypy on staged files, plus the import-boundary check above.
- **Secrets:** `.env` at repo root, gitignored; `.env.example` per package documents required variables.

## Feature boundary rule

A subsystem becomes its own package when at least two of:

1. It has external dependencies that other packages do not need.
2. It is consumed by at least one other package.
3. It is large enough that independent tests and documentation are warranted.

Otherwise it is a submodule within an existing package. By this rule:

| Subsystem | Decision |
|---|---|
| `query-index` | Own package (all three) |
| `query-index-eval` | Own package (1 and 3) |
| `synthesize` (future) | Submodule of `query-index-eval` |
| `schema-discovery` | Module inside `query-index` |
| `curate-cli` | Submodule of `query-index-eval` |

## Package: `query-index`

### Purpose

The only package that talks to Azure AI Search and Azure OpenAI. Provides hybrid search, chunk fetching, and helper utilities used by other features.

### Layout

```
features/query-index/
├── pyproject.toml
├── README.md
├── .env.example
├── src/query_index/
│   ├── __init__.py              # public API re-exports
│   ├── config.py                # ENV → frozen Config dataclass
│   ├── client.py                # builds AzureOpenAI + SearchClient lazily
│   ├── search.py                # hybrid_search
│   ├── chunks.py                # get_chunk, sample_chunks
│   ├── embeddings.py            # get_embedding
│   ├── ingest.py                # populate_index helper
│   ├── schema_discovery.py      # print_index_schema
│   └── types.py                 # SearchHit, Chunk
└── tests/
    └── unit/                    # all mocked
```

### Public API

```python
from query_index import (
    Chunk,
    Config,
    SearchHit,
    get_chunk,
    get_embedding,
    hybrid_search,
    sample_chunks,
)
```

### Types

```python
@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    title: str
    chunk: str = field(repr=False)

@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    title: str
    chunk: str = field(repr=False)
    score: float

    def __str__(self) -> str:
        return f"SearchHit(id={self.chunk_id}, score={self.score:.3f})"
```

`repr=False` on the `chunk` field prevents accidental leakage into logs, exception tracebacks, and pytest failure output.

### Public functions

```python
def hybrid_search(
    query: str,
    top: int = 10,
    filter: str | None = None,
) -> list[SearchHit]: ...

def get_chunk(chunk_id: str) -> Chunk: ...

def sample_chunks(n: int, seed: int) -> list[Chunk]: ...

def get_embedding(text: str) -> list[float]: ...
```

### Configuration

`config.py` reads from environment and returns a frozen `Config` dataclass:

- `AI_FOUNDRY_KEY`
- `AI_FOUNDRY_ENDPOINT`
- `AI_SEARCH_KEY`
- `AI_SEARCH_ENDPOINT`
- `AI_SEARCH_INDEX_NAME`
- `EMBEDDING_DEPLOYMENT_NAME`
- `EMBEDDING_MODEL_VERSION`
- `EMBEDDING_DIMENSIONS`
- `AZURE_OPENAI_API_VERSION`

Loaded once. Missing required variables raise on first access with a clear message naming the missing key.

### Helper functions

`ingest.populate_index(source_path: Path, index_name: str)` reads documents from `source_path`, chunks them, embeds them, and uploads. Logs metadata only — never chunk text. Used to populate an empty index.

`schema_discovery.print_index_schema(index_name: str)` calls `SearchIndexClient.get_index(name)` and prints the field definitions. Used to confirm field names before depending on them.

### Tests

Unit tests only. All Azure clients mocked via `unittest.mock`. Coverage target ≥ 90% on `src/query_index/`.

## Package: `query-index-eval`

### Purpose

Consumes `query-index` to evaluate retrieval quality against hand-curated query/expected-chunk pairs. Produces metric reports.

### Layout

```
features/query-index-eval/
├── pyproject.toml               # depends on query-index via editable workspace path
├── README.md
├── .env.example
├── src/query_index_eval/
│   ├── __init__.py
│   ├── schema.py                # EvalExample, MetricsReport
│   ├── datasets.py              # JSONL load/save, append-only enforcement
│   ├── curate.py                # interactive CLI loop
│   ├── metrics.py               # Recall@k, MAP, Hit Rate@k, MRR — pure
│   ├── runner.py                # eval orchestration + sample-size flagging
│   └── cli.py                   # entry point: curate, eval, report, schema-discovery
├── datasets/
│   └── golden_v1.jsonl          # gitignored, append-only
└── reports/                     # gitignored
    └── *.json
```

### Dataset schema

`EvalExample` (one JSONL line):

```json
{
  "query_id": "g0001",
  "query": "Wo ist die Änderung des Tragkorbdurchmessers aufgeführt?",
  "expected_chunk_ids": ["chunk_42", "chunk_43"],
  "source": "curated",
  "chunk_hashes": {"chunk_42": "sha256:...", "chunk_43": "sha256:..."},
  "filter": null,
  "deprecated": false,
  "created_at": "2026-04-27T10:00:00Z",
  "notes": null
}
```

- `query_id`: stable identifier; `g####` for golden, `s####` reserved for future synthetic.
- `expected_chunk_ids`: list. Multi-chunk relevance is the norm (the user explicitly confirmed several chunks may legitimately match a query, with rank ordering mattering).
- `source`: `"curated"` for now. Reserved value `"synthetic"` for future.
- `chunk_hashes`: SHA-256 over the **whitespace-normalized** chunk text at curation time. Detects drift after re-ingestion. Whitespace-normalization is `" ".join(text.split())`.
- `filter`: optional Azure-Search filter expression to apply when running this query (supports filter-aware evaluation per filter axis).
- `deprecated`: marks examples to exclude from current evaluation while preserving historical rows.

### Mutation rules

`golden_v1.jsonl` is immutable except for one controlled mutation:

| Operation | Allowed? |
|---|---|
| Append a new example | Yes |
| Flip an existing example's `deprecated` field from `false` to `true` | Yes |
| Edit `query`, `expected_chunk_ids`, `filter`, `chunk_hashes`, or any other field of an existing example | **No** in `_v1`. To correct an example, deprecate it and append a new one. |
| Flip `deprecated` from `true` back to `false` (un-deprecate) | **No.** Append a new example instead. |
| Schema change | Bump file to `golden_v2.jsonl`; `_v1` stays frozen. |

`datasets.py` enforces these at write time. Any other mutation raises. This guarantees that historical reports remain comparable: the active examples in `_v1` may shrink as deprecations land, but no past example's content silently changes.

### Curation CLI

`query-eval curate` runs an interactive loop:

1. **Refuses to run without interactive TTY.** Checks `os.isatty(sys.stdin.fileno())` and exits 1 with a clear message if false. This prevents accidental invocation through Claude's Bash tool, which is non-interactive.
2. Picks a chunk: random sample via `sample_chunks(1, seed=...)` or user-supplied `--chunk-id`.
3. Prints chunk text to stdout — terminal only, never persisted to file.
4. Prompts: *"Write a query this chunk should answer:"*.
5. **Substring check:** if the user's query contains a contiguous substring of length ≥ 30 characters from the chunk text, the CLI warns and requires explicit confirmation (default: abort). Prevents accidental copy-paste of chunk content into the query field.
6. Optional: runs `hybrid_search(query)` and shows top-5 chunk_ids so the user can decide whether to add additional chunks to `expected_chunk_ids` beyond the source chunk.
7. Confirms: *"Add this example to golden_v1.jsonl?"*.
8. On yes: appends a new JSONL line including `chunk_hashes` for all `expected_chunk_ids`.

A reminder is shown at the start and end of every session: *"Reminder: never paste chunk text into Claude chat. Reference chunks only by chunk_id."*

### Metrics

All metrics are pure functions over `(expected_ids: set[str], retrieved_ids: list[str]) -> float`. No I/O, no Azure calls.

| Metric | Definition |
|---|---|
| Recall@k | `\|expected ∩ retrieved[:k]\| / \|expected\|` |
| Hit Rate@k | `1.0` if `expected ∩ retrieved[:k]` is non-empty, else `0.0` |
| MRR | `1 / rank` of the first relevant retrieved chunk, else `0.0` |
| MAP | mean of `precision@k` over the ranks where each relevant item appears |

Reported metrics: Recall@5, Recall@10, Recall@20, MAP, Hit Rate@1, MRR.

Operational metrics added per run: mean latency, p95 latency, total queries, total embedding calls, failure count.

For the rationale behind these choices and the synthetic-data ceiling effect, see `docs/evaluation/metrics-rationale.md`.

### Runner and reports

`runner.run_eval(dataset_path, top_k_max=20, filter_default=None) -> MetricsReport`

Flow:

1. Load `EvalExample`s; filter out `deprecated`.
2. For each example: call `hybrid_search(query, top=top_k_max, filter=example.filter or filter_default)`.
3. Record per-query: `query_id`, `expected_chunk_ids`, retrieved chunk_ids in order, ranks of expected items, hit booleans, `latency_ms`.
4. Aggregate metrics across the dataset.
5. Write report to `reports/<UTC-timestamp>-golden_v1.json` and a Markdown summary to stdout.

`MetricsReport` includes:

- Aggregate metrics (Recall@5/10/20, MAP, Hit Rate@1, MRR, latency stats, counts).
- Run metadata: dataset path, dataset size (active and deprecated counts), `embedding_deployment_name`, `embedding_model_version`, `azure_openai_api_version`, `search_index_name`, run timestamp (UTC).
- Per-query records (chunk_ids only — never chunk text).

### Sample-size flagging

Reports flag dataset size against thresholds documented in `docs/evaluation/metrics-rationale.md`:

| n | Status |
|---|---|
| n < 30 | "Indicative — not statistically reliable" (highlighted in console output) |
| 30 ≤ n < 100 | "Preliminary" with confidence intervals |
| n ≥ 100 | Reportable |

Thresholds are convention. The rationale file documents the formula for deriving the required `n` for any target precision.

### Compare command

`query-eval report --compare reports/A.json reports/B.json` prints a side-by-side diff. Raises a warning if the two reports were produced with different `embedding_deployment_name`, `embedding_model_version`, `azure_openai_api_version`, or `search_index_name` — comparing across these is meaningless for retrieval quality assessment.

### CLI

```
query-eval curate                            # interactive curation
query-eval eval --top 20                     # run evaluation, write report
query-eval report --compare A.json B.json
query-eval schema-discovery                  # dump current index schema
```

Console-script entry point registered in `pyproject.toml`. Loads `.env` once at startup.

### Tests

Unit tests only. Mocked Azure clients. Strong parametric coverage on `metrics.py` (every metric tested with hand-computed expected values across single-chunk, multi-chunk, all-miss, all-hit, partial-hit, out-of-order cases). JSONL round-trip tests on `datasets.py`. Append-only enforcement tested explicitly.

Coverage target: ≥ 90% on `src/query_index_eval/`, with `metrics.py` at 100%.

## Memory and conventions

Two project-level Memory entries are saved (apply across all future Claude sessions on this repository):

1. **Workspace separation pattern** — no folder-level boundaries here; user maintains a separate cloned workspace for production.
2. **Document numerical rationale** — every cited threshold, convention, or "rule of thumb" gets a derivation file under `docs/`; chat carries only the conclusion plus a path reference.

## Open items deferred to implementation phase

- **Final field names for the Azure index.** Resolved by running `query-eval schema-discovery` once an index exists. The dataset schema does not depend on field names beyond `chunk_id`.
- **Filter axes for the corpus.** Decided based on observed structure during initial use. The `EvalExample.filter` field already supports per-query filters; no schema change required when filters are introduced.
- **Initial sample data.** The user's workspace already contains `GNB B 147_2001 Rev. 1.pdf` in `data/`. Whether to use this as the initial development corpus or add others is the user's choice.

## Acceptance criteria

The implementation is complete when:

1. `bootstrap.sh && make test` runs all unit tests successfully with ≥ 90% coverage on both packages, with `metrics.py` at 100%.
2. `make lint` passes ruff and mypy with zero errors.
3. `archive/query_index_v0.py` exists, byte-for-byte unchanged from the original `query_index.py`.
4. `query-eval curate` refuses to run without an interactive TTY, with a clear error message.
5. `query-eval eval` produces a JSON report with all metric fields and metadata fields populated, given a populated `golden_v1.jsonl` and a populated Azure index. Verified by the user in their separate workspace.
6. The boundary rule (`azure.*` and `openai` imports only inside `features/query-index`) is enforced by a passing pre-commit hook.
7. `README.md` at the repo root explains the clone-to-deploy workflow. Each package has a one-page `README.md` describing its purpose, public API, environment variables, and how to run its tests.
