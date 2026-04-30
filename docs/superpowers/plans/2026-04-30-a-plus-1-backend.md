# A-Plus.1 FastAPI Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a FastAPI HTTP backend in `features/goldens/src/goldens/api/` that exposes A.4-A.6 (curate, refine, deprecate, synthesise streaming) over HTTP, plus a new CLI sub-command `query-eval serve` to start it.

**Architecture:** Stateless single-process server bound to `127.0.0.1`. Pydantic-native domain (already migrated in PR #22) is exposed directly via `response_model=` — no mirror layer. Static `X-Auth-Token` middleware. NDJSON streaming for the long-running synthesise endpoint. Concurrency with the CLI is handled by A.3's existing `fcntl.LOCK_EX` on the event log.

**Tech Stack:** Python 3.11+ · FastAPI ≥ 0.110 · Pydantic v2 · pydantic-settings 2 · uvicorn 0.27+ · pytest · httpx · pytest-cov · existing `goldens` package layout.

**Spec:** `docs/superpowers/specs/2026-04-30-a-plus-1-backend-design.md`
**Prerequisite:** Pydantic-migration PR #22 merged (already done — current main has Pydantic-native schemas).

---

## File Map

**Modified:**
- `features/goldens/pyproject.toml` — add `fastapi`, `pydantic-settings`, `uvicorn[standard]`, plus `httpx` test-dep
- `features/goldens/src/goldens/creation/synthetic.py` — add new `synthesise_iter()` generator alongside existing `synthesise()`; the latter becomes a thin wrapper
- `features/evaluators/chunk_match/src/query_index_eval/cli.py` — add `serve` subparser + `cmd_serve` handler

**Created (production):**
- `features/goldens/src/goldens/api/__init__.py` — re-export `create_app`
- `features/goldens/src/goldens/api/app.py` — FastAPI factory, exception handlers, lifespan
- `features/goldens/src/goldens/api/auth.py` — X-Auth-Token middleware
- `features/goldens/src/goldens/api/config.py` — `ApiConfig` (pydantic-settings)
- `features/goldens/src/goldens/api/identity.py` — boot-time identity loader
- `features/goldens/src/goldens/api/schemas.py` — API-only Pydantic models (request bodies, aggregate views, streaming lines)
- `features/goldens/src/goldens/api/routers/__init__.py` — empty
- `features/goldens/src/goldens/api/routers/docs.py` — `/api/docs[/...]` routes + synthesise streaming
- `features/goldens/src/goldens/api/routers/entries.py` — `/api/entries[/...]` routes

**Created (tests):**
- `features/goldens/tests/test_api_schemas.py` — Pydantic model validation
- `features/goldens/tests/test_api_config.py` — env-var loading
- `features/goldens/tests/test_api_identity.py` — identity boot-loader
- `features/goldens/tests/test_api_auth.py` — middleware behaviour
- `features/goldens/tests/test_api_app.py` — health + exception handlers
- `features/goldens/tests/test_api_routers_docs.py` — slug/element endpoints + create-entry
- `features/goldens/tests/test_api_routers_entries.py` — list/get/refine/deprecate
- `features/goldens/tests/test_api_streaming_synthesise.py` — NDJSON streaming
- `features/goldens/tests/test_api_concurrency.py` — CLI vs API parallel writes
- `features/goldens/tests/test_synthesise_iter.py` — new generator semantics

---

## Task 1: Add FastAPI dependencies

**Files:**
- Modify: `features/goldens/pyproject.toml`

- [ ] **Step 1: Read current dependencies block**

Run: `grep -A8 "^dependencies =" features/goldens/pyproject.toml`

Expected: shows `pydantic`, `pysbd`, `pytest-cov`, `tiktoken`.

- [ ] **Step 2: Append new deps**

Edit `features/goldens/pyproject.toml`. Replace the dependencies block:

```toml
dependencies = [
    "pydantic>=2.5,<3",
    "pysbd>=0.3,<0.4",
    "pytest-cov>=7.1.0",
    "tiktoken>=0.7",
]
```

with:

```toml
dependencies = [
    "fastapi>=0.110,<1.0",
    "pydantic>=2.5,<3",
    "pydantic-settings>=2.0,<3",
    "pysbd>=0.3,<0.4",
    "pytest-cov>=7.1.0",
    "tiktoken>=0.7",
    "uvicorn[standard]>=0.27,<1.0",
]
```

Also extend the test-extra:

```toml
[project.optional-dependencies]
test = ["pytest", "pytest-cov", "respx>=0.21", "httpx>=0.25"]
```

- [ ] **Step 3: Reinstall the package**

Run: `source .venv/bin/activate && uv pip install -e features/goldens`

Expected: install succeeds; `fastapi`, `pydantic-settings`, `uvicorn` are fetched.

- [ ] **Step 4: Verify imports**

Run:
```bash
source .venv/bin/activate && python -c "import fastapi; import pydantic_settings; import uvicorn; print(fastapi.__version__, pydantic_settings.__version__, uvicorn.__version__)"
```

Expected: prints versions, no ImportError.

- [ ] **Step 5: Run the existing test suite to confirm no regression**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests 2>&1 | tail -3`

Expected: same passing count as before, coverage unchanged.

- [ ] **Step 6: Commit**

```bash
git add features/goldens/pyproject.toml
PATH="$PWD/.venv/bin:$PATH" git commit -m "deps(goldens): add fastapi/uvicorn/pydantic-settings/httpx for A-Plus.1 backend"
```

---

## Task 2: Skeleton the api/ module + re-export

**Files:**
- Create: `features/goldens/src/goldens/api/__init__.py`
- Create: `features/goldens/src/goldens/api/routers/__init__.py`

- [ ] **Step 1: Create `features/goldens/src/goldens/api/__init__.py`**

```python
"""HTTP API for goldens. See docs/superpowers/specs/2026-04-30-a-plus-1-backend-design.md."""

from __future__ import annotations

# create_app is implemented in app.py (Task 6); we forward-declare here so callers
# can `from goldens.api import create_app`.

__all__ = ["create_app"]


def create_app(*args, **kwargs):  # noqa: D401 — re-exported in app.py
    """Lazy proxy. Real implementation in goldens.api.app.create_app."""
    from goldens.api.app import create_app as real_create_app

    return real_create_app(*args, **kwargs)
```

- [ ] **Step 2: Create `features/goldens/src/goldens/api/routers/__init__.py`**

```python
"""Router modules for the goldens HTTP API."""
```

- [ ] **Step 3: Verify package imports**

Run: `source .venv/bin/activate && python -c "from goldens.api import create_app; print('ok')"`

Expected: `ok` (the lazy proxy raises on call, but import works).

- [ ] **Step 4: Commit**

```bash
git add features/goldens/src/goldens/api/__init__.py features/goldens/src/goldens/api/routers/__init__.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): scaffold api/ module with lazy create_app re-export"
```

---

## Task 3: API-only Pydantic schemas

**Files:**
- Create: `features/goldens/src/goldens/api/schemas.py`
- Create: `features/goldens/tests/test_api_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_schemas.py
"""Validation tests for API-only Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_create_entry_request_requires_non_empty_query() -> None:
    from goldens.api.schemas import CreateEntryRequest

    with pytest.raises(ValidationError):
        CreateEntryRequest(query="")
    assert CreateEntryRequest(query="Was ist X?").query == "Was ist X?"


def test_synthesise_request_defaults() -> None:
    from goldens.api.schemas import SynthesiseRequest

    req = SynthesiseRequest(llm_model="gpt-4o-mini")
    assert req.dry_run is False
    assert req.max_questions_per_element == 20
    assert req.max_prompt_tokens == 8000
    assert req.prompt_template_version == "v1"
    assert req.temperature == 0.0
    assert req.start_from is None
    assert req.limit is None
    assert req.embedding_model is None
    assert req.resume is False


def test_synthesise_request_round_trip_keeps_values() -> None:
    from goldens.api.schemas import SynthesiseRequest

    req = SynthesiseRequest(
        llm_model="gpt-4o-mini",
        dry_run=True,
        max_questions_per_element=5,
        start_from="p1-aaa",
    )
    assert req.dry_run is True
    assert req.max_questions_per_element == 5
    assert req.start_from == "p1-aaa"


def test_synth_line_discriminator_dispatches_correctly() -> None:
    from pydantic import TypeAdapter

    from goldens.api.schemas import (
        SynthCompleteLine,
        SynthElementLine,
        SynthErrorLine,
        SynthLine,
        SynthStartLine,
    )

    adapter: TypeAdapter[
        SynthStartLine | SynthElementLine | SynthCompleteLine | SynthErrorLine
    ] = TypeAdapter(SynthLine)
    assert isinstance(adapter.validate_python({"type": "start", "total_elements": 5}), SynthStartLine)
    assert isinstance(
        adapter.validate_python(
            {
                "type": "element",
                "element_id": "p1-aaa",
                "kept": 3,
                "skipped_reason": None,
                "tokens_estimated": 30,
            }
        ),
        SynthElementLine,
    )
    assert isinstance(
        adapter.validate_python({"type": "error", "element_id": "p1-aaa", "reason": "rate-limit"}),
        SynthErrorLine,
    )
    assert isinstance(
        adapter.validate_python({"type": "complete", "events_written": 9, "prompt_tokens_estimated": 1234}),
        SynthCompleteLine,
    )


def test_element_with_counts_composes_document_element() -> None:
    from goldens.api.schemas import ElementWithCounts
    from goldens.creation.elements.adapter import DocumentElement

    el = DocumentElement(
        element_id="p1-aaa",
        page_number=1,
        element_type="paragraph",
        content="Body.",
    )
    wrap = ElementWithCounts(element=el, count_active_entries=2)
    dumped = wrap.model_dump(mode="json")
    assert dumped["element"]["element_id"] == "p1-aaa"
    assert dumped["count_active_entries"] == 2


def test_health_response_default() -> None:
    from goldens.api.schemas import HealthResponse

    h = HealthResponse(goldens_root="outputs")
    assert h.status == "ok"
    assert h.goldens_root == "outputs"
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_schemas.py -v`

Expected: ImportError on `goldens.api.schemas`.

- [ ] **Step 3: Implement `features/goldens/src/goldens/api/schemas.py`**

```python
"""API-only Pydantic models. Domain models live in goldens.schemas (Pydantic
since PR #22) and are exposed by the routers directly via response_model=."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from goldens.creation.elements.adapter import DocumentElement


# ─── Request bodies ─────────────────────────────────────────────────────


class CreateEntryRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    query: str = Field(min_length=1)


class RefineRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    query: str = Field(min_length=1)
    expected_chunk_ids: list[str] = []
    chunk_hashes: dict[str, str] = {}
    notes: str | None = None
    deprecate_reason: str | None = None


class DeprecateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    reason: str | None = None


class SynthesiseRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
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


# ─── Aggregate views (no domain equivalent) ─────────────────────────────


class DocSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    element_count: int


class ElementWithCounts(BaseModel):
    model_config = ConfigDict(frozen=True)
    element: DocumentElement
    count_active_entries: int


# ─── Response wrappers ──────────────────────────────────────────────────


class CreateEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    entry_id: str
    event_id: str


class RefineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    new_entry_id: str


class DeprecateResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["ok"] = "ok"
    goldens_root: str


# ─── Synthesise streaming (NDJSON line types, discriminated union) ──────


class SynthStartLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["start"] = "start"
    total_elements: int


class SynthElementLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["element"] = "element"
    element_id: str
    kept: int
    skipped_reason: str | None = None
    tokens_estimated: int = 0


class SynthCompleteLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["complete"] = "complete"
    events_written: int
    prompt_tokens_estimated: int


class SynthErrorLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["error"] = "error"
    element_id: str | None = None
    reason: str


SynthLine = Annotated[
    SynthStartLine | SynthElementLine | SynthCompleteLine | SynthErrorLine,
    Field(discriminator="type"),
]
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_schemas.py -v`

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/schemas.py features/goldens/tests/test_api_schemas.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): API-only Pydantic schemas (requests, aggregates, streaming)"
```

---

## Task 4: ApiConfig (env-var settings)

**Files:**
- Create: `features/goldens/src/goldens/api/config.py`
- Create: `features/goldens/tests/test_api_config.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_config.py
from __future__ import annotations

from pathlib import Path

import pytest


def test_api_config_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GOLDENS_LOG_LEVEL", "debug")
    from goldens.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.api_token == "tok-test"
    assert cfg.data_root == tmp_path / "outputs"
    assert cfg.log_level == "debug"


def test_api_config_default_data_root_and_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.delenv("GOLDENS_DATA_ROOT", raising=False)
    monkeypatch.delenv("GOLDENS_LOG_LEVEL", raising=False)
    from goldens.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.data_root == Path("outputs")
    assert cfg.log_level == "info"


def test_api_config_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOLDENS_API_TOKEN", raising=False)
    from goldens.api.config import ApiConfig
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ApiConfig()
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_config.py -v`

Expected: ImportError.

- [ ] **Step 3: Implement `features/goldens/src/goldens/api/config.py`**

```python
"""Runtime config sourced from `GOLDENS_*` env vars (via pydantic-settings).

Loaded once when create_app() builds the FastAPI instance; tests override
via monkeypatch.setenv before instantiating.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GOLDENS_", extra="ignore")

    api_token: str = Field(min_length=1)
    data_root: Path = Path("outputs")
    log_level: Literal["debug", "info", "warning", "error"] = "info"
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_config.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/config.py features/goldens/tests/test_api_config.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): ApiConfig pulls GOLDENS_API_TOKEN/DATA_ROOT/LOG_LEVEL from env"
```

---

## Task 5: Identity loader (boot-time)

**Files:**
- Create: `features/goldens/src/goldens/api/identity.py`
- Create: `features/goldens/tests/test_api_identity.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_identity.py
from __future__ import annotations

from pathlib import Path

import pytest


def _seed_identity(tmp_xdg: Path, pseudonym: str = "alice", level: str = "phd") -> None:
    cfg = tmp_xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        f'schema_version = 1\npseudonym = "{pseudonym}"\nlevel = "{level}"\n'
        f'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def test_load_or_fail_returns_identity_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _seed_identity(tmp_path)
    from goldens.api.identity import load_or_fail

    ident = load_or_fail()
    assert ident.pseudonym == "alice"
    assert ident.level == "phd"


def test_load_or_fail_raises_on_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from goldens.api.identity import load_or_fail, IdentityNotConfigured

    with pytest.raises(IdentityNotConfigured, match="identity.toml"):
        load_or_fail()
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_identity.py -v`

- [ ] **Step 3: Implement `features/goldens/src/goldens/api/identity.py`**

```python
"""Boot-time identity loading for the API.

The API uses ONE identity for all event-writing — the curator running the
server. Fail loud if no identity.toml exists; the user must run
`query-eval curate` once first to bootstrap, or write the file manually.
"""

from __future__ import annotations

from goldens.creation.identity import Identity, load_identity


class IdentityNotConfigured(RuntimeError):
    """Raised at server boot when ~/.config/goldens/identity.toml is absent."""


def load_or_fail() -> Identity:
    ident = load_identity()
    if ident is None:
        raise IdentityNotConfigured(
            "identity.toml missing — run `query-eval curate` once to bootstrap, "
            "or write ~/.config/goldens/identity.toml manually."
        )
    return ident
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_identity.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/identity.py features/goldens/tests/test_api_identity.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): boot-time identity loader (fail loud if absent)"
```

---

## Task 6: Auth middleware (X-Auth-Token)

**Files:**
- Create: `features/goldens/src/goldens/api/auth.py`
- Create: `features/goldens/tests/test_api_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_auth.py
from __future__ import annotations

import pytest


def test_auth_middleware_allows_correct_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-good")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _protected() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-good"})
    assert resp.status_code == 200


def test_auth_middleware_rejects_missing_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _protected() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/protected")
    assert resp.status_code == 401
    assert "missing or invalid" in resp.json()["detail"].lower()


def test_auth_middleware_rejects_wrong_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _protected() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-bad"})
    assert resp.status_code == 401


def test_auth_middleware_lets_health_through() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/health")
    def _health() -> dict:
        return {"status": "ok"}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/health")  # no X-Auth-Token header
    assert resp.status_code == 200


def test_auth_middleware_lets_docs_through() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from goldens.api.auth import install_auth_middleware

    app = FastAPI()
    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    # /docs is built into FastAPI; the Swagger UI HTML must load without auth.
    resp = client.get("/docs")
    assert resp.status_code == 200
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_auth.py -v`

- [ ] **Step 3: Implement `features/goldens/src/goldens/api/auth.py`**

```python
"""X-Auth-Token middleware. Header-based static-token guard for /api/* paths.

Allowlisted (no token required):
- /api/health  — liveness probe
- /docs        — Swagger UI
- /openapi.json — schema
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


_ALLOWLIST = ("/api/health", "/docs", "/openapi.json", "/redoc")


def install_auth_middleware(app: FastAPI, *, token: str) -> None:
    """Register an HTTP middleware that requires `X-Auth-Token: <token>` on
    every `/api/*` path EXCEPT the allowlisted ones."""

    @app.middleware("http")
    async def _check_token(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path
        # Allowlisted paths: pass through unconditionally.
        if path in _ALLOWLIST or any(path.startswith(prefix + "/") for prefix in _ALLOWLIST):
            return await call_next(request)
        # Non-/api/ paths: pass through (FastAPI 404s them naturally).
        if not path.startswith("/api/"):
            return await call_next(request)
        sent = request.headers.get("X-Auth-Token")
        if not sent or sent != token:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid X-Auth-Token"},
            )
        return await call_next(request)
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_auth.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/auth.py features/goldens/tests/test_api_auth.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): X-Auth-Token middleware with /api/health and /docs allowlist"
```

---

## Task 7: App factory + health endpoint + exception handlers

**Files:**
- Create: `features/goldens/src/goldens/api/app.py`
- Create: `features/goldens/tests/test_api_app.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_app.py
from __future__ import annotations

from pathlib import Path

import pytest


def _seed_identity(xdg: Path, pseudonym: str = "alice") -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        f'schema_version = 1\npseudonym = "{pseudonym}"\nlevel = "phd"\n'
        f'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make() -> tuple:
        xdg = tmp_path / "xdg"
        xdg.mkdir()
        _seed_identity(xdg)
        outputs = tmp_path / "outputs"
        outputs.mkdir()
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
        monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))
        from goldens.api.app import create_app

        return create_app(), outputs

    return _make


def test_health_endpoint_returns_ok_without_auth(make_app) -> None:
    from fastapi.testclient import TestClient

    app, outputs = make_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["goldens_root"] == str(outputs)


def test_health_response_matches_schema(make_app) -> None:
    from fastapi.testclient import TestClient

    from goldens.api.schemas import HealthResponse

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    HealthResponse.model_validate(resp.json())


def test_unknown_path_returns_404(make_app) -> None:
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/nonexistent", headers={"X-Auth-Token": "tok-test"})
    assert resp.status_code == 404


def test_entry_not_found_error_maps_to_404(make_app) -> None:
    """Verify the exception handler chain for goldens domain errors."""
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    # Refining a missing entry — domain raises EntryNotFoundError.
    resp = client.post(
        "/api/entries/e_missing/refine",
        headers={"X-Auth-Token": "tok-test"},
        json={"query": "neue frage"},
    )
    assert resp.status_code == 404
    assert "e_missing" in resp.json()["detail"]


def test_missing_identity_raises_at_create_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg = tmp_path / "xdg"
    xdg.mkdir()
    # NO identity.toml seeded.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    from goldens.api.app import create_app
    from goldens.api.identity import IdentityNotConfigured

    with pytest.raises(IdentityNotConfigured):
        create_app()
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_app.py -v`

- [ ] **Step 3: Implement `features/goldens/src/goldens/api/app.py`**

```python
"""FastAPI app factory.

`create_app()` is the single entry point. It loads `ApiConfig` from env,
loads the boot-time Identity, registers exception handlers for goldens
domain errors, mounts the auth middleware, and includes the docs/entries
routers.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from goldens.api.auth import install_auth_middleware
from goldens.api.config import ApiConfig
from goldens.api.identity import load_or_fail
from goldens.api.schemas import HealthResponse
from goldens.creation.curate import SlugResolutionError, StartResolutionError
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError


def create_app() -> FastAPI:
    cfg = ApiConfig()
    identity = load_or_fail()  # raises IdentityNotConfigured if absent

    app = FastAPI(
        title="goldens-api",
        version="0.1.0",
        description="HTTP wrapper around goldens curate / refine / deprecate / synthesise.",
    )

    # Stash config + identity on app.state so routers can fetch them via Request.
    app.state.config = cfg
    app.state.identity = identity

    install_auth_middleware(app, token=cfg.api_token)

    # ─── Exception handlers (domain → HTTP) ──────────────────────────────

    @app.exception_handler(EntryNotFoundError)
    async def _entry_not_found(_request: Request, exc: EntryNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SlugResolutionError)
    async def _slug_unknown(_request: Request, exc: SlugResolutionError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(StartResolutionError)
    async def _start_unknown(_request: Request, exc: StartResolutionError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(EntryDeprecatedError)
    async def _entry_deprecated(_request: Request, exc: EntryDeprecatedError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def _file_not_found(_request: Request, exc: FileNotFoundError) -> JSONResponse:
        # AnalyzeJsonLoader raises FileNotFoundError when slug or analyze/ is missing.
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # ─── Routes ──────────────────────────────────────────────────────────

    @app.get("/api/health", response_model=HealthResponse)
    async def _health() -> HealthResponse:
        return HealthResponse(goldens_root=str(cfg.data_root))

    # Routers (Tasks 8+) attach via app.include_router(...) below.
    from goldens.api.routers.docs import router as docs_router
    from goldens.api.routers.entries import router as entries_router

    app.include_router(docs_router)
    app.include_router(entries_router)

    return app
```

- [ ] **Step 4: Add empty router stubs so app.py can import**

Add to `features/goldens/src/goldens/api/routers/docs.py`:
```python
"""Slug-scoped routes. Implemented in Tasks 8-10 + 12."""

from fastapi import APIRouter

router = APIRouter()
```

Add to `features/goldens/src/goldens/api/routers/entries.py`:
```python
"""Entry-id-scoped routes. Implemented in Tasks 13-16."""

from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 5: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_app.py -v`

Expected: 5 passed (entry-not-found test depends on entries router stub returning 404 — fix in Task 15).

If `test_entry_not_found_error_maps_to_404` still fails because the route doesn't exist yet, mark it `@pytest.mark.skip("router implemented in Task 15")` and unskip in Task 15.

- [ ] **Step 6: Commit**

```bash
git add features/goldens/src/goldens/api/app.py features/goldens/src/goldens/api/routers/docs.py features/goldens/src/goldens/api/routers/entries.py features/goldens/tests/test_api_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): FastAPI app factory with health + exception handlers + router stubs"
```

---

## Task 8: Docs router — list slugs

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/docs.py`
- Create: `features/goldens/tests/test_api_routers_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_routers_docs.py
from __future__ import annotations

from pathlib import Path

import pytest


def _seed_identity(xdg: Path) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "alice"\nlevel = "phd"\n'
        'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def _seed_doc(outputs: Path, slug: str, fixture_name: str = "analyze_minimal.json") -> None:
    import shutil

    src = Path(__file__).parent / "fixtures" / fixture_name
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


@pytest.fixture
def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))

    def _make() -> tuple[TestClient, Path]:
        from goldens.api.app import create_app

        client = TestClient(create_app())
        client.headers.update({"X-Auth-Token": "tok-test"})
        return client, outputs

    return _make


def test_list_docs_empty(make_client) -> None:
    client, _ = make_client()
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_docs_returns_doc_summary(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    _seed_doc(outputs, "doc-b")
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    body = resp.json()
    slugs = {d["slug"] for d in body}
    assert slugs == {"doc-a", "doc-b"}
    for d in body:
        assert d["element_count"] >= 1


def test_list_docs_skips_subdirs_without_analyze_json(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "real-doc")
    (outputs / "noisy-dir").mkdir()  # no analyze/
    resp = client.get("/api/docs")
    slugs = {d["slug"] for d in resp.json()}
    assert slugs == {"real-doc"}


def test_list_docs_requires_auth(make_client) -> None:
    client, _ = make_client()
    client.headers.pop("X-Auth-Token")
    resp = client.get("/api/docs")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py -v`

- [ ] **Step 3: Implement `features/goldens/src/goldens/api/routers/docs.py`**

```python
"""Slug-scoped routes:

- GET  /api/docs                                              — list slugs
- GET  /api/docs/{slug}/elements                              — element list (Task 9)
- GET  /api/docs/{slug}/elements/{element_id}                 — element detail (Task 10)
- POST /api/docs/{slug}/elements/{element_id}/entries         — create entry (Task 11)
- POST /api/docs/{slug}/synthesise                            — streaming (Task 13)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from goldens.api.schemas import DocSummary
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader

router = APIRouter()


@router.get("/api/docs", response_model=list[DocSummary])
async def list_docs(request: Request) -> list[DocSummary]:
    data_root: Path = request.app.state.config.data_root
    summaries: list[DocSummary] = []
    if not data_root.is_dir():
        return summaries
    for child in sorted(data_root.iterdir()):
        if not child.is_dir():
            continue
        analyze = child / "analyze"
        if not analyze.is_dir() or not any(analyze.glob("*.json")):
            continue
        loader = AnalyzeJsonLoader(child.name, outputs_root=data_root)
        elements = loader.elements()
        summaries.append(DocSummary(slug=child.name, element_count=len(elements)))
    return summaries
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/routers/docs.py features/goldens/tests/test_api_routers_docs.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): GET /api/docs lists slugs with element counts"
```

---

## Task 9: Docs router — list elements per slug

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/docs.py`
- Modify: `features/goldens/tests/test_api_routers_docs.py`

- [ ] **Step 1: Append test to `test_api_routers_docs.py`**

```python
def test_list_elements_returns_element_with_counts(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    resp = client.get("/api/docs/doc-a/elements")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    item = body[0]
    assert "element" in item
    assert "count_active_entries" in item
    assert item["element"]["element_id"]
    assert item["element"]["page_number"] >= 1


def test_list_elements_unknown_slug_404(make_client) -> None:
    client, _ = make_client()
    resp = client.get("/api/docs/nonexistent/elements")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py::test_list_elements_returns_element_with_counts tests/test_api_routers_docs.py::test_list_elements_unknown_slug_404 -v`

- [ ] **Step 3: Add the route + helper to `routers/docs.py`**

Append to `features/goldens/src/goldens/api/routers/docs.py`:

```python
from collections import defaultdict

from goldens.api.schemas import ElementWithCounts
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.projection import iter_active_retrieval_entries


def _count_entries_per_element(data_root: Path, slug: str) -> dict[str, int]:
    """Bare-element-id → number of active retrieval entries projected from the log."""
    log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    if not log.exists():
        return {}
    counts: dict[str, int] = defaultdict(int)
    for entry in iter_active_retrieval_entries(log):
        if entry.source_element is not None:
            counts[entry.source_element.element_id] += 1
    return counts


@router.get("/api/docs/{slug}/elements", response_model=list[ElementWithCounts])
async def list_elements(slug: str, request: Request) -> list[ElementWithCounts]:
    data_root: Path = request.app.state.config.data_root
    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()  # raises FileNotFoundError → 404 via app handler
    counts = _count_entries_per_element(data_root, slug)
    return [
        ElementWithCounts(
            element=el,
            count_active_entries=counts.get(el.element_id.split("-", 1)[1], 0),
        )
        for el in elements
    ]
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py -v`

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/routers/docs.py features/goldens/tests/test_api_routers_docs.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): GET /api/docs/{slug}/elements with active-entry counts"
```

---

## Task 10: Docs router — element detail (one element + its entries)

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/docs.py`
- Modify: `features/goldens/tests/test_api_routers_docs.py`

- [ ] **Step 1: Append test**

```python
def test_get_element_returns_element_and_entries(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    # First fetch the element list to learn an ID we can hit:
    elements = client.get("/api/docs/doc-a/elements").json()
    assert elements
    el_id = elements[0]["element"]["element_id"]
    resp = client.get(f"/api/docs/doc-a/elements/{el_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "element" in body and "entries" in body
    assert body["element"]["element_id"] == el_id
    assert isinstance(body["entries"], list)


def test_get_element_unknown_slug_404(make_client) -> None:
    client, _ = make_client()
    resp = client.get("/api/docs/nope/elements/p1-aaaaaaaa")
    assert resp.status_code == 404


def test_get_element_unknown_element_404(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    resp = client.get("/api/docs/doc-a/elements/p99-deadbeef")
    assert resp.status_code == 404
    assert "p99-deadbeef" in resp.json()["detail"]
```

- [ ] **Step 2: Run tests — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py -v`

- [ ] **Step 3: Add route to `routers/docs.py`**

```python
from typing import Any

from fastapi import HTTPException

from goldens.creation.elements.adapter import DocumentElement
from goldens.schemas.retrieval import RetrievalEntry


class ElementDetailResponse(BaseModel):
    """Used as response_model for GET /api/docs/{slug}/elements/{element_id}.

    Lives next to the route because it's purely an aggregate view of one
    element + its active entries.
    """
    model_config = ConfigDict(frozen=True)

    element: DocumentElement
    entries: list[RetrievalEntry]
```

Wait — `BaseModel` and `ConfigDict` aren't yet imported in `docs.py`. Add:

```python
from pydantic import BaseModel, ConfigDict
```

at the top of the file. Then the `ElementDetailResponse` class above goes near the top (after imports).

Now the route:

```python
@router.get(
    "/api/docs/{slug}/elements/{element_id}",
    response_model=ElementDetailResponse,
)
async def get_element(
    slug: str,
    element_id: str,
    request: Request,
) -> ElementDetailResponse:
    data_root: Path = request.app.state.config.data_root
    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()
    matching = next(
        (el for el in elements if el.element_id == element_id),
        None,
    )
    if matching is None:
        raise HTTPException(status_code=404, detail=f"element {element_id} not found in {slug}")

    log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    bare = element_id.split("-", 1)[1] if "-" in element_id else element_id
    entries: list[RetrievalEntry] = []
    if log.exists():
        for entry in iter_active_retrieval_entries(log):
            if entry.source_element is not None and entry.source_element.element_id == bare:
                entries.append(entry)

    return ElementDetailResponse(element=matching, entries=entries)
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py -v`

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/routers/docs.py features/goldens/tests/test_api_routers_docs.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): GET /api/docs/{slug}/elements/{element_id} with active entries"
```

---

## Task 11: Docs router — POST create entry

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/docs.py`
- Modify: `features/goldens/tests/test_api_routers_docs.py`

- [ ] **Step 1: Append test**

```python
def test_create_entry_writes_event(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]

    resp = client.post(
        f"/api/docs/doc-a/elements/{el_id}/entries",
        json={"query": "Was steht hier?"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["entry_id"]
    assert body["event_id"]

    # And the count goes up.
    after = client.get("/api/docs/doc-a/elements").json()
    matching = next(e for e in after if e["element"]["element_id"] == el_id)
    assert matching["count_active_entries"] >= 1


def test_create_entry_rejects_empty_query(make_client) -> None:
    client, outputs = make_client()
    _seed_doc(outputs, "doc-a")
    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]

    resp = client.post(
        f"/api/docs/doc-a/elements/{el_id}/entries",
        json={"query": ""},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests — expect failure**

- [ ] **Step 3: Add route to `routers/docs.py`**

```python
from fastapi import status as http_status

from goldens.api.schemas import CreateEntryRequest, CreateEntryResponse
from goldens.creation.curate import build_created_event
from goldens.storage import append_event


@router.post(
    "/api/docs/{slug}/elements/{element_id}/entries",
    response_model=CreateEntryResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_entry(
    slug: str,
    element_id: str,
    body: CreateEntryRequest,
    request: Request,
) -> CreateEntryResponse:
    data_root: Path = request.app.state.config.data_root
    identity = request.app.state.identity

    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()
    matching = next((el for el in elements if el.element_id == element_id), None)
    if matching is None:
        raise HTTPException(status_code=404, detail=f"element {element_id} not found in {slug}")

    event = build_created_event(
        question=body.query,
        element=matching,
        loader=loader,
        identity=identity,
    )
    log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    log.parent.mkdir(parents=True, exist_ok=True)
    append_event(log, event)

    return CreateEntryResponse(
        entry_id=event.entry_id,
        event_id=event.event_id,
    )
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_docs.py -v`

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/routers/docs.py features/goldens/tests/test_api_routers_docs.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): POST /api/docs/{slug}/elements/{eid}/entries creates event"
```

---

## Task 12: synthesise_iter() generator in goldens.creation.synthetic

**Files:**
- Modify: `features/goldens/src/goldens/creation/synthetic.py`
- Create: `features/goldens/tests/test_synthesise_iter.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_synthesise_iter.py
"""Generator semantics for the streaming variant of synthesise()."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest


def test_synthesise_iter_yields_per_element_in_dry_run(tmp_path: Path) -> None:
    """In dry-run mode, the generator yields a (DocumentElement, ElementResult)
    pair for every element seen — both kept and skipped — and never makes
    LLM calls."""
    import shutil

    from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
    from goldens.creation.synthetic import synthesise_iter

    fixtures = Path(__file__).parent / "fixtures"
    analyze = tmp_path / "doc-a" / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze / "ts.json")

    loader = AnalyzeJsonLoader("doc-a", outputs_root=tmp_path)

    yielded = list(
        synthesise_iter(
            slug="doc-a",
            loader=loader,
            client=None,
            embed_client=None,
            model="gpt-4o-mini",
            embedding_model=None,
            dry_run=True,
            events_path=tmp_path / "events.jsonl",
        )
    )
    assert len(yielded) >= 1
    for el, result in yielded:
        assert el.element_id
        # Either kept>=0 OR skipped_reason set; never both contradicting.
        assert result.kept >= 0
        assert result.tokens_estimated >= 0


def test_synthesise_wrapper_still_returns_summary(tmp_path: Path) -> None:
    """The original synthesise() function continues to return a SynthesiseResult
    (it now wraps synthesise_iter under the hood)."""
    import shutil

    from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
    from goldens.creation.synthetic import SynthesiseResult, synthesise

    fixtures = Path(__file__).parent / "fixtures"
    analyze = tmp_path / "doc-a" / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze / "ts.json")

    loader = AnalyzeJsonLoader("doc-a", outputs_root=tmp_path)
    result = synthesise(
        slug="doc-a",
        loader=loader,
        client=None,
        embed_client=None,
        model="gpt-4o-mini",
        embedding_model=None,
        dry_run=True,
        events_path=tmp_path / "events.jsonl",
    )
    assert isinstance(result, SynthesiseResult)
    assert result.dry_run is True
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_synthesise_iter.py -v`

- [ ] **Step 3: Refactor `features/goldens/src/goldens/creation/synthetic.py`**

This is a careful refactor. The existing `synthesise()` function has the loop body we need to extract. Strategy:

1. Add a small dataclass `ElementResult` next to `SynthesiseResult`:

Add near the top of the file (after `SynthesiseResult`):

```python
@dataclass(frozen=True)
class ElementResult:
    """Per-element outcome from one iteration of synthesise_iter()."""

    kept: int
    skipped_reason: str | None = None
    tokens_estimated: int = 0
```

2. Add the `synthesise_iter()` generator that yields per-element. The simplest implementation: copy the `synthesise()` body but replace the bookkeeping-into-counters with `yield (element, ElementResult(...))`. The existing `synthesise()` becomes a wrapper that consumes `synthesise_iter` and accumulates totals.

Add `synthesise_iter` (BEFORE the existing `synthesise` function definition):

```python
def synthesise_iter(
    *,
    slug: str,
    loader: ElementsLoader,
    client: LLMClient | None,
    embed_client: LLMClient | None,
    model: str,
    embedding_model: str | None,
    prompt_template_version: str = "v1",
    temperature: float = 0.0,
    max_questions_per_element: int = 20,
    max_prompt_tokens: int = 8000,
    start_from: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
    events_path: Path | None = None,
) -> Iterator[tuple[DocumentElement, ElementResult]]:
    """Streaming version of synthesise(). Yields per-element results so a
    streaming HTTP endpoint can emit progress as work happens. Events are
    appended to the log inside the loop, not buffered — a cancellation
    mid-iteration leaves the log consistent.

    See synthesise() for the wrapper that aggregates totals into a
    SynthesiseResult.
    """
    events_path = events_path or (Path("outputs") / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME)

    existing_keys: set[str] = set()
    if resume and events_path.exists():
        for ev in read_events(events_path):
            if ev.event_type != "created":
                continue
            entry_data = ev.payload.get("entry_data") or {}
            src = entry_data.get("source_element")
            if isinstance(src, dict):
                eid = src.get("element_id")
                if isinstance(eid, str):
                    existing_keys.add(eid)

    tokenizer = tiktoken.get_encoding("cl100k_base")
    dedup = QuestionDedup(
        client=embed_client,
        model=embedding_model or "",
        threshold=0.95,
    )

    started = start_from is None
    yielded = 0

    for element in loader.elements():
        if not started:
            if element.element_id == start_from:
                started = True
            else:
                continue
        if limit is not None and yielded >= limit:
            break
        yielded += 1

        bare_id = element.element_id.split("-", 1)[1]
        if resume and bare_id in existing_keys:
            yield element, ElementResult(kept=0, skipped_reason="resume_skip")
            continue

        sub_units = decompose_to_sub_units(element)
        if not sub_units:
            yield element, ElementResult(kept=0, skipped_reason="no_sub_units")
            continue

        template = _resolve_template_for(element, prompt_template_version)
        if template is None:
            yield element, ElementResult(kept=0, skipped_reason="no_template")
            continue

        if dry_run:
            rendered = _render_prompt(template, sub_units)
            tokens = len(tokenizer.encode(rendered))
            yield element, ElementResult(kept=0, tokens_estimated=tokens, skipped_reason="dry_run")
            continue

        existing_questions = _existing_questions_for(events_path, bare_id)

        if client is None:
            raise ValueError("synthesise_iter() requires `client` when dry_run=False")

        generated, model_version, tokens = _generate_question_batches(
            element,
            sub_units,
            client=client,
            model=model,
            template=template,
            temperature=temperature,
            max_prompt_tokens=max_prompt_tokens,
            tokenizer=tokenizer,
        )

        kept_questions = dedup.filter(
            generated,
            against=existing_questions,
            source_key=bare_id,
        )[:max_questions_per_element]

        kept_count = 0
        ts = now_utc_iso()
        actor = LLMActor(
            model=model,
            model_version=model_version,
            prompt_template_version=prompt_template_version,
            temperature=temperature,
        )
        for q in kept_questions:
            ev = build_synthesised_event(
                question=q,
                element=element,
                loader=loader,
                actor=actor,
                timestamp_utc=ts,
            )
            append_event(events_path, ev)
            kept_count += 1

        yield element, ElementResult(kept=kept_count, tokens_estimated=tokens)
```

Note: `Iterator`, `DocumentElement` need to be imported. Check the top of `synthetic.py`. If not present:

```python
from collections.abc import Iterator
from goldens.creation.elements.adapter import DocumentElement
```

Also `LLMActor`, `build_synthesised_event`, `now_utc_iso` need to already be imported. Verify with `grep`.

3. Replace the body of the existing `synthesise()` function with a wrapper:

```python
def synthesise(
    *,
    slug: str,
    loader: ElementsLoader,
    client: LLMClient | None,
    embed_client: LLMClient | None,
    model: str,
    embedding_model: str | None,
    prompt_template_version: str = "v1",
    temperature: float = 0.0,
    max_questions_per_element: int = 20,
    max_prompt_tokens: int = 8000,
    start_from: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    resume: bool = False,
    events_path: Path | None = None,
) -> SynthesiseResult:
    """Walk loader.elements(), generate questions, write events.

    Thin wrapper over synthesise_iter() — accumulates per-element results
    into a SynthesiseResult summary for non-streaming callers (CLI, tests)."""
    events_path = events_path or (Path("outputs") / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME)

    elements_seen = 0
    elements_skipped = 0
    elements_with_questions = 0
    questions_kept = 0
    prompt_tokens_estimated = 0

    for _el, result in synthesise_iter(
        slug=slug,
        loader=loader,
        client=client,
        embed_client=embed_client,
        model=model,
        embedding_model=embedding_model,
        prompt_template_version=prompt_template_version,
        temperature=temperature,
        max_questions_per_element=max_questions_per_element,
        max_prompt_tokens=max_prompt_tokens,
        start_from=start_from,
        limit=limit,
        dry_run=dry_run,
        resume=resume,
        events_path=events_path,
    ):
        elements_seen += 1
        if result.skipped_reason:
            elements_skipped += 1
        if result.kept > 0:
            elements_with_questions += 1
        questions_kept += result.kept
        prompt_tokens_estimated += result.tokens_estimated

    events_written = questions_kept if not dry_run else 0
    return SynthesiseResult(
        slug=slug,
        events_path=events_path,
        elements_seen=elements_seen,
        elements_skipped=elements_skipped,
        elements_with_questions=elements_with_questions,
        questions_generated=questions_kept,  # post-dedup approximation
        questions_kept=questions_kept,
        questions_dropped_dedup=0,
        questions_dropped_cap=0,
        events_written=events_written,
        prompt_tokens_estimated=prompt_tokens_estimated,
        dry_run=dry_run,
    )
```

This preserves the public CLI signature while exposing the new generator for streaming.

- [ ] **Step 4: Run tests — both new and existing must pass**

Run: `cd features/goldens && python -m pytest tests/test_synthesise_iter.py tests/test_creation_synthetic_respx.py -v`

Expected: new 2 tests pass, existing synthetic tests still pass.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/creation/synthetic.py features/goldens/tests/test_synthesise_iter.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "refactor(goldens/synthetic): factor out synthesise_iter() generator for streaming"
```

---

## Task 13: Synthesise streaming endpoint (NDJSON)

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/docs.py`
- Create: `features/goldens/tests/test_api_streaming_synthesise.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_streaming_synthesise.py
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


def _seed_identity(xdg: Path) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "alice"\nlevel = "phd"\n'
        'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def _seed_doc(outputs: Path, slug: str = "doc-a") -> None:
    src = Path(__file__).parent / "fixtures" / "analyze_minimal.json"
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


@pytest.fixture
def client_with_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))
    _seed_doc(outputs)
    from goldens.api.app import create_app

    client = TestClient(create_app())
    client.headers.update({"X-Auth-Token": "tok-test"})
    return client


def test_synthesise_dry_run_streams_ndjson(client_with_doc) -> None:
    with client_with_doc.stream(
        "POST",
        "/api/docs/doc-a/synthesise",
        json={"llm_model": "gpt-4o-mini", "dry_run": True},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        lines: list[dict] = []
        for line in resp.iter_lines():
            line = line.strip()
            if not line:
                continue
            lines.append(json.loads(line))

    assert len(lines) >= 3
    assert lines[0]["type"] == "start"
    assert lines[0]["total_elements"] >= 1
    assert lines[-1]["type"] == "complete"
    elements = [ln for ln in lines if ln["type"] == "element"]
    assert all(ln["kept"] == 0 for ln in elements)  # dry-run keeps nothing


def test_synthesise_unknown_slug_404(client_with_doc) -> None:
    resp = client_with_doc.post(
        "/api/docs/nope/synthesise",
        json={"llm_model": "gpt-4o-mini", "dry_run": True},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_streaming_synthesise.py -v`

- [ ] **Step 3: Add streaming endpoint to `routers/docs.py`**

Append to `routers/docs.py`:

```python
import json
from typing import AsyncIterator

from fastapi.responses import StreamingResponse

from goldens.api.schemas import (
    SynthCompleteLine,
    SynthElementLine,
    SynthErrorLine,
    SynthesiseRequest,
    SynthStartLine,
)
from goldens.creation.synthetic import synthesise_iter


@router.post("/api/docs/{slug}/synthesise")
async def synthesise_stream(
    slug: str,
    body: SynthesiseRequest,
    request: Request,
) -> StreamingResponse:
    data_root: Path = request.app.state.config.data_root

    # Resolve loader BEFORE starting the stream so a SlugUnknown raises a
    # clean 404 (the exception handler kicks in before any chunked transfer).
    loader = AnalyzeJsonLoader(slug, outputs_root=data_root)
    elements = loader.elements()  # raises FileNotFoundError → 404

    events_path = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME

    # Lazy-build the LLM client only when not in dry_run.
    completion_client = None
    embedding_model = body.embedding_model
    embed_client = None
    if not body.dry_run:
        from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig
        import os

        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            raise HTTPException(status_code=400, detail="LLM_API_KEY env var required for non-dry-run")
        base_url = body.llm_base_url or os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        completion_client = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=api_key, base_url=base_url),
        )
        # Embedding-client mirrors the CLI synthesise_cmd logic.
        openai_key = os.environ.get("OPENAI_API_KEY")
        if embedding_model and openai_key:
            embed_client = OpenAIDirectClient(
                OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1"),
            )
        elif openai_key and not embedding_model:
            embedding_model = "text-embedding-3-large"
            embed_client = OpenAIDirectClient(
                OpenAIDirectConfig(api_key=openai_key, base_url="https://api.openai.com/v1"),
            )

    async def _stream() -> AsyncIterator[bytes]:
        # SynthStartLine (with total)
        start = SynthStartLine(total_elements=len(elements))
        yield (start.model_dump_json() + "\n").encode("utf-8")

        events_written = 0
        prompt_tokens = 0
        try:
            for element, result in synthesise_iter(
                slug=slug,
                loader=loader,
                client=completion_client,
                embed_client=embed_client,
                model=body.llm_model,
                embedding_model=embedding_model,
                prompt_template_version=body.prompt_template_version,
                temperature=body.temperature,
                max_questions_per_element=body.max_questions_per_element,
                max_prompt_tokens=body.max_prompt_tokens,
                start_from=body.start_from,
                limit=body.limit,
                dry_run=body.dry_run,
                resume=body.resume,
                events_path=events_path,
            ):
                line = SynthElementLine(
                    element_id=element.element_id,
                    kept=result.kept,
                    skipped_reason=result.skipped_reason,
                    tokens_estimated=result.tokens_estimated,
                )
                events_written += result.kept
                prompt_tokens += result.tokens_estimated
                yield (line.model_dump_json() + "\n").encode("utf-8")
        except Exception as e:  # pragma: no cover (hard to test deterministically)
            err = SynthErrorLine(reason=str(e))
            yield (err.model_dump_json() + "\n").encode("utf-8")
        finally:
            done = SynthCompleteLine(
                events_written=events_written,
                prompt_tokens_estimated=prompt_tokens,
            )
            yield (done.model_dump_json() + "\n").encode("utf-8")

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_streaming_synthesise.py -v`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/routers/docs.py features/goldens/tests/test_api_streaming_synthesise.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): POST /api/docs/{slug}/synthesise streams NDJSON progress"
```

---

## Task 14: Entries router — list + get

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/entries.py`
- Create: `features/goldens/tests/test_api_routers_entries.py`

- [ ] **Step 1: Write the failing test**

```python
# features/goldens/tests/test_api_routers_entries.py
from __future__ import annotations

import shutil
from pathlib import Path

import pytest


def _seed_identity(xdg: Path) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "alice"\nlevel = "phd"\n'
        'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def _seed_doc(outputs: Path, slug: str = "doc-a") -> None:
    src = Path(__file__).parent / "fixtures" / "analyze_minimal.json"
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


@pytest.fixture
def client_with_one_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg)
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))
    _seed_doc(outputs)

    from goldens.api.app import create_app

    client = TestClient(create_app())
    client.headers.update({"X-Auth-Token": "tok-test"})

    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]
    create_resp = client.post(
        f"/api/docs/doc-a/elements/{el_id}/entries",
        json={"query": "Test-Frage 1"},
    )
    entry_id = create_resp.json()["entry_id"]
    return client, entry_id


def test_list_entries_returns_active(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    resp = client.get("/api/entries")
    assert resp.status_code == 200
    body = resp.json()
    assert any(e["entry_id"] == entry_id for e in body)


def test_list_entries_filter_by_slug(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.get("/api/entries?slug=doc-a")
    assert resp.status_code == 200
    body = resp.json()
    assert all(
        e["source_element"] is None
        or e["source_element"]["document_id"] == "doc-a"
        for e in body
    )


def test_get_entry_returns_full_object(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    resp = client.get(f"/api/entries/{entry_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entry_id"] == entry_id
    assert body["query"] == "Test-Frage 1"
    assert body["deprecated"] is False


def test_get_entry_unknown_404(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.get("/api/entries/e_does_not_exist")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test — expect failure**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_entries.py -v`

- [ ] **Step 3: Implement `routers/entries.py`**

Replace `features/goldens/src/goldens/api/routers/entries.py` with:

```python
"""Entry-id-scoped routes:

- GET  /api/entries                        — list active (filterable)
- GET  /api/entries/{entry_id}             — single
- POST /api/entries/{entry_id}/refine      — Task 15
- POST /api/entries/{entry_id}/deprecate   — Task 16
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from goldens.schemas.retrieval import RetrievalEntry
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.log import read_events
from goldens.storage.projection import build_state, iter_active_retrieval_entries

router = APIRouter()


def _walk_event_logs(data_root: Path) -> list[Path]:
    """Yield every existing golden_events_v1.jsonl across all slugs under data_root."""
    if not data_root.is_dir():
        return []
    return [
        p
        for p in (data_root.glob(f"*/datasets/{GOLDEN_EVENTS_V1_FILENAME}"))
        if p.is_file()
    ]


