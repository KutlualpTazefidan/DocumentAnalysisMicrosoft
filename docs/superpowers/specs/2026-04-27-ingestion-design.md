# Ingestion Pipeline — Design

**Date:** 2026-04-27
**Status:** Approved through brainstorming + Kreuzverhör (6 rounds). Implementation pending.

## Goal

Build a CLI-driven 4-stage ingestion pipeline (`analyze` → `chunk` → `embed` → `upload`) that takes PDFs through Document Intelligence layout analysis, semantic chunking by section, embedding via Azure OpenAI, and into the Azure AI Search index. Replaces the existing `archive/semantic_chunking.ipynb` prototype with a tested, repo-versioned, multi-doc-capable implementation. Integrates with the existing `query-index-eval` feature for end-to-end measurement.

## Out of scope

- Synthetic / LLM-based chunking strategies. The Chunker plugin slot is reserved for future strategies; V1 ships only the section chunker.
- Audio / video ingestion. Document Intelligence handles documents only; multi-modal is a separate future feature.
- Production-scale parallelism (queue-based workers, batch processing). V1 is sequential per-document.
- Index schema migrations. V1 assumes the schema is stable; breaking changes require manual `--force-recreate`.
- CI / GitHub Actions. Deferred per project convention until a forcing function exists.
- Cross-chunker semantic golden sets (golden curated at text-range level, valid across chunkers). Mentioned as a known limitation; per-chunker re-curation is the V1 reality.

## Workspace model

Same as the existing project convention. This workspace is for development with sample data; the user maintains a separate cloned workspace for production. `data/` and `outputs/` are gitignored so each cloned workspace has its own.

## Pre-refactor: query-index updates (separate PR before this feature)

The existing `query-index` package was built around the field names from `archive/query_index_v0.py` (the original prototype). The user has since chosen the notebook's schema (`id`, `chunkVector`, `section_heading`, `source_file`) as canonical. A small refactor PR lands first:

1. **`Chunk` and `SearchHit` dataclasses gain two optional fields:** `section_heading: str | None = None` and `source_file: str | None = None`.

2. **JSON-field lookups updated** to read the notebook schema:
   - `r["id"]` (was `r["chunk_id"]`) — Python attribute name `chunk_id` stays, only the lookup string changes
   - `vector_query.fields = "chunkVector"` (was `"text_vector"`)
   - New optional reads for `r.get("section_heading")` and `r.get("source_file")`

3. **Public API expands** so ingestion can use the same Azure clients via the strict boundary:
   - `from query_index import get_search_client, get_search_index_client` becomes legal (currently those live in `client.py` but are not re-exported)
   - Added to `__all__`

4. **Tests adjusted** for the new field reads and the expanded public-API exports. Coverage maintained ≥ 90%.

This refactor is mechanical (no behavior change beyond the field-name reads) and should land as its own PR.

## Repository layout (after the ingestion feature)

```
DocumentAnalysisMicrosoft/
├── data/                                    # PDFs, gitignored
├── outputs/                                 # all pipeline artifacts, gitignored
│   └── {slug}/                              # per-document folder
│       ├── analyze/
│       │   └── {ts}.json                    # Document Intelligence response
│       ├── chunk/
│       │   └── {ts}-{strategy}.jsonl        # text-only chunks
│       ├── embed/
│       │   └── {ts}-{strategy}.jsonl        # chunks + vectors
│       ├── datasets/
│       │   └── golden_v1.jsonl              # accumulating, append-only
│       └── reports/
│           └── {ts}-{strategy}.json         # eval metric reports
│
├── docs/
│   ├── superpowers/specs/2026-04-27-ingestion-design.md   # THIS DOC
│   └── evaluation/metrics-rationale.md
│
├── scripts/
│   └── check_import_boundary.sh             # extended with two enforcement patterns
│
└── features/
    ├── query-index/                         # post-refactor
    ├── query-index-eval/                    # default paths recognise per-doc structure
    └── ingestion/                           # NEW
        ├── pyproject.toml
        ├── README.md
        ├── .env.example
        ├── src/ingestion/
        │   ├── __init__.py                  # public API re-exports
        │   ├── config.py                    # IngestionConfig (Doc Intel only)
        │   ├── client.py                    # DocumentIntelligenceClient factory
        │   ├── slug.py                      # filename → slug
        │   ├── timestamp.py                 # utc compact iso-8601 helpers
        │   ├── analyze.py                   # PDF → JSON
        │   ├── chunkers/
        │   │   ├── __init__.py
        │   │   ├── base.py                  # protocol Chunker
        │   │   ├── section.py               # V1 chunker (port of notebook logic)
        │   │   └── registry.py              # name → Chunker class mapping
        │   ├── chunk.py                     # CLI handler for chunk stage
        │   ├── embed.py                     # CLI handler for embed stage
        │   ├── upload.py                    # CLI handler for upload stage
        │   └── cli.py                       # entry point: ingest analyze | chunk | embed | upload
        └── tests/
            ├── conftest.py                  # mocked Azure clients, sample analyze JSON
            └── unit/
```

