# A-Plus.1 — `goldens/api/` (HTTP-Backend) — Design

**Status:** Draft, brainstorming-derived (2026-04-30). Companion to `2026-04-30-pydantic-core-migration-design.md`.

**Prerequisite:** Pydantic-Migration-PR (`refactor/pydantic-core-migration`) merged. This spec assumes domain models in `goldens.schemas` are Pydantic v2 BaseModels.

## 1. Motivation

A.4-A.7 stabilized the goldens stack as a CLI-first system. The smoke-test loop (PRs #15-#17) demonstrated three friction points that a browser-based UI is the natural answer to: dense table elements warrant multiple questions per element (now possible via PR #16), full-table rendering needs space (PR #17), and dry-run flows shouldn't require API keys (PR #15) — all things a browser surfaces more naturally than `query-eval curate`.

The phases-overview document (line 234) anticipates A-Plus as the *"erste echte Backend/Frontend-Parallelisierungs-Chance mit zwei Worktrees"*. This spec covers **only the backend half** (A-Plus.1). The frontend (A-Plus.2) gets its own brainstorming round once the backend contract is fixed.

For Day-1 scope, the user explicitly chose:

- **Single user** (themselves) — no multi-user, no SSO, no DSGVO/IT clearance now
- **Full A.4-A.6 surface** via API: curate, refine/deprecate, synthesise (sync streaming)
- **CLI co-existence** — server reads/writes the same `outputs/`-tree, A.3 file-locking sequences concurrent writes

## 2. Goals & Non-Goals

### Goals

- Single FastAPI process exposing curate / refine / deprecate / synthesise via HTTP
- Element-centric URL design matching the planned UI (phases-overview line 200-221)
- Streaming NDJSON for the long-running synthesise endpoint
- Stateless server (re-read event log per request) — concurrency safety inherited from A.3
- Static-token auth via `X-Auth-Token` header against an env-set token
- `127.0.0.1`-only bind by default — no exposure outside the local machine
- Pydantic-native domain models exposed directly via FastAPI's `response_model=` (no mirror layer)
- Auto-generated `/docs` (Swagger UI) for interactive testing without a frontend
- Test surface covering happy-path + error-path + auth + streaming + CLI/API concurrency
- New CLI sub-command `query-eval serve` that boots the API

### Non-Goals

- **No frontend.** A-Plus.2 is the next phase.
- **No multi-user / SSO / per-user identity.** The single-user model uses the existing `~/.config/goldens/identity.toml` for actor.
- **No background jobs / job queue.** Synthesise streams sync; YAGNI for solo MVP.
- **No WebSockets.** NDJSON streaming via HTTP chunked-transfer is sufficient.
- **No database.** The JSONL event log is the only data source.
- **No external network exposure.** Reverse proxies, tunnels, IT-clearance — separate phase.
- **No User-Signals (`signal_einverstanden` / `signal_disqualifiziert`).** Phase D.

## 3. Architecture

### 3.1 Process model

Foreground command `query-eval serve --port 8000`. Bound to `127.0.0.1`. Dies on SIGINT. No daemon, no systemd. User opens browser at `http://127.0.0.1:8000/docs` for Swagger UI; production-style frontend (A-Plus.2) hits `http://127.0.0.1:8000/api/...`.

### 3.2 State model

**Stateless.** Every request reads `outputs/<slug>/datasets/golden_events_v1.jsonl`, `outputs/<slug>/analyze/*.json`, `~/.config/goldens/identity.toml` fresh from disk. Concurrent CLI writes are serialized by A.3's `fcntl.LOCK_EX` in `append_event` / `append_events`. No in-process cache, no inotify watches, no shared state across requests.

For Tragkorb-scale (~9 elements, ~10s-100s entries) the per-request read cost is sub-millisecond. For 1000+ entry logs, in-memory caching with file-mtime invalidation may be added later — but it's not in scope.

### 3.3 Auth model

On startup, server reads `GOLDENS_API_TOKEN` from environment. If unset, server refuses to start with exit code 2.

Middleware checks `X-Auth-Token` header on every request matching `/api/*`. Missing or mismatched header → `401 {"detail": "missing or invalid X-Auth-Token"}`. The `/api/health` endpoint and the FastAPI-built-in `/docs` and `/openapi.json` paths are token-free (allowlisted).

`/docs` (Swagger UI) supports interactive Authorize via the standard "Authorize" button — feed the token once, all subsequent in-browser requests carry it.

### 3.4 Identity model

Server boots with one `Identity` (loaded via `goldens.creation.identity.load_identity()`). All `created` / `refined` / `deprecated` events written via the API use this Identity as the `HumanActor`. The token authenticates the *server itself*, not individual users — single-user MVP.

If `~/.config/goldens/identity.toml` is missing at boot, server refuses to start with a clear error: `"identity.toml missing — run query-eval curate once to bootstrap, or write the file manually."`

### 3.5 Boundary diagram

```
Browser/curl ──HTTP──▶ FastAPI(api/)
                          │
                          ├─ auth middleware
                          ├─ exception_handlers (Domain → HTTP)
                          ├─ routers/docs.py        ──▶ goldens.creation.{curate,synthetic}, AnalyzeJsonLoader
                          └─ routers/entries.py     ──▶ goldens.operations.{refine,deprecate}, projection
                                                          │
                                                          └─▶ goldens.storage (event log + locks)
                                                                  │
                                                                  └─▶ outputs/<slug>/datasets/*.jsonl
```

API-layer imports `creation`, `operations`, `storage`. These modules know nothing about HTTP. CLI continues to import the same modules — the API is the second caller of the same business logic.

## 4. URL Design

Mixed style: **element-centric** for the curate flow (matches the UI mockup in phases-overview line 200-221), **entry-centric** for entry edits.

### 4.1 Document/Element surface (slug-scoped)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/docs` | List available slugs (= subdirs of `outputs/` containing `analyze/*.json`) |
| `GET` | `/api/docs/{slug}/elements` | Element list for a doc, each enriched with `count_active_entries` for browser-progress display |
| `GET` | `/api/docs/{slug}/elements/{element_id}` | Single element + all active entries with `source_element.element_id == element_id` |
| `POST` | `/api/docs/{slug}/elements/{element_id}/entries` | Create a new entry from this element. Body: `CreateEntryRequest`. Returns: `CreateEntryResponse`. Internally calls `build_created_event` + `append_event` (analog A.4 curate) |
| `POST` | `/api/docs/{slug}/synthesise` | Streaming NDJSON. Body: `SynthesiseRequest`. Internally calls `synthesise_iter(...)` |

### 4.2 Entry surface (entry-id-scoped, slug-independent)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/entries` | List active entries. Query params: `?slug=<slug>`, `?source_element=<bare-id>`, `?include_deprecated=true` (default `false`) |
| `GET` | `/api/entries/{entry_id}` | Entry detail with refine-chain (`refines` / `refined_by` traversal) |
| `POST` | `/api/entries/{entry_id}/refine` | Wraps `goldens.operations.refine(...)`. Body: `RefineRequest`. Returns: `RefineResponse` |
| `POST` | `/api/entries/{entry_id}/deprecate` | Wraps `goldens.operations.deprecate(...)`. Body: `DeprecateRequest`. Returns: `DeprecateResponse` |

### 4.3 Server surface

| Method | Path | Purpose | Auth |
|---|---|---|---|
| `GET` | `/api/health` | `{status: "ok", goldens_root: "outputs"}` | none |
| `GET` | `/docs` | Swagger UI | none, but Authorize button for protected routes |
| `GET` | `/openapi.json` | OpenAPI schema | none |

### 4.4 Concrete Tragkorb examples

```http
GET /api/docs
→ 200  ["smoke-test-tragkorb"]

GET /api/docs/smoke-test-tragkorb/elements
→ 200  [
    {"element": {"element_id": "p1-da62cbad", "page_number": 1, "element_type": "heading",
                 "content": "Tragkorb B-147 — Technische Spezifikation", ...},
     "count_active_entries": 0},
    {"element": {"element_id": "p2-8e6e4a52", "page_number": 2, "element_type": "table",
                 "content": "Schraubentyp | Anzugs...", "table_dims": [4,3],
                 "table_full_content": "Schraubentyp | Anzugsdrehmoment | Norm\n..."},
     "count_active_entries": 2},
    ...
  ]

POST /api/docs/smoke-test-tragkorb/elements/p2-8e6e4a52/entries
     X-Auth-Token: <token>
     Content-Type: application/json
     {"query": "Welches Drehmoment für M10?"}
→ 201  {"entry_id": "e_abc123", "event_id": "ev_xyz789"}

POST /api/docs/smoke-test-tragkorb/synthesise
     X-Auth-Token: <token>
     Content-Type: application/json
     {"llm_model": "gpt-4o-mini", "dry_run": true, "max_questions_per_element": 3}
→ 200  Content-Type: application/x-ndjson
       {"type":"start","total_elements":9}
       {"type":"element","element_id":"p1-da62cbad","kept":0,"skipped_reason":"heading_too_short"}
       {"type":"element","element_id":"p2-8e6e4a52","kept":3,"tokens_estimated":234}
       ...
       {"type":"complete","events_written":18,"prompt_tokens_estimated":1834}
```

### 4.5 Design notes

- **No `/api/v1/` prefix** — solo MVP, frontend (A-Plus.2) lives in the same repo, lockstep updates. Versioning is YAGNI here.
- **No pagination** — Tragkorb has 9 elements; real docs ~100-200. Pagination adds complexity without benefit at this scale. Add when an actual doc exceeds 1000 elements.
- **`include_deprecated=false` default** — matches `iter_active_retrieval_entries` semantics from A.7.
- **Identity comes from token-resolved server-side**, not request body. Clients never set actor — server enforces from its boot-time loaded `Identity`.
- **`SynthesiseRequest` mirrors CLI args 1:1**: `llm_model`, `llm_base_url`, `dry_run`, `max_questions_per_element`, `max_prompt_tokens`, `prompt_template_version`, `temperature`, `start_from`, `limit`, `embedding_model`, `resume`. Same flags, same defaults.

## 5. Schema Strategy (Pattern A — Pydantic-native domain)

After the prerequisite migration PR, `goldens.schemas` exposes Pydantic BaseModels directly. The API layer reuses them and adds **only API-specific** Pydantic models for shapes that don't exist in the domain.

### 5.1 Reused domain models (no new code)

- `RetrievalEntry` → `response_model=RetrievalEntry` for `GET /api/entries/{entry_id}`
- `DocumentElement` → embedded in `ElementWithCounts` (Section 5.2) for element-listing
- `SourceElement`, `HumanActor`, `LLMActor`, `Actor` (discriminated union) → composed into `RetrievalEntry`

### 5.2 New API-specific schemas (`goldens/api/schemas.py`)

```python
# Request bodies
class CreateEntryRequest(BaseModel):
    query: str = Field(min_length=1)

class RefineRequest(BaseModel):
    query: str = Field(min_length=1)
    expected_chunk_ids: list[str] = []
    chunk_hashes: dict[str, str] = {}
    notes: str | None = None
    deprecate_reason: str | None = None

class DeprecateRequest(BaseModel):
    reason: str | None = None

class SynthesiseRequest(BaseModel):
    llm_model: str
    llm_base_url: str | None = None
    dry_run: bool = False
    max_questions_per_element: int = 20
    max_prompt_tokens: int = 8000
    prompt_template_version: str = "v1"
    temperature: float = 0.0
    start_from: str | None = None
    limit: int | None = None
    embedding_model: str | None = None
    resume: bool = False

# Aggregate views
class DocSummary(BaseModel):
    slug: str
    element_count: int

class ElementWithCounts(BaseModel):
    element: DocumentElement
    count_active_entries: int

# Response wrappers
class CreateEntryResponse(BaseModel):
    entry_id: str
    event_id: str

class RefineResponse(BaseModel):
    new_entry_id: str

class DeprecateResponse(BaseModel):
    event_id: str

class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    goldens_root: str

# Synthesise streaming lines (NDJSON)
class SynthStartLine(BaseModel):
    type: Literal["start"] = "start"
    total_elements: int

class SynthElementLine(BaseModel):
    type: Literal["element"] = "element"
    element_id: str
    kept: int
    skipped_reason: str | None = None
    tokens_estimated: int = 0

class SynthCompleteLine(BaseModel):
    type: Literal["complete"] = "complete"
    events_written: int
    prompt_tokens_estimated: int

class SynthErrorLine(BaseModel):
    type: Literal["error"] = "error"
    element_id: str | None = None  # None = global / non-element-bound
    reason: str

SynthLine = Annotated[
    SynthStartLine | SynthElementLine | SynthCompleteLine | SynthErrorLine,
    Field(discriminator="type"),
]
```

Total: ~13 small Pydantic models, ~80 LOC. No mirror code, no adapters.

## 6. Streaming Protocol (Synthesise)

### 6.1 Wire format

`Content-Type: application/x-ndjson`. Each NDJSON line is one `SynthLine` (discriminated union, Section 5.2). `Transfer-Encoding: chunked` — no `Content-Length`.

### 6.2 Line ordering

1. Exactly one `SynthStartLine` first (with `total_elements`).
2. Zero or more `SynthElementLine` (one per yielded element, includes both kept and skipped elements).
3. Zero or more `SynthErrorLine` interleaved with element lines (mid-stream errors don't abort the stream).
4. Exactly one `SynthCompleteLine` last.

If a fatal error occurs before any work happens (e.g., `SlugResolutionError`), the response is **not** a stream — it's a regular `404 / 422 / 500` JSON response from the exception handler.

### 6.3 Server-generator pattern

```python
@router.post("/api/docs/{slug}/synthesise")
async def synthesise_endpoint(slug: str, req: SynthesiseRequest):
    elements = AnalyzeJsonLoader(slug).elements()  # may raise → 404 via handler

    async def generate():
        yield (SynthStartLine(total_elements=len(elements)).model_dump_json() + "\n")
        try:
            for elem, result in synthesise_iter(slug, req, elements):
                yield (SynthElementLine(...).model_dump_json() + "\n")
        except Exception as e:
            yield (SynthErrorLine(reason=str(e)).model_dump_json() + "\n")
        finally:
            yield (SynthCompleteLine(...).model_dump_json() + "\n")

    return StreamingResponse(generate(), media_type="application/x-ndjson")
```

### 6.4 Required A.5 refactor

Current `goldens.creation.synthetic.synthesise(...)` returns a `SynthesiseResult` after walking all elements. For streaming we need a generator variant that yields per-element while persisting events as it goes. Spec:

```python
def synthesise_iter(
    *, slug, loader, client, embed_client, model, ...
) -> Iterator[tuple[DocumentElement, ElementResult]]:
    """Same signature as synthesise(...) but yields per element.
    
    Each yielded `ElementResult` carries: kept (int), skipped_reason (str | None),
    tokens_estimated (int). Events are appended to the log before yield, so a
    cancellation mid-iteration leaves a consistent log state.
    """
```

The existing `synthesise(...)` is rewritten as a thin wrapper around `synthesise_iter` that consumes the iterator and aggregates results. Both expose identical behaviour to existing callers; a new `synthesise_iter` is added for streaming consumers.

This refactor is **part of the A-Plus.1 PR**, not a separate PR — the streaming endpoint is meaningless without it.

### 6.5 Connection-drop handling

FastAPI's `StreamingResponse` cancels the generator on client disconnect by raising `GeneratorExit`. The generator's `try/finally` ensures the final `SynthCompleteLine` is *not* yielded on cancellation, but already-appended events stay in the log (each `append_event` is atomic + locked). Resume via `--resume` (in `SynthesiseRequest`) works as in CLI.

## 7. Error Handling

| Class | HTTP status | Body shape | Where mapped |
|---|---|---|---|
| Pydantic validation (request body) | `422` | `{"detail": [{"loc":..., "msg":..., "type":...}]}` | FastAPI built-in |
| `EntryNotFoundError` | `404` | `{"detail": "<msg>"}` | `@app.exception_handler` |
| `SlugResolutionError` | `404` | `{"detail": "<msg>"}` | `@app.exception_handler` |
| `EntryDeprecatedError` | `409` | `{"detail": "<msg>"}` | `@app.exception_handler` |
| `StartResolutionError` (during synthesise) | yielded as `SynthErrorLine` | (mid-stream) | generator |
| Auth missing/invalid | `401` | `{"detail": "missing or invalid X-Auth-Token"}` | middleware |
| Anything else (uncaught) | `500` | `{"detail": "internal server error"}` | FastAPI default |

Custom exception-handlers live in `goldens/api/app.py`. They use FastAPI's `JSONResponse` with the existing `{"detail": ...}` shape — no custom error envelope, no RFC7807 (would be over-engineering for solo MVP).

## 8. Configuration

`goldens/api/config.py`:

```python
class ApiConfig(BaseSettings):
    api_token: str                                # required, no default
    data_root: Path = Path("outputs")             # cwd-relative
    log_level: Literal["debug","info","warning","error"] = "info"

    model_config = SettingsConfigDict(env_prefix="GOLDENS_")
    # GOLDENS_API_TOKEN, GOLDENS_DATA_ROOT, GOLDENS_LOG_LEVEL
```

CLI command for boot:

```python
# In query_index_eval/cli.py
p_serve = sub.add_parser("serve", help="Run the goldens HTTP API on 127.0.0.1")
p_serve.add_argument("--port", type=int, default=8000)
p_serve.add_argument("--host", default="127.0.0.1")
p_serve.add_argument("--reload", action="store_true")
p_serve.set_defaults(func=cmd_serve)

def cmd_serve(args):
    if not os.environ.get("GOLDENS_API_TOKEN"):
        print("ERROR: GOLDENS_API_TOKEN env var is required", file=sys.stderr)
        return 2
    import uvicorn
    from goldens.api.app import create_app
    uvicorn.run(create_app(), host=args.host, port=args.port, reload=args.reload, log_level="info")
    return 0
```

## 9. Module Layout

```
features/goldens/src/goldens/
├── api/                                   ← NEW
│   ├── __init__.py                        re-export create_app
│   ├── app.py                             FastAPI factory, exception_handlers, lifespan, middleware mount
│   ├── auth.py                            X-Auth-Token middleware
│   ├── config.py                          ApiConfig (Pydantic Settings)
│   ├── identity.py                        load identity at boot, expose as dep-injection
│   ├── schemas.py                         API-only Pydantic models (Section 5.2)
│   └── routers/
│       ├── __init__.py
│       ├── docs.py                        slug-scoped routes
│       └── entries.py                     entry-id-scoped routes
├── creation/
│   ├── synthetic.py                       ← MODIFIED: add `synthesise_iter()` generator
│   └── (others unchanged)
├── operations/                            ← UNCHANGED
├── schemas/                               ← Pydantic-migrated (prerequisite PR)
└── storage/                               ← Pydantic-callsite-updated (prerequisite PR)

features/goldens/tests/
├── test_api_auth.py
├── test_api_app.py
├── test_api_routers_docs.py
├── test_api_routers_entries.py
├── test_api_streaming_synthesise.py
├── test_api_concurrency_cli_vs_api.py
└── conftest.py                            ← extended with api-app + token + tmp-events fixtures

features/evaluators/chunk_match/src/query_index_eval/
└── cli.py                                 ← MODIFIED: + `serve` sub-command
```

## 10. Test Strategy

### 10.1 Per-area coverage

| Area | What's tested | Style |
|---|---|---|
| Auth middleware | missing token → 401, wrong token → 401, valid token → handler reached, `/api/health` and `/docs` token-free | httpx + tmp env |
| Endpoint happy paths | every endpoint with realistic body → 200/201/202 | httpx + in-process FastAPI + tmp_path event log |
| Endpoint error paths | per domain exception → mapped HTTP status with detail | httpx + assert on status_code + detail substring |
| Streaming endpoint | Tragkorb 9-element fixture in dry-run → start + 9 elements + complete; mid-stream error injection → SynthErrorLine + complete; client-disconnect → no orphan events | httpx streaming iterator |
| CLI/API concurrency | CLI `query-eval refine` while API serves a request → A.3 lock sequences both, both events land in log deterministically | subprocess + httpx parallel |

### 10.2 Fixtures (in `conftest.py`)

```python
@pytest.fixture
def goldens_root(tmp_path: Path) -> Path:
    """Tmp outputs/-tree with a copy of the Tragkorb fixture and seeded identity.toml."""

@pytest.fixture
def api_token() -> str:
    return "test-token-not-secret"

@pytest.fixture
def app(goldens_root: Path, api_token: str, monkeypatch) -> FastAPI:
    monkeypatch.setenv("GOLDENS_API_TOKEN", api_token)
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(goldens_root))
    from goldens.api.app import create_app
    return create_app()

@pytest.fixture
def client(app: FastAPI, api_token: str) -> httpx.Client:
    return httpx.Client(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Auth-Token": api_token},
    )
```

### 10.3 Out of scope for tests

- Real LLM calls in synthesise streaming test — `dry_run=True` only. Real LLM tests live in `test_creation_synthetic_respx.py` (existing).
- Browser/frontend — A-Plus.2.
- Cross-platform locking edge cases — A.3 tests cover, API inherits.
- Performance / load — solo-user MVP.

### 10.4 Coverage target

`features/goldens/pyproject.toml` has `fail-under=70`. Goldens-suite-coverage post-A-Plus.1 should hit 95%+. The streaming generator's `except GeneratorExit` branch is hard to test deterministically — accept `# pragma: no cover` for that one line.

## 11. Decision Log

| # | Topic | Decision | Why |
|---|---|---|---|
| AP1.1 | User scope (Day 1) | Single user (yourself); auth via static `GOLDENS_API_TOKEN` env var | No multi-user need yet; keeps MVP scope small; deferred IT/DSGVO clearance |
| AP1.2 | A.4-A.6 surface in API | All three (curate, refine/deprecate, synthesise sync) | Full feature parity with CLI; chose against MVP-with-only-curate to avoid second migration |
| AP1.3 | CLI vs API co-existence | A — both write to same files via A.3 locking | Zero migration cost; CLI stays useful for power-user tasks; locking already implemented |
| AP1.4 | Synthesise progress UX | B — Streaming NDJSON | Sweet spot between sync-block (poor UX) and async-job (heavy infra); no job state to manage |
| AP1.5 | Schema strategy | A — Pydantic-native domain via prerequisite migration PR | Single source of truth; no mirror drift; matches Microsoft Python conventions; Pattern C (dataclass + FastAPI auto-convert) rejected because Pydantic-migration is inevitable for Phase B (LLM-Judge) anyway and doing it now keeps A-Plus.1 cleaner |
| AP1.6 | URL design | Mixed — element-centric for curate, entry-centric for operations | Matches UI mockup; entry IDs are global (no slug needed for refine/deprecate) |
| AP1.7 | Versioning prefix | None (no `/api/v1/`) | Solo MVP, lockstep updates with frontend; YAGNI |
| AP1.8 | Pagination | None | Tragkorb 9 elements, real docs ~100-200; pagination at 1000+ is future work |
| AP1.9 | Error envelope | FastAPI default `{"detail": ...}` | No custom error format; fewer test cases; standard HTTP semantics |
| AP1.10 | Bind interface | `127.0.0.1` only | No outside exposure Day 1; reverse-proxy is separate phase |
| AP1.11 | Identity model | Server boots with one Identity from `~/.config/goldens/identity.toml`; token authenticates server, not user | Single-user; no per-request identity; reuses existing CLI identity bootstrap |

## 12. Out of Scope (explicit)

- Frontend — A-Plus.2
- User signals (Phase D)
- Multi-user / SSO — A-Plus.3 if/when Microsoft reviewers come on board
- Background job queue / WebSockets / database
- Network exposure (TLS, reverse proxy, tunnel) — separate concern
- Performance optimization / caching — premature

## 13. Verification Checklist

Before merging A-Plus.1:

- [ ] Pydantic-Migration-PR merged first
- [ ] Full test suite green: `pytest features/goldens/tests features/evaluators/chunk_match/tests`
- [ ] Goldens-coverage ≥ 95%
- [ ] Ruff + mypy + format pre-commit hooks pass
- [ ] Manual smoke: `query-eval serve` starts; `curl http://127.0.0.1:8000/api/health` returns 200; `/docs` loads in browser; one happy-path entry created via `/docs` Authorize + Try-it-out flow
- [ ] Manual smoke: streaming synthesise on Tragkorb fixture in dry-run shows live progress lines
- [ ] CLI smoke: `query-eval curate --doc smoke-test-tragkorb` (interactive) still works alongside running server, both write events that land in the same log deterministically