@router.get("/api/entries", response_model=list[RetrievalEntry])
async def list_entries(
    request: Request,
    slug: str | None = Query(default=None),
    source_element: str | None = Query(default=None),
    include_deprecated: bool = Query(default=False),
) -> list[RetrievalEntry]:
    data_root: Path = request.app.state.config.data_root
    entries: list[RetrievalEntry] = []

    if slug:
        log = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
        logs = [log] if log.exists() else []
    else:
        logs = _walk_event_logs(data_root)

    for log in logs:
        if include_deprecated:
            for entry in build_state(read_events(log)).values():
                entries.append(entry)
        else:
            for entry in iter_active_retrieval_entries(log):
                entries.append(entry)

    if source_element is not None:
        entries = [
            e
            for e in entries
            if e.source_element is not None and e.source_element.element_id == source_element
        ]
    return entries


@router.get("/api/entries/{entry_id}", response_model=RetrievalEntry)
async def get_entry(entry_id: str, request: Request) -> RetrievalEntry:
    data_root: Path = request.app.state.config.data_root
    for log in _walk_event_logs(data_root):
        state = build_state(read_events(log))
        if entry_id in state:
            return state[entry_id]
    raise HTTPException(status_code=404, detail=f"entry {entry_id} not found")
```

- [ ] **Step 4: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_entries.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add features/goldens/src/goldens/api/routers/entries.py features/goldens/tests/test_api_routers_entries.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): GET /api/entries and /api/entries/{id} with filters"
```