## Boundary rules (extended, strict)

`scripts/check_import_boundary.sh` enforces two patterns:

1. **Search & OpenAI imports — only `features/query-index/`:** `azure.search.documents.*`, `azure.identity.*`, `azure.core.credentials.*`, `openai.*`.
2. **Document Intelligence imports — only `features/query-index/` OR `features/ingestion/`:** `azure.ai.documentintelligence.*`.

Other features cannot import any of the above. They must consume `query-index`'s and `ingestion`'s public APIs. The two patterns share the same indented-imports / prefix-collision guards from the existing hook.

## Stack and tooling

Same as established: Python ≥ 3.11, pip + venv editable installs, ruff, mypy, pytest with mocked Azure clients, pre-commit. Ingestion's `pyproject.toml` declares dependencies on `query-index` (workspace path), `azure-ai-documentintelligence`, `python-dotenv`, and `tiktoken` (used by the section chunker for token-truncation in long chunks).

## Hybrid `cfg` convention

`ingestion` follows the same hybrid-`cfg` pattern as `query-index`:

- `analyze` takes `cfg: IngestionConfig | None = None` (the Doc-Intel-specific config)
- `embed` and `upload` take `cfg: query_index.Config | None = None` (re-using query-index's config since they call query-index's clients)
- All default to `*.from_env()` when `cfg=None`

`IngestionConfig` is a small frozen dataclass:

```python
@dataclass(frozen=True)
class IngestionConfig:
    doc_intel_endpoint: str
    doc_intel_key: str

    @classmethod
    def from_env(cls) -> "IngestionConfig":
        return cls(
            doc_intel_endpoint=os.environ["DOC_INTEL_ENDPOINT"],
            doc_intel_key=os.environ["DOC_INTEL_KEY"],
        )
```

`.env.example` for ingestion documents the new variables alongside re-stating the query-index ones (since users typically have one combined `.env` at repo root):

```
# Document Intelligence (used by `ingest analyze`)
DOC_INTEL_ENDPOINT=https://your-doc-intel.cognitiveservices.azure.com/
DOC_INTEL_KEY=

# All query-index variables (re-used by `ingest embed` and `ingest upload`)
AI_FOUNDRY_KEY=
AI_FOUNDRY_ENDPOINT=https://your-foundry.services.ai.azure.com
AI_SEARCH_KEY=
AI_SEARCH_ENDPOINT=https://your-search.search.windows.net
AI_SEARCH_INDEX_NAME=push-semantic-chunking-1
EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
EMBEDDING_MODEL_VERSION=1
EMBEDDING_DIMENSIONS=3072
AZURE_OPENAI_API_VERSION=2024-02-01
```

## Slug and timestamp helpers

### `slug.py`

```python
def slug_from_filename(filename: str) -> str:
    """Convert a filename to a URL-safe slug.

    Lowercase; replace whitespace, dots, and underscores with hyphens; strip
    non-alphanumeric (except hyphens); collapse runs of hyphens; trim leading/
    trailing hyphens; remove a trailing `.pdf`-equivalent.

    Examples:
        'GNB B 147_2001 Rev. 1.pdf' -> 'gnb-b-147-2001-rev-1'
        'IAEA TS-G-1.1.pdf'         -> 'iaea-ts-g-1-1'
    """
```

### `timestamp.py`

```python
def now_compact_utc() -> str:
    """Return UTC time as compact ISO-8601, suitable for filenames.

    Format: 'YYYYMMDDTHHMMSS' (e.g., '20260427T143000'). No timezone suffix —
    UTC is implicit by convention. Sorts alphabetically equal to chronologically.
    """
```

Both are pure, no I/O, easy to unit-test.

## Sub-feature 1 — `analyze`

**Purpose:** Send a PDF to Azure Document Intelligence (`prebuilt-layout`) and persist the JSON response.

**Module:** `src/ingestion/analyze.py`

