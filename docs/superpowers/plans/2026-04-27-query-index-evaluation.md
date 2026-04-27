# Query Index Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a retrieval-quality evaluation pipeline (`query-index-eval`) on top of a small Azure AI Search wrapper (`query-index`), structured as a `pip`+`venv` monorepo with two feature packages, full TDD coverage, and a pre-commit boundary check that keeps Azure SDK imports inside `query-index`.

**Architecture:** Monorepo with `features/query-index/` (search library — only place that imports `azure.*` / `openai`) and `features/query-index-eval/` (evaluation pipeline that consumes `query-index`). Single root venv with editable installs. Hand-curated `golden_v1.jsonl` is gitignored and append-only. Tests are unit-only with mocked Azure clients; live verification happens in the user's separate cloned workspace.

**Tech Stack:** Python ≥ 3.11, `pip` + `venv`, `pytest` + `pytest-cov`, `ruff`, `mypy`, `pre-commit`, `python-dotenv`, `azure-search-documents`, `azure-identity`, `openai`.

**Spec reference:** `docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md`

---

## File structure (lock-in)

This plan implements the structure from the spec. Files created or modified are listed per task, with paths relative to the repository root.

```
DocumentAnalysisMicrosoft/
├── pyproject.toml                              # NEW — root tool config (ruff/mypy/pytest)
├── requirements-dev.txt                        # NEW
├── .pre-commit-config.yaml                     # NEW
├── scripts/
│   └── check_import_boundary.sh                # NEW — boundary enforcement
├── bootstrap.sh                                # NEW
├── Makefile                                    # NEW
├── README.md                                   # NEW
├── archive/
│   └── query_index_v0.py                       # MOVED from query_index.py via git mv
├── features/
│   ├── query-index/
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   ├── .env.example
│   │   ├── src/query_index/
│   │   │   ├── __init__.py
│   │   │   ├── types.py
│   │   │   ├── config.py
│   │   │   ├── client.py
│   │   │   ├── embeddings.py
│   │   │   ├── search.py
│   │   │   ├── chunks.py
│   │   │   ├── schema_discovery.py
│   │   │   └── ingest.py
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_types.py
│   │       ├── test_config.py
│   │       ├── test_client.py
│   │       ├── test_embeddings.py
│   │       ├── test_search.py
│   │       ├── test_chunks.py
│   │       ├── test_schema_discovery.py
│   │       └── test_ingest.py
│   └── query-index-eval/                       # implemented in Phase 2 (separate plan section)
```

Phase 2 (the `query-index-eval` package) and Phase 3 (final acceptance) will be added to this plan after Phase 1 review.

---

# Phase 0 — Repository scaffolding

Goal of this phase: a working `bootstrap.sh && make test` on an empty test suite, with pre-commit installed and the boundary check operational. No feature code yet.

## Task 1: Root tool configuration