---

## Task 15: Entries router — refine

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/entries.py`
- Modify: `features/goldens/tests/test_api_routers_entries.py`

- [ ] **Step 1: Append test**

```python
def test_refine_creates_new_entry_and_deprecates_old(client_with_one_entry) -> None:
    client, old_entry_id = client_with_one_entry
    resp = client.post(
        f"/api/entries/{old_entry_id}/refine",
        json={"query": "Verbesserte Frage"},
    )
    assert resp.status_code == 200
    new_id = resp.json()["new_entry_id"]
    assert new_id != old_entry_id

    # Old is now deprecated; new is active.
    new_get = client.get(f"/api/entries/{new_id}")
    assert new_get.status_code == 200
    assert new_get.json()["query"] == "Verbesserte Frage"

    # Old is no longer in active list.
    active_ids = {e["entry_id"] for e in client.get("/api/entries").json()}
    assert old_entry_id not in active_ids


def test_refine_unknown_entry_404(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.post("/api/entries/e_missing/refine", json={"query": "x"})
    assert resp.status_code == 404


def test_refine_already_deprecated_entry_409(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    # Deprecate first.
    client.post(f"/api/entries/{entry_id}/deprecate", json={"reason": "test"})
    # Then try to refine.
    resp = client.post(f"/api/entries/{entry_id}/refine", json={"query": "x"})
    assert resp.status_code == 409
```

- [ ] **Step 2: Append the route to `routers/entries.py`**

```python
from goldens.api.schemas import RefineRequest, RefineResponse, DeprecateRequest, DeprecateResponse
from goldens.operations.errors import EntryNotFoundError
from goldens.operations.refine import refine as refine_op


@router.post("/api/entries/{entry_id}/refine", response_model=RefineResponse)
async def refine_entry(
    entry_id: str,
    body: RefineRequest,
    request: Request,
) -> RefineResponse:
    data_root: Path = request.app.state.config.data_root
    identity = request.app.state.identity

    # The refine() operation needs the path to the specific log. Since entries
    # live under one slug, we walk all logs and find which one contains this id.
    target_log: Path | None = None
    for log in _walk_event_logs(data_root):
        state = build_state(read_events(log))
        if entry_id in state:
            target_log = log
            break
    if target_log is None:
        raise EntryNotFoundError(entry_id)

    new_id = refine_op(
        target_log,
        entry_id,
        query=body.query,
        expected_chunk_ids=tuple(body.expected_chunk_ids),
        chunk_hashes=dict(body.chunk_hashes),
        actor=_human_actor_from_identity(identity),
        notes=body.notes,
        deprecate_reason=body.deprecate_reason,
    )
    return RefineResponse(new_entry_id=new_id)
```

Plus add the helper at the top of `routers/entries.py`:

```python
from goldens.creation.identity import Identity, identity_to_human_actor
from goldens.schemas import HumanActor


def _human_actor_from_identity(identity: Identity) -> HumanActor:
    return identity_to_human_actor(identity)
```

- [ ] **Step 3: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_entries.py -v`

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add features/goldens/src/goldens/api/routers/entries.py features/goldens/tests/test_api_routers_entries.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): POST /api/entries/{id}/refine wraps operations.refine"
```

---

## Task 16: Entries router — deprecate

**Files:**
- Modify: `features/goldens/src/goldens/api/routers/entries.py`
- Modify: `features/goldens/tests/test_api_routers_entries.py`

- [ ] **Step 1: Append test**

```python
def test_deprecate_marks_entry(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    resp = client.post(
        f"/api/entries/{entry_id}/deprecate",
        json={"reason": "duplicate"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_id"]

    # Entry is no longer in active list.
    active_ids = {e["entry_id"] for e in client.get("/api/entries").json()}
    assert entry_id not in active_ids

    # But shows up with include_deprecated=true.
    all_ids = {e["entry_id"] for e in client.get("/api/entries?include_deprecated=true").json()}
    assert entry_id in all_ids


def test_deprecate_already_deprecated_409(client_with_one_entry) -> None:
    client, entry_id = client_with_one_entry
    client.post(f"/api/entries/{entry_id}/deprecate", json={"reason": "first"})
    resp = client.post(f"/api/entries/{entry_id}/deprecate", json={"reason": "second"})
    assert resp.status_code == 409


def test_deprecate_unknown_404(client_with_one_entry) -> None:
    client, _ = client_with_one_entry
    resp = client.post("/api/entries/e_missing/deprecate", json={"reason": "x"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Append route**

```python
from goldens.operations.deprecate import deprecate as deprecate_op


@router.post("/api/entries/{entry_id}/deprecate", response_model=DeprecateResponse)
async def deprecate_entry(
    entry_id: str,
    body: DeprecateRequest,
    request: Request,
) -> DeprecateResponse:
    data_root: Path = request.app.state.config.data_root
    identity = request.app.state.identity

    target_log: Path | None = None
    for log in _walk_event_logs(data_root):
        state = build_state(read_events(log))
        if entry_id in state:
            target_log = log
            break
    if target_log is None:
        raise EntryNotFoundError(entry_id)

    event_id = deprecate_op(
        target_log,
        entry_id,
        actor=_human_actor_from_identity(identity),
        reason=body.reason,
    )
    return DeprecateResponse(event_id=event_id)
```

- [ ] **Step 3: Run tests**

Run: `cd features/goldens && python -m pytest tests/test_api_routers_entries.py -v`

Expected: 10 passed.

- [ ] **Step 4: Commit**

```bash
git add features/goldens/src/goldens/api/routers/entries.py features/goldens/tests/test_api_routers_entries.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(goldens/api): POST /api/entries/{id}/deprecate wraps operations.deprecate"
```

---

## Task 17: CLI — `query-eval serve` subcommand

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/cli.py`

- [ ] **Step 1: Locate the existing `main()` parser block**

Run: `grep -n "p_curate\|p_synth\|p_eval\|p_report\|sub.add_parser" features/evaluators/chunk_match/src/query_index_eval/cli.py | head -10`

Expected: shows the existing subparsers. Note the line where they're registered.

- [ ] **Step 2: Add the `serve` subparser + handler**

In `features/evaluators/chunk_match/src/query_index_eval/cli.py`, after the existing subparsers, add:

```python
    p_serve = sub.add_parser("serve", help="Run the goldens HTTP API on 127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")
    p_serve.set_defaults(func=cmd_serve)
```

And add the handler (anywhere in the file, e.g., after `_cmd_schema_discovery`):

```python
def cmd_serve(args: argparse.Namespace) -> int:  # pragma: no cover
    """Boot the goldens HTTP API via uvicorn. Reads config from env."""
    import os
    import sys

    if not os.environ.get("GOLDENS_API_TOKEN"):
        print(
            "ERROR: GOLDENS_API_TOKEN env var is required. "
            "Set it before running, e.g.:\n"
            "    export GOLDENS_API_TOKEN=$(uuidgen)\n"
            "    query-eval serve",
            file=sys.stderr,
        )
        return 2

    try:
        import uvicorn
        from goldens.api.app import create_app
    except ImportError as e:
        print(f"ERROR: {e}. Did you install features/goldens with the api extra?", file=sys.stderr)
        return 2

    app = create_app()
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0
```

- [ ] **Step 3: Verify the CLI subparser is registered**

Run: `source .venv/bin/activate && query-eval --help 2>&1 | grep -i serve`

Expected: `serve  Run the goldens HTTP API on 127.0.0.1`.

- [ ] **Step 4: Verify the serve subcommand parses without booting**

Run: `source .venv/bin/activate && query-eval serve --help 2>&1 | tail -10`

Expected: shows `--port`, `--host`, `--reload`.

- [ ] **Step 5: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/cli.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(query-eval): add 'serve' subcommand to boot goldens HTTP API"
```

---

## Task 18: CLI/API concurrency test

**Files:**
- Create: `features/goldens/tests/test_api_concurrency.py`

This test ensures parallel writes from CLI subprocess + API in-process don't corrupt the event log. A.3's fcntl.LOCK_EX serialises them.

- [ ] **Step 1: Write the test**

```python
# features/goldens/tests/test_api_concurrency.py
"""Verify CLI subprocess writes and API in-process writes serialise correctly
via A.3's fcntl.LOCK_EX. No torn or duplicated entries; total count = sum of
parties' writes."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest


def _seed_identity(xdg: Path, pseudonym: str) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        f'schema_version = 1\npseudonym = "{pseudonym}"\nlevel = "phd"\n'
        f'created_at_utc = "2026-04-30T08:00:00Z"\n',
        encoding="utf-8",
    )


def _seed_doc(outputs: Path, slug: str = "doc-a") -> None:
    src = Path(__file__).parent / "fixtures" / "analyze_minimal.json"
    analyze = outputs / slug / "analyze"
    analyze.mkdir(parents=True)
    shutil.copy(src, analyze / "ts.json")


def test_parallel_api_writes_all_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two threads each call POST .../entries N times; expect 2*N events
    in the log, none duplicated, none lost."""
    from fastapi.testclient import TestClient

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    _seed_identity(xdg, "alice")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
    monkeypatch.setenv("GOLDENS_DATA_ROOT", str(outputs))
    _seed_doc(outputs)

    from goldens.api.app import create_app

    client = TestClient(create_app())
    client.headers.update({"X-Auth-Token": "tok-test"})

    elements = client.get("/api/docs/doc-a/elements").json()
    el_id = elements[0]["element"]["element_id"]

    N = 10
    errors: list[str] = []

    def _writer(prefix: str) -> None:
        for i in range(N):
            try:
                resp = client.post(
                    f"/api/docs/doc-a/elements/{el_id}/entries",
                    json={"query": f"Frage {prefix}-{i}"},
                )
                if resp.status_code != 201:
                    errors.append(f"{prefix}-{i}: status {resp.status_code}")
            except Exception as e:
                errors.append(f"{prefix}-{i}: {e}")

    t1 = threading.Thread(target=_writer, args=("A",))
    t2 = threading.Thread(target=_writer, args=("B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    listed = client.get("/api/entries").json()
    queries = {e["query"] for e in listed}
    assert len(queries) == 2 * N
    for prefix in ("A", "B"):
        for i in range(N):
            assert f"Frage {prefix}-{i}" in queries
```

- [ ] **Step 2: Run test**

Run: `cd features/goldens && python -m pytest tests/test_api_concurrency.py -v`

Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add features/goldens/tests/test_api_concurrency.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "test(goldens/api): parallel writes serialise via A.3 fcntl lock — no loss, no dup"
```

---

## Task 19: Final smoke + push + open PR

- [ ] **Step 1: Full goldens test suite + coverage**

Run: `source .venv/bin/activate && python -m pytest features/goldens/tests features/evaluators/chunk_match/tests 2>&1 | tail -10`

Expected: every test passes; goldens coverage ≥95%; chunk_match coverage unchanged.

- [ ] **Step 2: Lint + format**

```bash
.venv/bin/ruff check features/goldens && .venv/bin/ruff format --check features/goldens 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 3: Manual smoke against the real Tragkorb fixture**

```bash
source .venv/bin/activate
export GOLDENS_API_TOKEN=$(uuidgen)
echo "Token: $GOLDENS_API_TOKEN"
query-eval serve &
sleep 2
curl -s http://127.0.0.1:8000/api/health
echo
curl -s -H "X-Auth-Token: $GOLDENS_API_TOKEN" http://127.0.0.1:8000/api/docs
echo
pkill -f "query-eval serve"
```

Expected: `{"status":"ok","goldens_root":"outputs"}` then `[{"slug":"smoke-test-tragkorb","element_count":9}]`.

- [ ] **Step 4: Push branch**

```bash
git push -u origin feat/a-plus-1-backend
```

- [ ] **Step 5: Open PR**

```bash
gh pr create --title "feat(goldens): A-Plus.1 FastAPI backend" --body "$(cat <<'EOF'
## Summary
Implements A-Plus.1 — FastAPI HTTP backend in `features/goldens/src/goldens/api/` exposing A.4-A.6 over HTTP.

Spec: `docs/superpowers/specs/2026-04-30-a-plus-1-backend-design.md` (PR #18)
Plan: `docs/superpowers/plans/2026-04-30-a-plus-1-backend.md`
Prerequisite: Pydantic-migration PR #22 (merged)

## Endpoints
- \`GET /api/health\` — liveness, no auth
- \`GET /api/docs\` — list slugs
- \`GET /api/docs/{slug}/elements\` — element list with active-entry counts
- \`GET /api/docs/{slug}/elements/{element_id}\` — element detail with active entries
- \`POST /api/docs/{slug}/elements/{element_id}/entries\` — create entry
- \`POST /api/docs/{slug}/synthesise\` — NDJSON streaming
- \`GET /api/entries\` — list active entries (filterable: ?slug, ?source_element, ?include_deprecated)
- \`GET /api/entries/{id}\` — entry detail
- \`POST /api/entries/{id}/refine\` — refine
- \`POST /api/entries/{id}/deprecate\` — deprecate

## Key code
- Auth: X-Auth-Token middleware with /api/health + /docs allowlist
- Streaming: synthesise_iter() generator factored out of synthesise(); endpoint emits NDJSON SynthLine union
- State: stateless server; A.3 fcntl-locking handles CLI/API concurrent writes
- Identity: server boots with one HumanActor from ~/.config/goldens/identity.toml
- CLI: \`query-eval serve --port 8000\` boots uvicorn

## Test plan
- [x] \`pytest features/goldens/tests features/evaluators/chunk_match/tests\` — green, ≥95% coverage
- [x] ruff check + format — clean
- [x] Manual smoke: \`/api/health\` + \`/api/docs\` against Tragkorb fixture
- [x] Concurrency test: 2 threads × 10 POST /entries each → 20 events, no loss/dup
- [x] Streaming test: dry-run synthesise emits start + per-element + complete lines
EOF
)"
```

- [ ] **Step 6: Final report to lead**

After PR opens, message lead with `[phase-complete]` summary.

---

## Self-Review

**Spec coverage:**
- §3 Architecture (process model, state, boundary) → Tasks 6, 17
- §4 URL design (10 endpoints) → Tasks 6 (health), 8-13 (docs/synthesise), 14-16 (entries)
- §5 Schema strategy (Pydantic-native domain + small API additions) → Task 3 (schemas) + reuse of `goldens.schemas` everywhere
- §6 Streaming protocol (start/element/complete/error lines, generator pattern, A.5 refactor) → Tasks 12, 13
- §7 Error handling (401/422/404/409/streaming-mid-error) → Task 6 (handlers), per-router (Tasks 8-16)
- §8 Auth flow → Tasks 6, 7
- §9 Module layout → covered file-by-file across Tasks 2-7
- §10 Test strategy (httpx + msw-equivalent + tmp_path fixtures + concurrency) → Tasks 8-16, 18
- §11 Build/Deploy (CLI serve subcommand) → Task 17
- §13 Decisions AP1.1-AP1.11 → all consistent with implementation choices

**Placeholder scan:** none.

**Type consistency:**
- `CreateEntryResponse` returns `entry_id` + `event_id` — matches both `build_created_event` Event fields and consumer in test
- `RefineResponse.new_entry_id` matches `refine_op` return — checked
- `DeprecateResponse.event_id` matches `deprecate_op` return — checked
- `SynthLine` discriminated union has `start`/`element`/`error`/`complete` — all four emitted by streaming endpoint
- `ElementWithCounts.element` is `DocumentElement` (frozen-Pydantic since PR #22) — composes correctly
- `ElementDetailResponse.entries: list[RetrievalEntry]` — matches projection result type
- `_human_actor_from_identity` calls `identity_to_human_actor` — matches existing curate.py usage

**Scope check:** one PR worth of work. ~19 tasks, each bite-sized. The synthesise_iter refactor (Task 12) is the only multi-step internal change but it's well-bounded. Concurrency test (Task 18) is a single integration test, not a separate subsystem.