**Public function:**
```python
def analyze_pdf(
    in_path: Path,
    out_path: Path | None = None,
    cfg: IngestionConfig | None = None,
) -> Path:
    """Analyze a PDF with Document Intelligence; write JSON to out_path.

    If out_path is None, derive: outputs/{slug(in_path.name)}/analyze/{now_compact_utc()}.json

    Returns the actual out_path used.
    """
```

**Flow:**
1. Resolve `cfg` via hybrid pattern.
2. Resolve `out_path` via auto-derivation if not given.
3. Open `in_path` in binary mode.
4. Construct `DocumentIntelligenceClient(endpoint=cfg.doc_intel_endpoint, credential=AzureKeyCredential(cfg.doc_intel_key))`.
5. Call `client.begin_analyze_document(model_id="prebuilt-layout", analyze_request=f, content_type="application/pdf")`.
6. Wait for `poller.result()` (synchronous; the SDK polls internally).
7. **Wrap the raw response with ingestion metadata** so downstream stages can derive slug + source_file:
   ```json
   {
     "_ingestion_metadata": {
       "source_file": "GNB B 147_2001 Rev. 1.pdf",
       "slug": "gnb-b-147-2001-rev-1",
       "timestamp_utc": "20260427T143000"
     },
     "analyzeResult": { ... }
   }
   ```
8. `out_path.parent.mkdir(parents=True, exist_ok=True)`.
9. `out_path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")`.
10. Print one-line confirmation: `Wrote {out_path} ({page_count} pages, {paragraph_count} paragraphs)`.
11. Return `out_path`.

**Logs metadata only** — never the document content.

**Tests:** `test_analyze.py` mocks `DocumentIntelligenceClient`, asserts the call is made with the right args, asserts the file is written with the expected JSON shape (including the `_ingestion_metadata` sidecar), asserts no document content appears in stdout/stderr.

## Sub-feature 2 — `chunk` (with chunker plugin)

**Purpose:** Read an analyze JSON, run a named chunker strategy, write a text-only chunks JSONL.

### `chunkers/base.py`

```python
from typing import Protocol


class Chunker(Protocol):
    """Protocol for chunking strategies."""
    name: str

    def chunk(
        self,
        analyze_result: dict,
        slug: str,
        source_file: str,
    ) -> list[RawChunk]: ...
```

`RawChunk` is the per-line shape of the chunk JSONL:

```python
@dataclass(frozen=True)
class RawChunk:
    chunk_id: str         # f"{slug}-{seq:03d}"
    title: str            # document title (from the analyze result)
    section_heading: str  # the heading that started this chunk
    chunk: str            # body text
    source_file: str      # original PDF filename, e.g. 'GNB B 147_2001 Rev. 1.pdf'
```

### `chunkers/section.py`

V1 chunker, direct port of the notebook logic.

```python
SKIP_ROLES = frozenset({"pageHeader", "pageFooter", "pageNumber", "footnote"})


class SectionChunker:
    name = "section"

    def chunk(
        self,
        analyze_result: dict,
        slug: str,
        source_file: str,
    ) -> list[RawChunk]:
        result = analyze_result["analyzeResult"]
        paragraphs = result["paragraphs"]

        title = next(
            (p["content"] for p in paragraphs if p.get("role") == "title"),
            "",
        )

        chunks: list[RawChunk] = []
        current_heading: str | None = None
        current_paragraphs: list[str] = []
        seq = 1

        def flush() -> None:
            nonlocal seq
            if current_heading is None:
                return
            chunks.append(
                RawChunk(
                    chunk_id=f"{slug}-{seq:03d}",
                    title=title,
                    section_heading=current_heading,
                    chunk=" ".join(current_paragraphs),
                    source_file=source_file,
                )
            )
            seq += 1

        for p in paragraphs:
            role = p.get("role")
            if role in SKIP_ROLES:
                continue
            if role in ("sectionHeading", "title"):
                flush()
                current_heading = p["content"]
                current_paragraphs = []
            else:
                current_paragraphs.append(p["content"])
        flush()

        return chunks
```

### `chunkers/registry.py`

```python
_REGISTRY: dict[str, type[Chunker]] = {
    "section": SectionChunker,
}


def get_chunker(name: str) -> Chunker:
    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown chunker strategy: {name!r}. "
            f"Available: {', '.join(sorted(_REGISTRY))}"
        )
    return _REGISTRY[name]()


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)
```

### `chunk.py` (the CLI-stage handler)