**Files:**
- Create: `pyproject.toml`
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create root `pyproject.toml`**

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"
extend-exclude = ["archive/"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
ignore = []

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
warn_unused_ignores = true
warn_return_any = true
warn_unreachable = true
ignore_missing_imports = true
exclude = ["archive/", "build/", "dist/"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers"
testpaths = ["features"]
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
# requirements-dev.txt
ruff==0.6.9
mypy==1.11.2
pytest==8.3.3
pytest-cov==5.0.0
pre-commit==3.8.0
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml requirements-dev.txt
git commit -m "chore: add root tool config (ruff, mypy, pytest) and dev requirements"
```

---

## Task 2: Import-boundary check + pre-commit config

**Files:**
- Create: `scripts/check_import_boundary.sh`
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Create the boundary check script**

```bash
# scripts/check_import_boundary.sh
#!/usr/bin/env bash
# Enforce: only features/query-index/ may import azure.* or openai.
# Exits non-zero with the offending lines if a violation is found.
set -euo pipefail

if [ ! -d features ]; then
    exit 0
fi

violations="$(grep -rEn '^(import|from)[[:space:]]+(azure|openai)' \
    --include='*.py' \
    features/ \
    | grep -v '^features/query-index/' \
    || true)"

if [ -n "$violations" ]; then
    echo "BOUNDARY VIOLATION: azure/openai imports are only allowed inside features/query-index/"
    echo "$violations"
    exit 1
fi
exit 0
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/check_import_boundary.sh
```

- [ ] **Step 3: Verify it passes on the empty repo**

Run: `bash scripts/check_import_boundary.sh`
Expected: exit 0, no output.

- [ ] **Step 4: Verify it fails on a fake violation**

Create a temp file: `mkdir -p features/query-index-eval/src/x && echo 'import azure.search.documents' > features/query-index-eval/src/x/bad.py`
Run: `bash scripts/check_import_boundary.sh`
Expected: prints "BOUNDARY VIOLATION", exits with code 1.
Cleanup: `rm -rf features/query-index-eval`

- [ ] **Step 5: Create `.pre-commit-config.yaml`**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: []
        args: [--config-file=pyproject.toml]
        exclude: ^archive/

  - repo: local
    hooks:
      - id: import-boundary-check
        name: Restrict azure/openai imports to features/query-index/
        entry: bash scripts/check_import_boundary.sh
        language: system
        pass_filenames: false
        always_run: true
```

- [ ] **Step 6: Commit**

```bash
git add scripts/check_import_boundary.sh .pre-commit-config.yaml
git commit -m "chore: add import-boundary check and pre-commit config"
```

---

## Task 3: bootstrap.sh and Makefile

**Files:**
- Create: `bootstrap.sh`
- Create: `Makefile`

- [ ] **Step 1: Create `bootstrap.sh`**

```bash
# bootstrap.sh
#!/usr/bin/env bash
# Create the development venv and install the workspace in editable mode.
set -euo pipefail

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements-dev.txt

if [ -f features/query-index/pyproject.toml ]; then
    pip install -e features/query-index
fi
if [ -f features/query-index-eval/pyproject.toml ]; then
    pip install -e features/query-index-eval
fi

pre-commit install

echo
echo "Bootstrap complete."
echo "Activate with: source .venv/bin/activate"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x bootstrap.sh
```

- [ ] **Step 3: Create `Makefile`**

```makefile
# Makefile
.PHONY: bootstrap test test-cov lint fmt clean curate eval schema help

help:
	@echo "Targets:"
	@echo "  bootstrap   Create .venv and install workspace in editable mode"
	@echo "  test        Run unit tests"
	@echo "  test-cov    Run unit tests with coverage report"
	@echo "  lint        Run ruff and mypy"
	@echo "  fmt         Auto-fix ruff issues and format"
	@echo "  clean       Remove .venv and caches"
	@echo "  curate      Run query-eval curate (interactive)"
	@echo "  eval        Run query-eval eval"
	@echo "  schema      Run query-eval schema-discovery"

bootstrap:
	./bootstrap.sh

test:
	pytest features/

test-cov:
	pytest features/ --cov=features --cov-report=term-missing

lint:
	ruff check features/ scripts/
	mypy features/

fmt:
	ruff check --fix features/ scripts/
	ruff format features/ scripts/

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

curate:
	query-eval curate

eval:
	query-eval eval

schema:
	query-eval schema-discovery
```

- [ ] **Step 4: Commit**

```bash
git add bootstrap.sh Makefile
git commit -m "chore: add bootstrap.sh and Makefile for venv + dev workflow"
```

---

## Task 4: Move `query_index.py` to `archive/query_index_v0.py`

**Files:**
- Move: `query_index.py` → `archive/query_index_v0.py` (byte-for-byte unchanged, history preserved via `git mv`)

- [ ] **Step 1: Create the archive directory**

```bash
mkdir -p archive
```

- [ ] **Step 2: Move the file via git**

```bash
git mv query_index.py archive/query_index_v0.py
```

- [ ] **Step 3: Verify the file is unchanged**

```bash
git diff --staged --stat
```

Expected: `1 file changed, 0 insertions(+), 0 deletions(-)` — git recognises the rename, no content change.

- [ ] **Step 4: Verify content byte-for-byte**

```bash
git show HEAD:query_index.py | diff - archive/query_index_v0.py
```

Expected: no output (files are identical).

- [ ] **Step 5: Commit**

```bash
git commit -m "chore: move original query_index.py to archive/query_index_v0.py

Preserves the prototype unchanged for reference. New code lives in
features/query-index/."
```

---

## Task 5: Repository README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

````markdown
# DocumentAnalysisMicrosoft

A retrieval-quality evaluation harness for an Azure AI Search index, structured as a small monorepo of feature packages.

## Workspace separation pattern

This repository follows a workspace-separation pattern:

- **This workspace** is for development. Sample / non-sensitive data lives in `data/`; tests and lint pass without touching real Azure services.
- **Production runs** happen in a separate cloned workspace maintained by the user, with real data in `data/` and real credentials in `.env`.

The following are gitignored so each cloned workspace has its own copy:

- `data/`, `data_dummy/`
- `.env`
- `features/*/datasets/golden_*.jsonl`
- `features/*/reports/`, `features/*/logs/`
- `.venv/` and Python build/cache artefacts

## Layout

```
features/
  query-index/          # Azure AI Search wrapper (only package importing azure.*)
  query-index-eval/     # retrieval-quality evaluation pipeline
archive/
  query_index_v0.py     # original prototype, preserved unchanged
docs/
  superpowers/
    specs/              # design specs
    plans/              # implementation plans
  evaluation/
    metrics-rationale.md
```

## Setup

```bash
./bootstrap.sh
source .venv/bin/activate
make test
```

`bootstrap.sh` creates a single root venv, installs all feature packages in editable mode, and installs the pre-commit hooks (including the boundary check that confines `azure.*` and `openai` imports to `features/query-index/`).

## Development workflow

```bash
make test       # unit tests (mocked, offline)
make lint       # ruff + mypy
make fmt        # auto-fix
make clean      # remove caches and venv
```

## Production workflow (user's separate clone)

```bash
git clone <this repo> ~/code/DocumentAnalysisMicrosoft-real
cd ~/code/DocumentAnalysisMicrosoft-real
cp .env.example .env  # and fill in real keys
mkdir data && cp <real PDFs> data/
./bootstrap.sh
make schema     # confirm index field names
make curate     # build hand-curated golden set
make eval       # produce metric report
```

## Documents

- Design spec: [`docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md`](docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md)
- Metric rationale: [`docs/evaluation/metrics-rationale.md`](docs/evaluation/metrics-rationale.md)
- Implementation plan: [`docs/superpowers/plans/2026-04-27-query-index-evaluation.md`](docs/superpowers/plans/2026-04-27-query-index-evaluation.md)
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add repository README with workspace-separation pattern"
```

---

## Task 6: Bootstrap end-to-end smoke test

Verify Phase 0 actually works before adding feature code.

- [ ] **Step 1: Run bootstrap**

```bash
./bootstrap.sh
```

Expected: a `.venv/` is created, dev requirements install successfully, pre-commit installs. No errors. Two missing-package messages from `bootstrap.sh` are fine because the feature packages do not exist yet — the script skips them when the `pyproject.toml` is missing.

- [ ] **Step 2: Activate the venv**

```bash
source .venv/bin/activate
which pytest
```

Expected: `which pytest` points inside `.venv/bin/`.

- [ ] **Step 3: Run the (empty) test target**

```bash
make test
```

Expected: pytest collects 0 items, exits 0 (no error). pytest may emit `no tests ran` — that's success at this point.

- [ ] **Step 4: Run lint targets**

```bash
make lint
```

Expected: ruff finds 0 issues; mypy reports `Success: no issues found` (no Python files to check yet apart from the boundary script — mypy is configured to skip `archive/`).

- [ ] **Step 5: Run pre-commit on all files**

```bash
pre-commit run --all-files
```

Expected: all hooks pass (the boundary check runs on an empty `features/`, so there is nothing to violate). Ruff may auto-format files — if it does, re-run until clean.

- [ ] **Step 6: Commit any auto-format changes (if any)**

```bash
git status
# If pre-commit modified anything:
git add -A
git commit -m "style: apply ruff auto-formatting"
```

If nothing changed, skip the commit.

---

# Phase 1 — `query-index` package

Goal of this phase: a fully tested `query-index` library that wraps Azure AI Search and Azure OpenAI behind a small public API. All tests are mocked. The package installs in editable mode and `make test` passes with ≥ 90% coverage on `features/query-index/src/query_index/`.

The package consists of small files, each with one responsibility. Tasks are ordered to respect dependencies: `types` → `config` → `client` → `embeddings` → `search`/`chunks`/`schema_discovery`/`ingest` → `__init__`.

**Hybrid `cfg` convention (applies to every public function in this package):**

Every public function takes an optional `cfg: Config | None = None` as its last parameter. The body starts with `if cfg is None: cfg = Config.from_env()`. This means:

- Consumers can omit `cfg` for the convenient case: `hybrid_search("foo")` works.
- Tests pass `cfg` explicitly, avoiding global state and monkey-patching.
- Multi-config use (e.g., dev vs. prod side-by-side) is supported by passing different `Config` objects.

## Task 7: Package skeleton

**Files:**
- Create: `features/query-index/pyproject.toml`
- Create: `features/query-index/.env.example`
- Create: `features/query-index/README.md`
- Create: `features/query-index/src/query_index/__init__.py` (empty for now)
- Create: `features/query-index/tests/__init__.py` (empty)
- Create: `features/query-index/tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
# features/query-index/pyproject.toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "query-index"
version = "0.1.0"
description = "Azure AI Search hybrid-query library — the only package that talks to Azure."
requires-python = ">=3.11"
dependencies = [
    "azure-search-documents>=11.5.0",
    "azure-identity>=1.17.0",
    "openai>=1.40.0",
    "python-dotenv>=1.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers --cov=query_index --cov-report=term-missing --cov-fail-under=90"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```
# features/query-index/.env.example
# Azure AI Foundry (OpenAI)
AI_FOUNDRY_KEY=
AI_FOUNDRY_ENDPOINT=https://your-foundry.services.ai.azure.com

# Azure AI Search
AI_SEARCH_KEY=
AI_SEARCH_ENDPOINT=https://your-search.search.windows.net
AI_SEARCH_INDEX_NAME=

# Embedding model (pin deployment + version explicitly)
EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
EMBEDDING_MODEL_VERSION=1
EMBEDDING_DIMENSIONS=3072
AZURE_OPENAI_API_VERSION=2024-02-01
```

- [ ] **Step 3: Create `README.md`**

````markdown
# query-index

Azure AI Search hybrid-query library. The **only** package in this repository allowed to import `azure.*` or `openai` — enforced by a pre-commit hook at the repo root.

## Public API

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

## Environment

See [`.env.example`](.env.example). Variables are loaded once at the entry point of any consuming CLI; this package itself does not call `load_dotenv()`.

## Tests

```bash
pytest features/query-index/
```

All tests are mocked — they do not call Azure. Live verification is done by the user in their separate cloned workspace.
````

- [ ] **Step 4: Create empty package `__init__.py` and tests `__init__.py`**

```bash
mkdir -p features/query-index/src/query_index features/query-index/tests
touch features/query-index/src/query_index/__init__.py
touch features/query-index/tests/__init__.py
```

- [ ] **Step 5: Create `tests/conftest.py` with shared fixtures**

```python
# features/query-index/tests/conftest.py
"""Shared fixtures for query_index tests. All fixtures mock Azure clients."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Populate the environment with valid dummy values for Config.from_env()."""
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
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """A MagicMock that mimics openai.AzureOpenAI."""
    client = MagicMock()
    client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 3072)]
    )
    return client


@pytest.fixture
def mock_search_client() -> MagicMock:
    """A MagicMock that mimics azure.search.documents.SearchClient."""
    client = MagicMock()
    client.search.return_value = []
    return client
```

- [ ] **Step 6: Install the (empty) package in the venv**

```bash
source .venv/bin/activate
pip install -e features/query-index
```

Expected: install succeeds, `pip show query-index` reports version 0.1.0.

- [ ] **Step 7: Verify package is importable**

```bash
python -c "import query_index; print(query_index.__file__)"
```

Expected: prints the path to `features/query-index/src/query_index/__init__.py`.

- [ ] **Step 8: Commit**

```bash
git add features/query-index/
git commit -m "feat(query-index): scaffold package (pyproject, README, .env.example, conftest)"
```

---

## Task 8: `types.py` — `Chunk` and `SearchHit`

The two frozen dataclasses that flow through the rest of the package. `chunk` is `repr=False` so accidental logging of a `SearchHit` does not emit chunk text.

**Files:**
- Create: `features/query-index/src/query_index/types.py`
- Create: `features/query-index/tests/test_types.py`

- [ ] **Step 1: Write the failing test**

```python
# features/query-index/tests/test_types.py
"""Tests for the dataclasses in query_index.types."""
from __future__ import annotations

import pytest


def test_chunk_holds_id_title_chunk() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="Title", chunk="Some chunk body.")
    assert c.chunk_id == "c1"
    assert c.title == "Title"
    assert c.chunk == "Some chunk body."


def test_chunk_repr_excludes_chunk_field() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="T", chunk="SECRET-CONTENT")
    assert "SECRET-CONTENT" not in repr(c)


def test_chunk_is_frozen() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="T", chunk="x")
    with pytest.raises(Exception):  # FrozenInstanceError is a dataclasses.FrozenInstanceError
        c.chunk_id = "c2"  # type: ignore[misc]


def test_searchhit_holds_all_fields() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c1", title="T", chunk="body", score=0.87)
    assert h.chunk_id == "c1"
    assert h.title == "T"
    assert h.chunk == "body"
    assert h.score == pytest.approx(0.87)


def test_searchhit_repr_excludes_chunk_field() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c1", title="T", chunk="LEAKY", score=0.5)
    assert "LEAKY" not in repr(h)


def test_searchhit_str_shows_id_and_score_only() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c42", title="T", chunk="body", score=0.875)
    s = str(h)
    assert "c42" in s
    assert "0.875" in s
    assert "body" not in s
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
pytest features/query-index/tests/test_types.py -v
```

Expected: 6 failures, all citing `ModuleNotFoundError: No module named 'query_index.types'`.

- [ ] **Step 3: Implement `types.py`**

```python
# features/query-index/src/query_index/types.py
"""Frozen dataclasses passed through the search pipeline.

`chunk` is declared with repr=False so logging or pytest assertion failures
do not emit chunk text — see the spec section on logging hygiene.
"""
from __future__ import annotations

from dataclasses import dataclass, field


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

- [ ] **Step 4: Run the test, confirm it passes**

```bash
pytest features/query-index/tests/test_types.py -v
```

Expected: 6 passing tests.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/types.py features/query-index/tests/test_types.py
git commit -m "feat(query-index): add Chunk and SearchHit dataclasses with repr-safe chunk field"
```

---

## Task 9: `config.py` — environment-driven Config

A single frozen dataclass loaded once from `os.environ`. Every required variable raises a clear error if missing. Type-converted (`EMBEDDING_DIMENSIONS` is an int).

**Files:**
- Create: `features/query-index/src/query_index/config.py`
- Create: `features/query-index/tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_config.py
"""Tests for query_index.config.Config.from_env()."""
from __future__ import annotations

import pytest


def test_from_env_loads_all_required_fields(env_vars: dict[str, str]) -> None:
    from query_index.config import Config

    cfg = Config.from_env()
    assert cfg.ai_foundry_key == env_vars["AI_FOUNDRY_KEY"]
    assert cfg.ai_foundry_endpoint == env_vars["AI_FOUNDRY_ENDPOINT"]
    assert cfg.ai_search_key == env_vars["AI_SEARCH_KEY"]
    assert cfg.ai_search_endpoint == env_vars["AI_SEARCH_ENDPOINT"]
    assert cfg.ai_search_index_name == env_vars["AI_SEARCH_INDEX_NAME"]
    assert cfg.embedding_deployment_name == env_vars["EMBEDDING_DEPLOYMENT_NAME"]
    assert cfg.embedding_model_version == env_vars["EMBEDDING_MODEL_VERSION"]
    assert cfg.embedding_dimensions == int(env_vars["EMBEDDING_DIMENSIONS"])
    assert cfg.azure_openai_api_version == env_vars["AZURE_OPENAI_API_VERSION"]


def test_from_env_is_frozen(env_vars: dict[str, str]) -> None:
    from query_index.config import Config

    cfg = Config.from_env()
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.ai_foundry_key = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    "missing_var",
    [
        "AI_FOUNDRY_KEY",
        "AI_FOUNDRY_ENDPOINT",
        "AI_SEARCH_KEY",
        "AI_SEARCH_ENDPOINT",
        "AI_SEARCH_INDEX_NAME",
        "EMBEDDING_DEPLOYMENT_NAME",
        "EMBEDDING_MODEL_VERSION",
        "EMBEDDING_DIMENSIONS",
        "AZURE_OPENAI_API_VERSION",
    ],
)
def test_from_env_raises_with_clear_message_when_required_missing(
    env_vars: dict[str, str], monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    from query_index.config import Config

    monkeypatch.delenv(missing_var, raising=False)
    with pytest.raises(KeyError) as excinfo:
        Config.from_env()
    assert missing_var in str(excinfo.value)


def test_embedding_dimensions_must_be_integer(
    env_vars: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from query_index.config import Config

    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "not-a-number")
    with pytest.raises(ValueError):
        Config.from_env()
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_config.py -v
```

Expected: every test fails with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `config.py`**

```python
# features/query-index/src/query_index/config.py
"""Environment-driven configuration for query_index.

`Config.from_env()` reads required variables from os.environ. Missing variables
raise KeyError with the variable name in the message. EMBEDDING_DIMENSIONS is
parsed as int; if it is not numeric, ValueError is raised.

Loading dotenv files (`.env`) is the responsibility of the entry point, not this
module — see the spec section on env loading.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED_VARS: tuple[str, ...] = (
    "AI_FOUNDRY_KEY",
    "AI_FOUNDRY_ENDPOINT",
    "AI_SEARCH_KEY",
    "AI_SEARCH_ENDPOINT",
    "AI_SEARCH_INDEX_NAME",
    "EMBEDDING_DEPLOYMENT_NAME",
    "EMBEDDING_MODEL_VERSION",
    "EMBEDDING_DIMENSIONS",
    "AZURE_OPENAI_API_VERSION",
)


@dataclass(frozen=True)
class Config:
    ai_foundry_key: str
    ai_foundry_endpoint: str
    ai_search_key: str
    ai_search_endpoint: str
    ai_search_index_name: str
    embedding_deployment_name: str
    embedding_model_version: str
    embedding_dimensions: int
    azure_openai_api_version: str

    @classmethod
    def from_env(cls) -> "Config":
        for var in _REQUIRED_VARS:
            if var not in os.environ:
                raise KeyError(f"Required environment variable not set: {var}")

        return cls(
            ai_foundry_key=os.environ["AI_FOUNDRY_KEY"],
            ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
            ai_search_key=os.environ["AI_SEARCH_KEY"],
            ai_search_endpoint=os.environ["AI_SEARCH_ENDPOINT"],
            ai_search_index_name=os.environ["AI_SEARCH_INDEX_NAME"],
            embedding_deployment_name=os.environ["EMBEDDING_DEPLOYMENT_NAME"],
            embedding_model_version=os.environ["EMBEDDING_MODEL_VERSION"],
            embedding_dimensions=int(os.environ["EMBEDDING_DIMENSIONS"]),
            azure_openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_config.py -v
```

Expected: 12 tests pass (1 success + 1 frozen + 9 parametrized missing-var + 1 non-numeric dimensions).

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/config.py features/query-index/tests/test_config.py
git commit -m "feat(query-index): add Config dataclass loaded from environment"
```

---

## Task 10: `client.py` — lazy Azure client factory

Builds `AzureOpenAI` and `SearchClient` on first access. Lazy because tests should never instantiate real clients.

**Files:**
- Create: `features/query-index/src/query_index/client.py`
- Create: `features/query-index/tests/test_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_client.py
"""Tests for query_index.client lazy-construction helpers."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_get_openai_client_constructs_azureopenai_with_config(
    env_vars: dict[str, str],
) -> None:
    from query_index.client import get_openai_client
    from query_index.config import Config

    cfg = Config.from_env()
    with patch("query_index.client.AzureOpenAI") as mock_cls:
        get_openai_client(cfg)
    mock_cls.assert_called_once_with(
        api_version=cfg.azure_openai_api_version,
        azure_endpoint=cfg.ai_foundry_endpoint,
        api_key=cfg.ai_foundry_key,
    )


def test_get_search_client_constructs_searchclient_with_config(
    env_vars: dict[str, str],
) -> None:
    from query_index.client import get_search_client
    from query_index.config import Config

    cfg = Config.from_env()
    with patch("query_index.client.SearchClient") as mock_cls, patch(
        "query_index.client.AzureKeyCredential"
    ) as mock_cred:
        mock_cred.return_value = "credential-instance"
        get_search_client(cfg)
    mock_cred.assert_called_once_with(cfg.ai_search_key)
    mock_cls.assert_called_once_with(
        endpoint=cfg.ai_search_endpoint,
        index_name=cfg.ai_search_index_name,
        credential="credential-instance",
    )


def test_get_search_index_client_constructs_with_config(
    env_vars: dict[str, str],
) -> None:
    from query_index.client import get_search_index_client
    from query_index.config import Config

    cfg = Config.from_env()
    with patch("query_index.client.SearchIndexClient") as mock_cls, patch(
        "query_index.client.AzureKeyCredential"
    ) as mock_cred:
        mock_cred.return_value = "credential-instance"
        get_search_index_client(cfg)
    mock_cred.assert_called_once_with(cfg.ai_search_key)
    mock_cls.assert_called_once_with(
        endpoint=cfg.ai_search_endpoint,
        credential="credential-instance",
    )
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_client.py -v
```

Expected: 3 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `client.py`**

```python
# features/query-index/src/query_index/client.py
"""Factory functions for the Azure SDK clients used by query_index.

Construction is lazy and parameterised on a Config — callers pass the config
they have, no module-level singletons. Tests patch the SDK classes here.
"""
from __future__ import annotations

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

from query_index.config import Config


def get_openai_client(cfg: Config) -> AzureOpenAI:
    return AzureOpenAI(
        api_version=cfg.azure_openai_api_version,
        azure_endpoint=cfg.ai_foundry_endpoint,
        api_key=cfg.ai_foundry_key,
    )


def get_search_client(cfg: Config) -> SearchClient:
    return SearchClient(
        endpoint=cfg.ai_search_endpoint,
        index_name=cfg.ai_search_index_name,
        credential=AzureKeyCredential(cfg.ai_search_key),
    )


def get_search_index_client(cfg: Config) -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=cfg.ai_search_endpoint,
        credential=AzureKeyCredential(cfg.ai_search_key),
    )
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_client.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/client.py features/query-index/tests/test_client.py
git commit -m "feat(query-index): add lazy factory functions for Azure clients"
```

---

## Task 11: `embeddings.py` — `get_embedding`

Wraps `client.embeddings.create` and returns `list[float]`.

**Files:**
- Create: `features/query-index/src/query_index/embeddings.py`
- Create: `features/query-index/tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_embeddings.py
"""Tests for query_index.embeddings.get_embedding()."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_get_embedding_calls_openai_with_text_and_deployment_name(
    env_vars: dict[str, str], mock_openai_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.embeddings import get_embedding

    cfg = Config.from_env()
    with patch("query_index.embeddings.get_openai_client", return_value=mock_openai_client):
        result = get_embedding("hello world", cfg)

    assert result == [0.1] * 3072
    mock_openai_client.embeddings.create.assert_called_once_with(
        input=["hello world"], model=cfg.embedding_deployment_name
    )


def test_get_embedding_returns_list_of_floats(
    env_vars: dict[str, str], mock_openai_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.embeddings import get_embedding

    mock_openai_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.5, 0.25, 0.125])]
    )
    cfg = Config.from_env()
    with patch("query_index.embeddings.get_openai_client", return_value=mock_openai_client):
        result = get_embedding("hi", cfg)

    assert result == [0.5, 0.25, 0.125]
    assert all(isinstance(x, float) for x in result)