```python
def chunk(
    in_path: Path,
    strategy: str,
    out_path: Path | None = None,
) -> Path:
    """Run a chunker strategy over an analyze JSON; write chunks JSONL.

    Reads slug and source_file from `_ingestion_metadata` in the analyze JSON.
    Auto-derived out_path: outputs/{slug}/chunk/{ts}-{strategy}.jsonl
    """
```

Reads the analyze JSON, extracts `_ingestion_metadata.slug` and `.source_file`, gets the chunker via `get_chunker(strategy)`, calls `chunker.chunk(analyze_result, slug, source_file)`, writes JSONL where each line is `json.dumps(asdict(raw_chunk))`.

**Tests:** `test_section_chunker.py` uses a hand-crafted `analyze_result` dict (a small Document Intelligence shape with title, sectionHeading, body, pageHeader paragraphs) and asserts the chunks come out correctly. `test_registry.py` checks the registry returns the right class and raises on unknown names.

## Sub-feature 3 — `embed` (separate stage)

**Purpose:** Read a chunks JSONL, embed each chunk via Azure OpenAI, write an embedded JSONL.

**Module:** `src/ingestion/embed.py`

**Public function:**
```python
def embed_chunks(
    in_path: Path,
    out_path: Path | None = None,
    cfg: query_index.Config | None = None,
) -> Path:
    """Read chunks JSONL; for each chunk call query_index.get_embedding;
    write an embedded JSONL where each line includes a `vector` field."""
```

**Flow:**
1. Resolve `cfg` via the query-index hybrid pattern.
2. Auto-derive `out_path` from `in_path`: same name in `outputs/{slug}/embed/{ts}-{strategy}.jsonl`.
3. For each line in `in_path`:
   - Parse JSON to dict.
   - Construct embed input: `{section_heading} {chunk}` (matches notebook — adds heading context to the embedding).
   - Truncate to 8191 tokens via tiktoken.
   - Call `query_index.get_embedding(text, cfg)` → 3072-dim list[float].
   - Add `"vector"` field to the dict.
   - Write line to `out_path`.
4. Print one-line confirmation: `Embedded {n} chunks → {out_path}`.

**Token truncation** (from notebook):

```python
import tiktoken

_MAX_TOKENS = 8191
_ENC = tiktoken.get_encoding("cl100k_base")

def truncate_for_embedding(text: str) -> str:
    tokens = _ENC.encode(text)
    if len(tokens) <= _MAX_TOKENS:
        return text
    return _ENC.decode(tokens[:_MAX_TOKENS])
```

The vast majority of chunks fit. Truncation only applies to very long sections (rare for technical documents but possible for appendices, bibliographies).

**Tests:** `test_embed.py` mocks `query_index.get_embedding` to return a fixed 3072-dim vector, runs `embed_chunks` over a small JSONL fixture, asserts each output line has a `vector` field, asserts the embedding input includes both `section_heading` and `chunk`, asserts truncation kicks in for an artificially long chunk.

## Sub-feature 4 — `upload` (multi-doc cumulative)

**Purpose:** Read an embedded JSONL, upload to the Azure AI Search index. Multi-doc cumulative — deletes only chunks belonging to the source_file in the file before uploading.

**Module:** `src/ingestion/upload.py`

**Public function:**
```python
def upload_chunks(
    in_path: Path,
    index_name: str | None = None,
    force_recreate: bool = False,
    cfg: query_index.Config | None = None,
) -> int:
    """Upload chunks to the index. Returns the number of chunks uploaded.

    Multi-doc behavior:
    - If --force-recreate: drop the entire index, create fresh, upload.
    - Else: ensure index exists (create if not), delete existing chunks where
      source_file == <file in this JSONL>, upload new chunks.
    """
```

**Index schema (created if not exists, matches notebook):**

```python
fields = [
    SimpleField(name="id", type=String, key=True, filterable=True),
    SearchableField(name="title", type=String, analyzer_name="de.lucene"),
    SearchableField(name="section_heading", type=String, analyzer_name="de.lucene"),
    SearchableField(name="chunk", type=String, analyzer_name="de.lucene"),
    SimpleField(name="source_file", type=String, filterable=True, facetable=True),
    SearchField(
        name="chunkVector",
        type=Collection(Single),
        searchable=True,
        vector_search_dimensions=cfg.embedding_dimensions,
        vector_search_profile_name="default-vector-profile",
    ),
]
```

Plus VectorSearch (HNSW + default profile) and SemanticSearch (priority on `section_heading` for title, `chunk` for content), as in the notebook.

**Multi-doc delete-by-filter** (the key Multi-Doc-Cumulative mechanism):

```python
def _delete_existing_chunks_for_source(
    search_client: SearchClient,
    source_file: str,
) -> int:
    """Find all chunks where source_file == <given>, delete by their ids.

    Azure AI Search has no native filter-based delete — we have to query for
    ids first and then delete by key.
    """
    results = search_client.search(
        search_text="*",
        filter=f"source_file eq '{escape_odata_string(source_file)}'",
        select=["id"],
        top=10000,
    )
    ids = [{"id": r["id"]} for r in results]
    if ids:
        search_client.delete_documents(documents=ids)
    return len(ids)
```

`escape_odata_string` doubles single quotes per OData rules (`O'Brien` → `O''Brien`).

**Flow:**
1. Resolve `cfg`.
2. Resolve `index_name`: argument, else `cfg.ai_search_index_name`.
3. Read all lines of `in_path`. Determine the `source_file` (from the first line — all lines are expected to have the same).
4. If `force_recreate`: `index_client.delete_index(index_name)` (swallow not-found), then `index_client.create_index(<schema>)`.
5. Else: if index missing, create; if exists, `_delete_existing_chunks_for_source(search_client, source_file)`.
6. Upload chunks in batches of 100. Sum succeeded / failed.
7. Print: `Uploaded {n} chunks ({deleted} replaced) → {index_name}`.
8. Return number of chunks uploaded.