def test_get_embedding_loads_config_from_env_when_cfg_omitted(
    env_vars: dict[str, str], mock_openai_client: MagicMock
) -> None:
    """When called without cfg, the function loads Config.from_env() itself.
    This exercises the hybrid-cfg convention used across the public API."""
    from query_index.embeddings import get_embedding

    with patch("query_index.embeddings.get_openai_client", return_value=mock_openai_client):
        result = get_embedding("hi")  # no cfg passed

    assert result == [0.1] * 3072
    mock_openai_client.embeddings.create.assert_called_once()
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_embeddings.py -v
```

Expected: 2 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `embeddings.py`**

```python
# features/query-index/src/query_index/embeddings.py
"""Embedding helper.

`get_embedding` calls Azure OpenAI's embeddings API with the deployment name
configured in the environment and returns the embedding vector as a list of
floats.
"""
from __future__ import annotations

from query_index.client import get_openai_client
from query_index.config import Config


def get_embedding(text: str, cfg: Config | None = None) -> list[float]:
    if cfg is None:
        cfg = Config.from_env()
    client = get_openai_client(cfg)
    response = client.embeddings.create(
        input=[text], model=cfg.embedding_deployment_name
    )
    return list(response.data[0].embedding)
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_embeddings.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/embeddings.py features/query-index/tests/test_embeddings.py
git commit -m "feat(query-index): add get_embedding wrapper around Azure OpenAI"
```

---

## Task 12: `search.py` — `hybrid_search`

The core hybrid (text + vector) search call. Calls `get_embedding` then issues a `SearchClient.search` with both `search_text` and `vector_queries`. Returns `list[SearchHit]`.

**Files:**
- Create: `features/query-index/src/query_index/search.py`
- Create: `features/query-index/tests/test_search.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_search.py
"""Tests for query_index.search.hybrid_search()."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_hybrid_search_returns_list_of_searchhits(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search
    from query_index.types import SearchHit

    mock_search_client.search.return_value = [
        {
            "chunk_id": "c1",
            "title": "Title 1",
            "chunk": "Body 1",
            "@search.score": 0.91,
        },
        {
            "chunk_id": "c2",
            "title": "Title 2",
            "chunk": "Body 2",
            "@search.score": 0.55,
        },
    ]
    cfg = Config.from_env()
    with patch(
        "query_index.search.get_search_client", return_value=mock_search_client
    ), patch("query_index.search.get_embedding", return_value=[0.1] * 3072):
        results = hybrid_search("query text", top=2, cfg=cfg)

    assert len(results) == 2
    assert all(isinstance(r, SearchHit) for r in results)
    assert results[0].chunk_id == "c1"
    assert results[0].score == 0.91
    assert results[1].chunk_id == "c2"


def test_hybrid_search_passes_text_and_vector_to_searchclient(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with patch(
        "query_index.search.get_search_client", return_value=mock_search_client
    ), patch("query_index.search.get_embedding", return_value=[0.7] * 3072):
        hybrid_search("the query", top=5, cfg=cfg)

    args, kwargs = mock_search_client.search.call_args
    assert kwargs["search_text"] == "the query"
    assert kwargs["top"] == 5
    vector_queries = kwargs["vector_queries"]
    assert len(vector_queries) == 1
    assert vector_queries[0].vector == [0.7] * 3072
    assert vector_queries[0].k_nearest_neighbors == 5
    assert vector_queries[0].fields == "text_vector"


def test_hybrid_search_passes_filter_when_provided(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with patch(
        "query_index.search.get_search_client", return_value=mock_search_client
    ), patch("query_index.search.get_embedding", return_value=[0.0] * 3072):
        hybrid_search("q", top=3, cfg=cfg, filter="labels/any(l: l eq 'csp:azure')")

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["filter"] == "labels/any(l: l eq 'csp:azure')"


def test_hybrid_search_omits_filter_when_none(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with patch(
        "query_index.search.get_search_client", return_value=mock_search_client
    ), patch("query_index.search.get_embedding", return_value=[0.0] * 3072):
        hybrid_search("q", top=3, cfg=cfg, filter=None)

    _, kwargs = mock_search_client.search.call_args
    # filter should either be absent or explicitly None — both acceptable
    assert kwargs.get("filter") is None


def test_hybrid_search_returns_empty_list_when_no_results(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with patch(
        "query_index.search.get_search_client", return_value=mock_search_client
    ), patch("query_index.search.get_embedding", return_value=[0.0] * 3072):
        results = hybrid_search("q", top=3, cfg=cfg)

    assert results == []
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_search.py -v
```

Expected: 5 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `search.py`**

```python
# features/query-index/src/query_index/search.py
"""Hybrid (text + vector) search over the configured Azure AI Search index."""
from __future__ import annotations

from azure.search.documents.models import VectorizedQuery

from query_index.client import get_search_client
from query_index.config import Config
from query_index.embeddings import get_embedding
from query_index.types import SearchHit


def hybrid_search(
    query: str,
    top: int = 10,
    filter: str | None = None,
    cfg: Config | None = None,
) -> list[SearchHit]:
    """Run a hybrid (text + vector) search.

    Returns up to `top` SearchHits ranked by Azure's hybrid scoring. The
    `filter` argument, if given, is passed through as an OData filter
    expression. The chunk text is included in each SearchHit but is
    repr-suppressed (see types.py).
    """
    if cfg is None:
        cfg = Config.from_env()
    vector = get_embedding(query, cfg)
    vector_query = VectorizedQuery(
        vector=vector,
        k_nearest_neighbors=top,
        fields="text_vector",
    )
    search_client = get_search_client(cfg)
    results = search_client.search(
        search_text=query,
        vector_queries=[vector_query],
        top=top,
        filter=filter,
    )

    hits: list[SearchHit] = []
    for r in results:
        hits.append(
            SearchHit(
                chunk_id=r["chunk_id"],
                title=r["title"],
                chunk=r["chunk"],
                score=float(r.get("@search.score", 0.0)),
            )
        )
    return hits
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_search.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/search.py features/query-index/tests/test_search.py
git commit -m "feat(query-index): add hybrid_search returning typed SearchHits"
```

---

## Task 13: `chunks.py` — `get_chunk` and `sample_chunks`

Used by the eval pipeline for hand-curation: fetch a chunk by id, or sample N random chunks deterministically.

**Files:**
- Create: `features/query-index/src/query_index/chunks.py`
- Create: `features/query-index/tests/test_chunks.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_chunks.py
"""Tests for query_index.chunks (get_chunk, sample_chunks)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_get_chunk_returns_chunk_for_known_id(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import get_chunk
    from query_index.config import Config
    from query_index.types import Chunk

    mock_search_client.get_document.return_value = {
        "chunk_id": "c42",
        "title": "Section 4.2",
        "chunk": "Tragkorbdurchmesser ...",
    }
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = get_chunk("c42", cfg)

    assert isinstance(result, Chunk)
    assert result.chunk_id == "c42"
    assert result.title == "Section 4.2"
    assert result.chunk == "Tragkorbdurchmesser ..."
    mock_search_client.get_document.assert_called_once_with(key="c42")


def test_sample_chunks_returns_n_chunks(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config
    from query_index.types import Chunk

    mock_search_client.search.return_value = [
        {"chunk_id": f"c{i}", "title": f"T{i}", "chunk": f"body{i}"} for i in range(5)
    ]
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = sample_chunks(n=5, seed=42, cfg=cfg)

    assert len(result) == 5
    assert all(isinstance(c, Chunk) for c in result)


def test_sample_chunks_pulls_a_window_at_least_as_large_as_sample_window(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """sample_chunks pulls a window of at least SAMPLE_WINDOW docs (or n if n
    is larger) before shuffling, so the returned sample is meaningfully random
    rather than just the top-n by relevance."""
    from query_index.chunks import SAMPLE_WINDOW, sample_chunks
    from query_index.config import Config

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        sample_chunks(n=3, seed=1, cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["top"] == max(3, SAMPLE_WINDOW)


def test_sample_chunks_deterministic_for_same_seed(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """Same seed must produce the same shuffled selection of chunk_ids
    given the same upstream document set."""
    from query_index.chunks import sample_chunks
    from query_index.config import Config

    docs = [{"chunk_id": f"c{i}", "title": f"T{i}", "chunk": f"b{i}"} for i in range(20)]
    mock_search_client.search.return_value = docs
    cfg = Config.from_env()

    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        run1 = sample_chunks(n=5, seed=12345, cfg=cfg)
    mock_search_client.search.return_value = docs  # re-prime the iterator
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        run2 = sample_chunks(n=5, seed=12345, cfg=cfg)

    assert [c.chunk_id for c in run1] == [c.chunk_id for c in run2]


def test_sample_chunks_raises_when_n_zero_or_negative(env_vars: dict[str, str]) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config

    cfg = Config.from_env()
    with pytest.raises(ValueError):
        sample_chunks(n=0, seed=1, cfg=cfg)
    with pytest.raises(ValueError):
        sample_chunks(n=-1, seed=1, cfg=cfg)
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_chunks.py -v
```

Expected: 5 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `chunks.py`**

```python
# features/query-index/src/query_index/chunks.py
"""Chunk-fetching helpers used by curation and synthesis flows.

`get_chunk(chunk_id, cfg)` fetches a single document by key.
`sample_chunks(n, seed, cfg)` returns N pseudo-random chunks; determinism is
provided by a local random.Random(seed) so the same seed yields the same
selection given the same upstream document set.
"""
from __future__ import annotations

import random

from query_index.client import get_search_client
from query_index.config import Config
from query_index.types import Chunk


def get_chunk(chunk_id: str, cfg: Config | None = None) -> Chunk:
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_client(cfg)
    doc = client.get_document(key=chunk_id)
    return Chunk(
        chunk_id=doc["chunk_id"],
        title=doc["title"],
        chunk=doc["chunk"],
    )


SAMPLE_WINDOW = 100
"""Default candidate-window size for sample_chunks.

We pull SAMPLE_WINDOW (or n, whichever is larger) candidates from the index,
then shuffle them with a seeded RNG and take the first n. This gives a
meaningfully random sample — pulling exactly n would just return the top-n by
relevance, which defeats the purpose of sampling.
"""


def sample_chunks(n: int, seed: int, cfg: Config | None = None) -> list[Chunk]:
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_client(cfg)
    window = max(n, SAMPLE_WINDOW)
    raw = list(client.search(search_text="*", top=window))
    rng = random.Random(seed)
    rng.shuffle(raw)
    selected = raw[:n]
    return [
        Chunk(chunk_id=d["chunk_id"], title=d["title"], chunk=d["chunk"])
        for d in selected
    ]
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_chunks.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/chunks.py features/query-index/tests/test_chunks.py
git commit -m "feat(query-index): add get_chunk and deterministic sample_chunks"
```

---

## Task 14: `schema_discovery.py` — print the index schema

Tiny helper that prints `SearchIndexClient.get_index(name)` field definitions. Useful for the user to confirm field names before evaluation.

**Files:**
- Create: `features/query-index/src/query_index/schema_discovery.py`
- Create: `features/query-index/tests/test_schema_discovery.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_schema_discovery.py
"""Tests for query_index.schema_discovery.print_index_schema()."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_print_index_schema_calls_get_index_with_name(
    env_vars: dict[str, str], capsys: "pytest.CaptureFixture[str]"
) -> None:
    from query_index.config import Config
    from query_index.schema_discovery import print_index_schema

    mock_index_client = MagicMock()
    mock_field = MagicMock()
    mock_field.name = "chunk_id"
    mock_field.type = "Edm.String"
    mock_field.searchable = False
    mock_field.filterable = False
    mock_field.retrievable = True
    mock_index_client.get_index.return_value = MagicMock(fields=[mock_field])

    cfg = Config.from_env()
    with patch(
        "query_index.schema_discovery.get_search_index_client",
        return_value=mock_index_client,
    ):
        print_index_schema("test-index", cfg)

    mock_index_client.get_index.assert_called_once_with("test-index")
    out = capsys.readouterr().out
    assert "chunk_id" in out
    assert "Edm.String" in out


def test_print_index_schema_handles_multiple_fields(
    env_vars: dict[str, str], capsys: "pytest.CaptureFixture[str]"
) -> None:
    from query_index.config import Config
    from query_index.schema_discovery import print_index_schema

    mock_index_client = MagicMock()
    fields = []
    for name, ftype in [("chunk_id", "Edm.String"), ("text_vector", "Collection(Edm.Single)")]:
        f = MagicMock()
        f.name = name
        f.type = ftype
        f.searchable = False
        f.filterable = False
        f.retrievable = True
        fields.append(f)
    mock_index_client.get_index.return_value = MagicMock(fields=fields)

    cfg = Config.from_env()
    with patch(
        "query_index.schema_discovery.get_search_index_client",
        return_value=mock_index_client,
    ):
        print_index_schema("test-index", cfg)

    out = capsys.readouterr().out
    assert "chunk_id" in out
    assert "text_vector" in out
    assert "Collection(Edm.Single)" in out
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_schema_discovery.py -v
```

Expected: 2 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `schema_discovery.py`**

```python
# features/query-index/src/query_index/schema_discovery.py
"""Print the field definitions of a named Azure AI Search index.

Used at setup time to confirm field names (chunk_id, chunk, title, text_vector,
labels, ...) match what the rest of the pipeline expects.
"""
from __future__ import annotations

from query_index.client import get_search_index_client
from query_index.config import Config


def print_index_schema(index_name: str, cfg: Config | None = None) -> None:
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_index_client(cfg)
    index = client.get_index(index_name)
    print(f"Index: {index_name}")
    print("-" * 60)
    for field in index.fields:
        flags = []
        if getattr(field, "searchable", False):
            flags.append("searchable")
        if getattr(field, "filterable", False):
            flags.append("filterable")
        if getattr(field, "retrievable", True):
            flags.append("retrievable")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {field.name}: {field.type}{flag_str}")
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_schema_discovery.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/schema_discovery.py features/query-index/tests/test_schema_discovery.py
git commit -m "feat(query-index): add print_index_schema helper"
```

---

## Task 15: `ingest.py` — `populate_index`

Reads documents from a directory, embeds them, and uploads them in batches. Logs only metadata — never chunk text. Path-driven; the *what to chunk* is intentionally simple at this stage (one chunk per file) and is widened later if needed.

**Files:**
- Create: `features/query-index/src/query_index/ingest.py`
- Create: `features/query-index/tests/test_ingest.py`

- [ ] **Step 1: Write the failing tests**

```python
# features/query-index/tests/test_ingest.py
"""Tests for query_index.ingest.populate_index()."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_populate_index_reads_files_and_uploads(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from query_index.config import Config
    from query_index.ingest import populate_index

    (tmp_path / "doc1.txt").write_text("First chunk body.")
    (tmp_path / "doc2.txt").write_text("Second chunk body.")

    mock_search_client = MagicMock()
    cfg = Config.from_env()
    with patch(
        "query_index.ingest.get_search_client", return_value=mock_search_client
    ), patch("query_index.ingest.get_embedding", return_value=[0.0] * 3072):
        populate_index(tmp_path, cfg)

    mock_search_client.upload_documents.assert_called_once()
    uploaded = mock_search_client.upload_documents.call_args.kwargs.get(
        "documents"
    ) or mock_search_client.upload_documents.call_args.args[0]
    assert len(uploaded) == 2
    chunk_ids = {d["chunk_id"] for d in uploaded}
    assert chunk_ids == {"doc1", "doc2"}


def test_populate_index_does_not_log_chunk_text(
    env_vars: dict[str, str], tmp_path: Path, capsys: "pytest.CaptureFixture[str]"
) -> None:
    from query_index.config import Config
    from query_index.ingest import populate_index

    secret = "SECRET-CHUNK-PAYLOAD-DO-NOT-LOG"
    (tmp_path / "doc1.txt").write_text(secret)

    mock_search_client = MagicMock()
    cfg = Config.from_env()
    with patch(
        "query_index.ingest.get_search_client", return_value=mock_search_client
    ), patch("query_index.ingest.get_embedding", return_value=[0.0] * 3072):
        populate_index(tmp_path, cfg)

    out = capsys.readouterr().out + capsys.readouterr().err
    assert secret not in out


def test_populate_index_raises_when_source_missing(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from query_index.config import Config
    from query_index.ingest import populate_index

    cfg = Config.from_env()
    missing = tmp_path / "does-not-exist"
    with patch("query_index.ingest.get_search_client") as mock_get_search:
        try:
            populate_index(missing, cfg)
        except FileNotFoundError:
            mock_get_search.assert_not_called()
            return
    raise AssertionError("populate_index should raise FileNotFoundError")
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
pytest features/query-index/tests/test_ingest.py -v
```

Expected: 3 failures with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `ingest.py`**

```python
# features/query-index/src/query_index/ingest.py
"""Populate an Azure AI Search index from a directory of source documents.

This is the simplest possible ingestion: each file in `source_path` becomes
one chunk, with `chunk_id` derived from the filename stem. Logs are
metadata-only — chunk text is never printed, written, or otherwise emitted
to anything other than the Azure upload payload.

Real ingestion (chunking by paragraph, embedding metadata, deduplication)
is a separate concern handled outside this package.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from query_index.client import get_search_client
from query_index.config import Config
from query_index.embeddings import get_embedding


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def populate_index(source_path: Path, cfg: Config | None = None) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"source_path does not exist: {source_path}")
    if cfg is None:
        cfg = Config.from_env()

    documents = []
    for file in sorted(source_path.iterdir()):
        if not file.is_file():
            continue
        chunk_text = file.read_text(encoding="utf-8")
        embedding = get_embedding(chunk_text, cfg)
        chunk_id = file.stem
        documents.append(
            {
                "chunk_id": chunk_id,
                "title": file.name,
                "chunk": chunk_text,
                "text_vector": embedding,
            }
        )
        print(
            f"Prepared chunk_id={chunk_id} size={len(chunk_text)} hash={_hash(chunk_text)}"
        )

    if not documents:
        print("No source files found; nothing to upload.")
        return

    client = get_search_client(cfg)
    client.upload_documents(documents=documents)
    print(f"Uploaded {len(documents)} documents to index {cfg.ai_search_index_name}")
```

- [ ] **Step 4: Run the tests, confirm they pass**

```bash
pytest features/query-index/tests/test_ingest.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index/src/query_index/ingest.py features/query-index/tests/test_ingest.py
git commit -m "feat(query-index): add populate_index helper (metadata-only logging)"
```

---

## Task 16: Public API in `__init__.py`

Re-export the public surface so consumers write `from query_index import hybrid_search` (not `from query_index.search import hybrid_search`).

**Files:**
- Modify: `features/query-index/src/query_index/__init__.py`
- Create: additional test in `features/query-index/tests/test_public_api.py`

- [ ] **Step 1: Write the failing test**

```python
# features/query-index/tests/test_public_api.py
"""Tests for the re-exported public API at query_index.__init__."""
from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index

    expected = {
        "Chunk",
        "Config",
        "SearchHit",
        "get_chunk",
        "get_embedding",
        "hybrid_search",
        "sample_chunks",
    }
    missing = expected - set(dir(query_index))
    assert not missing, f"Missing public exports: {missing}"


def test_public_api_does_not_expose_helpers() -> None:
    import query_index

    # Internal-only — should NOT be at the top level.
    not_expected = {"get_openai_client", "get_search_client", "get_search_index_client"}
    overexposed = not_expected & set(dir(query_index))
    assert not overexposed, f"Helpers leaked into public API: {overexposed}"
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
pytest features/query-index/tests/test_public_api.py -v
```

Expected: `test_public_api_exports_expected_names` fails (the names are not yet re-exported).

- [ ] **Step 3: Populate `__init__.py`**

```python
# features/query-index/src/query_index/__init__.py
"""Public API for the query_index package.

Internal modules (client, schema_discovery, ingest helpers) are NOT re-exported.
"""
from query_index.chunks import get_chunk, sample_chunks
from query_index.config import Config
from query_index.embeddings import get_embedding
from query_index.search import hybrid_search
from query_index.types import Chunk, SearchHit

__all__ = [
    "Chunk",
    "Config",
    "SearchHit",
    "get_chunk",
    "get_embedding",
    "hybrid_search",
    "sample_chunks",
]
```

- [ ] **Step 4: Run the public-API test, confirm it passes**

```bash
pytest features/query-index/tests/test_public_api.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Run the full package test suite with coverage**

```bash
pytest features/query-index/ -v --cov=query_index --cov-report=term-missing
```

Expected: all tests pass, coverage ≥ 90% on `src/query_index/`. The coverage gate in `features/query-index/pyproject.toml` will fail the run if coverage is below 90 %.

- [ ] **Step 6: Run the import-boundary check**

```bash
bash scripts/check_import_boundary.sh
```

Expected: exits 0 (no violations — `azure.*` and `openai` are inside `features/query-index/`).

- [ ] **Step 7: Run the lint suite**

```bash
make lint
```

Expected: ruff and mypy both clean.

- [ ] **Step 8: Commit**

```bash
git add features/query-index/src/query_index/__init__.py features/query-index/tests/test_public_api.py
git commit -m "feat(query-index): expose Chunk, SearchHit, Config, hybrid_search, get_chunk, sample_chunks, get_embedding"
```

---

## Task 17: Phase 1 acceptance check

Verify the whole package satisfies its acceptance criteria before moving to Phase 2.

- [ ] **Step 1: Full test run**

```bash
pytest features/query-index/ --cov=query_index --cov-report=term-missing
```

Expected: every test passes, coverage on `src/query_index/` ≥ 90 %.

- [ ] **Step 2: Full lint run**

```bash
make lint
```

Expected: zero ruff issues, zero mypy issues.

- [ ] **Step 3: Pre-commit on all files**

```bash
pre-commit run --all-files
```

Expected: all hooks pass, including `import-boundary-check`.

- [ ] **Step 4: Verify the package is importable end-to-end**

```bash
python -c "from query_index import hybrid_search, Chunk, SearchHit, Config; print('public API OK')"
```

Expected: `public API OK`.

- [ ] **Step 5: Tag Phase 1 complete (no commit needed; work is already committed)**

End of Phase 1. Hand back to user for review before starting Phase 2 (`query-index-eval`).

---

# Phase 2 and Phase 3 — to be added

After Phase 1 is reviewed and accepted, this plan will be extended with:

- **Phase 2 — `query-index-eval` package** (~9 tasks): schema, datasets (with mutation enforcement), metrics (Recall@k, Hit Rate@k, MRR, MAP), runner (with sample-size flagging and report-metadata), curate (TTY enforcement + substring check), CLI dispatch, public API.
- **Phase 3 — Acceptance** (~3 tasks): full `make test` + `make lint`, pre-commit boundary-violation negative test, README polish, final verification against the spec's acceptance criteria.

These will be appended to this same file on user signal.