**Tests:** `test_upload.py` mocks `SearchClient` and `SearchIndexClient`, asserts:
- Index is created if mocked as missing
- Existing chunks for the source_file are deleted (via filter query then by-id delete)
- New chunks are uploaded in correct batches
- `--force-recreate` triggers a full delete+create
- Two source_files in two runs accumulate (the second run does not delete the first's chunks)

## CLI surface

Console-script entry point: `ingest`. Four subcommands.

```bash
ingest analyze --in data/foo.pdf
ingest chunk   --in outputs/foo/analyze/{ts}.json --strategy section
ingest embed   --in outputs/foo/chunk/{ts}-section.jsonl
ingest upload  --in outputs/foo/embed/{ts}-section.jsonl
```

**Default-path inference:** each step propagates metadata forward via the analyze JSON sidecar (`_ingestion_metadata`) and via filename conventions. The user only specifies the input file at each step.

**`--use-latest`:** convenience flag for chunk/embed/upload that means "find the most recent file matching the expected pattern in the right outputs folder". Implemented via globbing + `max(by name)`.

**Tests:** `test_cli.py` mocks each stage's main function (`analyze_pdf`, `chunk`, `embed_chunks`, `upload_chunks`) and asserts the dispatcher routes correctly with the expected arguments.

## Testing strategy

Unit tests only, all mocked. Same conventions as `query-index` and `query-index-eval`:

- `tests/conftest.py` provides shared fixtures: `env_vars`, `mock_doc_intel_client`, `mock_search_client`, `mock_search_index_client`, `sample_analyze_result`.
- pre-commit conventions follow the rest of the repo (B017 → specific exceptions; TC003 → `if TYPE_CHECKING:`; ruff-format auto-applied).
- Coverage target: ≥ 90% on `src/ingestion/`. The chunker plugin's `base.py` (Protocol) is excluded from coverage as it has no runtime code.
- No live tests in CI/local. The user verifies live behavior in the separate cloned workspace.

## Eval integration (Mission C)

The user's mission for V1 is **production CLI + eval integration**. Eval integration means: `query-eval` understands per-doc paths and can run against the index that ingestion just populated.

**`query-index-eval` CLI updates** (small change, separate sub-PR or bundled):

- `query-eval curate`, `query-eval eval`, and `query-eval report` accept a `--doc <slug>` flag.
- When `--doc` is given, defaults derive:
  - `--dataset` → `outputs/{slug}/datasets/golden_v1.jsonl`
  - `--out` → `outputs/{slug}/reports/{ts}-{strategy}.json`
- A `--strategy <name>` flag is also added so the report filename includes the strategy. Default: `unspecified` (when ingestion is not part of the workflow).
- The existing default paths (`features/query-index-eval/datasets/`, `.../reports/`) remain valid — backwards compat for users not using ingestion.

**Convenience: `Makefile` target** chains the whole pipeline:

```makefile
ingest-and-eval:
	@if [ -z "$(DOC)" ] || [ -z "$(STRATEGY)" ] || [ -z "$(PDF)" ]; then \
	    echo "Usage: make ingest-and-eval DOC=foo STRATEGY=section PDF=data/foo.pdf"; exit 1; \
	fi
	ingest analyze --in $(PDF)
	ingest chunk --in $$(ls -1t outputs/$(DOC)/analyze/*.json | head -1) --strategy $(STRATEGY)
	ingest embed --in $$(ls -1t outputs/$(DOC)/chunk/*-$(STRATEGY).jsonl | head -1)
	ingest upload --in $$(ls -1t outputs/$(DOC)/embed/*-$(STRATEGY).jsonl | head -1)
	query-eval eval --doc $(DOC) --strategy $(STRATEGY)
```

Used as: `make ingest-and-eval DOC=gnb-b-147-2001-rev-1 STRATEGY=section PDF="data/GNB B 147_2001 Rev. 1.pdf"`

This is brittle in a few ways (whitespace in PDF filenames, `ls -1t` not portable to all shells) but does the job for local user-runs-it-once-in-a-while. Future improvement: a single `ingest pipeline` command that does all four stages in one process. For V1, the Makefile target is enough.

## Hash drift check (active in `query-index-eval`)

The runner already accepts `chunk_hashes` in `EvalExample`, but does not currently check them. This feature also includes a small change in `runner.py`:

After fetching retrieved chunks for an example, for each `expected_chunk_id` that is also a key of `example.chunk_hashes`:

1. Fetch the chunk from the index via `query_index.get_chunk(chunk_id, cfg)`.
2. Hash its content (whitespace-normalized SHA-256).
3. Compare to `example.chunk_hashes[chunk_id]`.
4. If mismatch: append the example's `query_id` to a `drifted_query_ids` list.

The `MetricsReport.metadata` gains:

- `drifted_query_ids: list[str]` — IDs whose expected chunk content has changed
- `drift_warning: bool` — True if more than 10% of active examples have drift

The CLI prints a clear warning. Without this, multi-chunk-relevance evaluation against a re-chunked index gives silently-wrong results.

## Acceptance criteria

The implementation is complete when:

1. **`bootstrap.sh && make test` passes for all three packages** (`query-index`, `query-index-eval`, `ingestion`) with ≥ 90% coverage on each.
2. **`make lint` passes** (ruff + mypy clean).
3. **Pre-commit boundary check** has the two patterns and:
   - Catches `import azure.search.documents` in `features/query-index-eval/` (negative test: planted violation)
   - Catches `import azure.ai.documentintelligence` in `features/query-index-eval/`
   - Allows `import azure.search.documents` only in `features/query-index/`
   - Allows `import azure.ai.documentintelligence` in either `features/query-index/` or `features/ingestion/`
4. **All four CLI subcommands work** end-to-end against mocked services — `ingest analyze | chunk | embed | upload`.
5. **`ingest --help` lists all four subcommands** with concise descriptions.
6. **Multi-doc cumulative behavior verified** via test: two source_files uploaded in sequence, second upload does not affect first's chunks; re-upload of one source_file deletes only its old chunks.
7. **Hash drift check** emits the expected warning when an `expected_chunk_id`'s content differs from the recorded hash.
8. **Per-doc outputs structure** is followed by all auto-derived defaults; user-supplied `--out` overrides cleanly.
9. **`make ingest-and-eval DOC=... STRATEGY=... PDF=...`** runs the complete pipeline (mocked or live, user discretion).
10. **README documents the workflow** including the four CLI commands, the `outputs/{slug}/` structure, and the relationship to `query-index-eval`.
11. **End-to-end against a real Azure setup — verified by user in their separate cloned workspace** (deferred per spec; AC11).

## Memory and conventions

The two existing project memory entries (workspace separation pattern, document numerical rationale) continue to apply. No new memory entries are needed for this feature.

## Open items deferred to implementation

- **Source-file metadata in analyze JSON sidecar.** The exact JSON key (`_ingestion_metadata`) is locked, but if it conflicts with a future Document Intelligence field, the implementer must rename it.
- **Token-truncation at chunker level vs embed level.** Currently the spec puts truncation in `embed` (where the embedding API hard-limit applies). If the chunker produces a chunk larger than 8191 tokens, the truncation in embed will silently drop content. A future enhancement could surface this as a warning at chunk time.
- **Whether to use API key or DefaultAzureCredential for Document Intelligence.** Current spec uses API key for parity with the notebook. DefaultAzureCredential is preferred for production but requires user has run `az login` and has the right RBAC. A `--credential-type {key,default}` flag could be added in a later iteration.
