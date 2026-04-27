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

# Phase 2 — `query-index-eval` package

Goal: a fully tested evaluation pipeline that consumes `query-index`, computes IR metrics against a hand-curated golden set, and produces JSON reports. All tests are mocked (the `query_index` calls are mocked at the import boundary).

Tasks ordered so each builds on the previous: schema → datasets → metrics → runner → curate → cli → public API.

Hybrid `cfg` convention from Phase 1 also applies here: any function that needs a `query_index.Config` accepts an optional `cfg=None` and falls back to `Config.from_env()`.

## Task 18: Package skeleton for `query-index-eval`

**Files:**
- Create: `features/query-index-eval/pyproject.toml`
- Create: `features/query-index-eval/.env.example`
- Create: `features/query-index-eval/README.md`
- Create: `features/query-index-eval/src/query_index_eval/__init__.py` (empty)
- Create: `features/query-index-eval/tests/__init__.py` (empty)
- Create: `features/query-index-eval/tests/conftest.py`

- [ ] **Step 1: Create the directory tree**

```bash
mkdir -p features/query-index-eval/src/query_index_eval features/query-index-eval/tests features/query-index-eval/datasets features/query-index-eval/reports
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "query-index-eval"
version = "0.1.0"
description = "Retrieval-quality evaluation pipeline for the query-index search library."
requires-python = ">=3.11"
dependencies = [
    "query-index",
    "python-dotenv>=1.0.0",
]

[project.scripts]
query-eval = "query_index_eval.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers --cov=query_index_eval --cov-report=term-missing --cov-fail-under=90"
testpaths = ["tests"]
```

- [ ] **Step 3: Create `.env.example`**

```
# query-index-eval reuses the variables defined by query-index.
# Copy/symlink the values from query-index/.env at the repo root.
AI_FOUNDRY_KEY=
AI_FOUNDRY_ENDPOINT=https://your-foundry.services.ai.azure.com
AI_SEARCH_KEY=
AI_SEARCH_ENDPOINT=https://your-search.search.windows.net
AI_SEARCH_INDEX_NAME=
EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large
EMBEDDING_MODEL_VERSION=1
EMBEDDING_DIMENSIONS=3072
AZURE_OPENAI_API_VERSION=2024-02-01
```

- [ ] **Step 4: Create `README.md`**

````markdown
# query-index-eval

Retrieval-quality evaluation pipeline for the `query-index` search library.

## Public API

```python
from query_index_eval import (
    AggregateMetrics,
    EvalExample,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
    average_precision,
    hit_rate_at_k,
    load_dataset,
    mrr,
    recall_at_k,
    run_eval,
)
```

## CLI

```bash
query-eval curate                        # interactive curation (TTY required)
query-eval eval --top 20                 # run evaluation, write report
query-eval report --compare A.json B.json
query-eval schema-discovery              # dump current index schema
```

## Datasets

Hand-curated golden set lives at `features/query-index-eval/datasets/golden_v1.jsonl`. Gitignored — your curation work stays local. Format: one `EvalExample` per line, append-only with controlled deprecation.

## Reports

Produced under `features/query-index-eval/reports/<utc-timestamp>-golden_v1.json`. Gitignored.

## Tests

```bash
pytest features/query-index-eval/
```

All tests are mocked — `query_index` calls are patched at the import boundary.
````

- [ ] **Step 5: Create empty `__init__.py` files**

```bash
: > features/query-index-eval/src/query_index_eval/__init__.py
: > features/query-index-eval/tests/__init__.py
```

- [ ] **Step 6: Create `tests/conftest.py`**

```python
"""Shared fixtures for query_index_eval tests.

The `query_index` package is patched at module level so that no test in this
suite ever touches Azure. Fixtures expose: a temporary JSONL path, sample
EvalExample objects, and a sample MetricsReport.
"""
from __future__ import annotations

from pathlib import Path

import pytest


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
```

- [ ] **Step 7: Install the (empty) package in editable mode**

```bash
source .venv/bin/activate
pip install -e features/query-index-eval
pip show query-index-eval | head -5
```

Expected: install succeeds, `pip show` reports name `query-index-eval`, version `0.1.0`. The `query-eval` console script is now in PATH.

- [ ] **Step 8: Verify package is importable**

```bash
python -c "import query_index_eval; print(query_index_eval.__file__)"
```

Expected: prints the package path.

- [ ] **Step 9: Commit**

```bash
git add features/query-index-eval/ Makefile  # Makefile is unchanged but git may show no diff — that's fine
# If Makefile shows no diff, just:
git add features/query-index-eval/
git commit -m "feat(query-index-eval): scaffold package (pyproject, README, conftest, console-script)"
```

---

## Task 19: `schema.py` — `EvalExample`, `MetricsReport`, and helpers

Frozen dataclasses for dataset entries and metric reports. Designed so that `dataclasses.asdict` produces JSON-serialisable dicts directly.

**Files:**
- Create: `features/query-index-eval/src/query_index_eval/schema.py`
- Create: `features/query-index-eval/tests/test_schema.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for query_index_eval.schema dataclasses."""
from __future__ import annotations

from dataclasses import asdict

import pytest


def test_eval_example_holds_all_fields(sample_example_dict: dict) -> None:
    from query_index_eval.schema import EvalExample

    e = EvalExample(**sample_example_dict)
    assert e.query_id == "g0001"
    assert e.expected_chunk_ids == ["c42"]
    assert e.source == "curated"
    assert e.deprecated is False


def test_eval_example_round_trip_via_asdict(sample_example_dict: dict) -> None:
    from query_index_eval.schema import EvalExample

    e = EvalExample(**sample_example_dict)
    out = asdict(e)
    assert out["query_id"] == "g0001"
    # Reconstruct
    e2 = EvalExample(**out)
    assert e2 == e


def test_eval_example_is_frozen(sample_example_dict: dict) -> None:
    from dataclasses import FrozenInstanceError

    from query_index_eval.schema import EvalExample

    e = EvalExample(**sample_example_dict)
    with pytest.raises(FrozenInstanceError):
        e.query_id = "g0002"  # type: ignore[misc]


def test_aggregate_metrics_holds_all_metric_fields() -> None:
    from query_index_eval.schema import AggregateMetrics

    m = AggregateMetrics(
        recall_at_5=0.7, recall_at_10=0.85, recall_at_20=0.95,
        map_score=0.65, hit_rate_at_1=0.8, mrr=0.72,
    )
    assert m.recall_at_10 == 0.85
    assert m.mrr == 0.72


def test_operational_metrics_holds_counts_and_latency() -> None:
    from query_index_eval.schema import OperationalMetrics

    m = OperationalMetrics(
        mean_latency_ms=120.0, p95_latency_ms=350.0,
        total_queries=42, total_embedding_calls=42, failure_count=1,
    )
    assert m.total_queries == 42


def test_query_record_holds_per_query_data() -> None:
    from query_index_eval.schema import QueryRecord

    r = QueryRecord(
        query_id="g0001",
        expected_chunk_ids=["c42"],
        retrieved_chunk_ids=["c10", "c42", "c7"],
        ranks=[2],
        hits=[True],
        latency_ms=110.0,
    )
    assert r.ranks == [2]
    assert r.hits == [True]


def test_run_metadata_includes_embedding_and_size_status() -> None:
    from query_index_eval.schema import RunMetadata

    md = RunMetadata(
        dataset_path="features/query-index-eval/datasets/golden_v1.jsonl",
        dataset_size_active=42, dataset_size_deprecated=3,
        embedding_deployment_name="text-embedding-3-large",
        embedding_model_version="1",
        azure_openai_api_version="2024-02-01",
        search_index_name="wizard-1",
        run_timestamp_utc="2026-04-27T10:00:00Z",
        size_status="preliminary",
    )
    assert md.size_status == "preliminary"


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
        "features/query-index-eval/datasets/golden_v1.jsonl",
        42, 3, "text-embedding-3-large", "1", "2024-02-01", "wizard-1",
        "2026-04-27T10:00:00Z", "preliminary",
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

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_schema.py -v 2>&1 | tail -10
```

Expected: 8 errors with `ModuleNotFoundError: No module named 'query_index_eval.schema'`.

- [ ] **Step 3: Implement `schema.py`**

```python
"""Frozen dataclasses for the eval pipeline.

Designed so that `dataclasses.asdict` produces a JSON-serialisable structure.
EvalExample mirrors the JSONL row schema documented in the design spec; the
metric/report dataclasses compose into a single MetricsReport that the CLI
serialises to disk.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvalExample:
    query_id: str
    query: str
    expected_chunk_ids: list[str]
    source: str
    chunk_hashes: dict[str, str]
    filter: str | None
    deprecated: bool
    created_at: str
    notes: str | None


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
    size_status: str  # "indicative" | "preliminary" | "reportable"


@dataclass(frozen=True)
class QueryRecord:
    query_id: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    ranks: list[int]   # 1-based rank of each expected; -1 if not retrieved
    hits: list[bool]   # parallel to expected_chunk_ids
    latency_ms: float


@dataclass(frozen=True)
class MetricsReport:
    aggregate: AggregateMetrics
    operational: OperationalMetrics
    metadata: RunMetadata
    per_query: list[QueryRecord] = field(default_factory=list)
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_schema.py -v 2>&1 | tail -10
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/schema.py features/query-index-eval/tests/test_schema.py
git commit -m "feat(eval): add EvalExample, MetricsReport, and supporting dataclasses"
```

---

## Task 20: `datasets.py` — JSONL load/save with mutation enforcement

Public API: `load_dataset(path) -> list[EvalExample]`, `append_example(path, example)`, `deprecate_example(path, query_id)`. Direct file edits are not protected — but in-process, only these functions touch the file, and they enforce the rules from the spec.

**Files:**
- Create: `features/query-index-eval/src/query_index_eval/datasets.py`
- Create: `features/query-index-eval/tests/test_datasets.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for query_index_eval.datasets — JSONL I/O with mutation rules."""
from __future__ import annotations

from pathlib import Path

import pytest


def _example(qid: str = "g0001", deprecated: bool = False) -> dict:
    return {
        "query_id": qid,
        "query": f"Question {qid}?",
        "expected_chunk_ids": [f"c{qid[1:]}"],
        "source": "curated",
        "chunk_hashes": {f"c{qid[1:]}": f"sha256:hash_{qid}"},
        "filter": None,
        "deprecated": deprecated,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }


def test_load_dataset_returns_empty_list_when_file_missing(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import load_dataset

    assert load_dataset(tmp_dataset_path) == []


def test_load_dataset_parses_jsonl_into_eval_examples(tmp_dataset_path: Path) -> None:
    import json

    from query_index_eval.datasets import load_dataset
    from query_index_eval.schema import EvalExample

    rows = [_example("g0001"), _example("g0002")]
    tmp_dataset_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    result = load_dataset(tmp_dataset_path)
    assert len(result) == 2
    assert all(isinstance(e, EvalExample) for e in result)
    assert {e.query_id for e in result} == {"g0001", "g0002"}


def test_append_example_creates_file_if_missing(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import append_example, load_dataset
    from query_index_eval.schema import EvalExample

    e = EvalExample(**_example("g0001"))
    append_example(tmp_dataset_path, e)
    assert tmp_dataset_path.exists()
    loaded = load_dataset(tmp_dataset_path)
    assert len(loaded) == 1
    assert loaded[0].query_id == "g0001"


def test_append_example_appends_subsequent_rows(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import append_example, load_dataset
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001")))
    append_example(tmp_dataset_path, EvalExample(**_example("g0002")))
    loaded = load_dataset(tmp_dataset_path)
    assert [e.query_id for e in loaded] == ["g0001", "g0002"]


def test_append_example_rejects_duplicate_query_id(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import DatasetMutationError, append_example
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001")))
    with pytest.raises(DatasetMutationError, match="g0001"):
        append_example(tmp_dataset_path, EvalExample(**_example("g0001")))


def test_deprecate_example_flips_flag_in_place(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import (
        append_example,
        deprecate_example,
        load_dataset,
    )
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001")))
    append_example(tmp_dataset_path, EvalExample(**_example("g0002")))

    deprecate_example(tmp_dataset_path, "g0001")
    loaded = load_dataset(tmp_dataset_path)
    by_id = {e.query_id: e for e in loaded}
    assert by_id["g0001"].deprecated is True
    assert by_id["g0002"].deprecated is False


def test_deprecate_example_raises_when_id_missing(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import DatasetMutationError, deprecate_example

    tmp_dataset_path.write_text("")  # empty file
    with pytest.raises(DatasetMutationError, match="not found"):
        deprecate_example(tmp_dataset_path, "g0099")


def test_deprecate_example_refuses_to_undeprecate(tmp_dataset_path: Path) -> None:
    """Once deprecated, an example stays deprecated — deprecate_example called
    on an already-deprecated id is a no-op (or raises, depending on
    implementation choice; here we expect a no-op-or-raise)."""
    from query_index_eval.datasets import (
        DatasetMutationError,
        append_example,
        deprecate_example,
        load_dataset,
    )
    from query_index_eval.schema import EvalExample

    append_example(
        tmp_dataset_path, EvalExample(**_example("g0001", deprecated=True))
    )
    with pytest.raises(DatasetMutationError, match="already deprecated"):
        deprecate_example(tmp_dataset_path, "g0001")
    loaded = load_dataset(tmp_dataset_path)
    assert loaded[0].deprecated is True
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_datasets.py -v 2>&1 | tail -15
```

Expected: 8 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `datasets.py`**

```python
"""JSONL load/save for EvalExamples with controlled-mutation rules.

Public API:
- `load_dataset(path)` reads JSONL into a list of EvalExample (empty if file missing).
- `append_example(path, example)` appends one row; raises on duplicate query_id.
- `deprecate_example(path, query_id)` flips the example's `deprecated` flag to
  True. Refuses to operate on an already-deprecated row (the rule is "deprecate
  is one-way"); raises if the id is not found.

Direct file edits are not protected. The convention is: only these three
functions touch the JSONL file in process. The rules implement the
"controlled mutation" contract from the design spec.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from query_index_eval.schema import EvalExample


class DatasetMutationError(Exception):
    """Raised when a mutation violates the controlled-mutation rules."""


def load_dataset(path: Path) -> list[EvalExample]:
    if not path.exists():
        return []
    examples: list[EvalExample] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            examples.append(EvalExample(**json.loads(line)))
    return examples


def append_example(path: Path, example: EvalExample) -> None:
    existing = load_dataset(path)
    if any(e.query_id == example.query_id for e in existing):
        raise DatasetMutationError(
            f"query_id {example.query_id!r} already exists in {path}; "
            f"deprecate-and-append-new instead of editing in place"
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")


def deprecate_example(path: Path, query_id: str) -> None:
    existing = load_dataset(path)
    found = False
    new_rows: list[EvalExample] = []
    for e in existing:
        if e.query_id == query_id:
            found = True
            if e.deprecated:
                raise DatasetMutationError(
                    f"query_id {query_id!r} is already deprecated; "
                    f"deprecation is one-way (no un-deprecate in v1)"
                )
            new_rows.append(
                EvalExample(
                    query_id=e.query_id,
                    query=e.query,
                    expected_chunk_ids=e.expected_chunk_ids,
                    source=e.source,
                    chunk_hashes=e.chunk_hashes,
                    filter=e.filter,
                    deprecated=True,
                    created_at=e.created_at,
                    notes=e.notes,
                )
            )
        else:
            new_rows.append(e)
    if not found:
        raise DatasetMutationError(
            f"query_id {query_id!r} not found in {path}; cannot deprecate"
        )
    with path.open("w", encoding="utf-8") as f:
        for e in new_rows:
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_datasets.py -v 2>&1 | tail -15
```

Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/datasets.py features/query-index-eval/tests/test_datasets.py
git commit -m "feat(eval): add JSONL load/append/deprecate with controlled-mutation rules"
```

---

## Task 21: `metrics.py` — pure metric functions

Public API: `recall_at_k`, `hit_rate_at_k`, `mrr`, `average_precision`, plus a `mean_average_precision` aggregate. All pure, no I/O, no Azure. The module that earns the most rigour because correctness here is the foundation of every report.

**Files:**
- Create: `features/query-index-eval/src/query_index_eval/metrics.py`
- Create: `features/query-index-eval/tests/test_metrics.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for query_index_eval.metrics.

Each metric tested with:
- Single-relevant scenarios (the synthetic-style case)
- Multi-relevant scenarios (the golden-style case)
- Edge: empty expected, empty retrieved, all-miss, all-hit, partial-hit
- Order sensitivity where relevant (MRR, MAP)
"""
from __future__ import annotations

import pytest


# ---------- recall_at_k ----------

@pytest.mark.parametrize(
    "expected,retrieved,k,want",
    [
        ({"a"}, ["a"], 1, 1.0),
        ({"a"}, ["b"], 1, 0.0),
        ({"a"}, ["b", "a"], 2, 1.0),
        ({"a"}, ["b", "a"], 1, 0.0),
        ({"a", "b"}, ["a", "c"], 2, 0.5),
        ({"a", "b"}, ["a", "b", "c"], 3, 1.0),
        ({"a", "b", "c"}, ["d", "e", "f"], 3, 0.0),
        (set(), [], 5, 0.0),
        (set(), ["a"], 5, 0.0),
        ({"a"}, [], 5, 0.0),
    ],
)
def test_recall_at_k(expected, retrieved, k, want) -> None:
    from query_index_eval.metrics import recall_at_k

    assert recall_at_k(expected, retrieved, k) == pytest.approx(want)


# ---------- hit_rate_at_k ----------

@pytest.mark.parametrize(
    "expected,retrieved,k,want",
    [
        ({"a"}, ["a"], 1, 1.0),
        ({"a"}, ["b"], 1, 0.0),
        ({"a"}, ["b", "a"], 2, 1.0),
        ({"a", "b"}, ["a", "c"], 2, 1.0),
        ({"a", "b"}, ["c", "d"], 2, 0.0),
        (set(), ["a"], 5, 0.0),
        ({"a"}, [], 5, 0.0),
    ],
)
def test_hit_rate_at_k(expected, retrieved, k, want) -> None:
    from query_index_eval.metrics import hit_rate_at_k

    assert hit_rate_at_k(expected, retrieved, k) == pytest.approx(want)


# ---------- MRR ----------

@pytest.mark.parametrize(
    "expected,retrieved,want",
    [
        ({"a"}, ["a"], 1.0),
        ({"a"}, ["b", "a"], 0.5),
        ({"a"}, ["b", "c", "a"], 1 / 3),
        ({"a", "b"}, ["b", "a"], 1.0),  # earliest of any expected
        ({"a", "b"}, ["c", "a", "b"], 0.5),
        ({"a"}, ["b", "c", "d"], 0.0),
        (set(), ["a"], 0.0),
    ],
)
def test_mrr(expected, retrieved, want) -> None:
    from query_index_eval.metrics import mrr

    assert mrr(expected, retrieved) == pytest.approx(want)


# ---------- Average Precision ----------

def test_average_precision_single_relevant_at_top() -> None:
    from query_index_eval.metrics import average_precision

    # one relevant at rank 1 -> AP = 1/1 / 1 = 1.0
    assert average_precision({"a"}, ["a", "b", "c"]) == pytest.approx(1.0)


def test_average_precision_single_relevant_at_rank_3() -> None:
    from query_index_eval.metrics import average_precision

    # one relevant at rank 3 -> precision at hit = 1/3, mean = 1/3
    assert average_precision({"a"}, ["b", "c", "a"]) == pytest.approx(1 / 3)


def test_average_precision_two_relevant_well_ranked() -> None:
    from query_index_eval.metrics import average_precision

    # rank 1: precision = 1/1; rank 2: precision = 2/2; mean = (1 + 1) / 2 = 1.0
    assert average_precision({"a", "b"}, ["a", "b", "c"]) == pytest.approx(1.0)


def test_average_precision_two_relevant_with_gap() -> None:
    from query_index_eval.metrics import average_precision

    # rank 1: precision = 1/1; rank 3: precision = 2/3; mean = (1 + 2/3) / 2 = 5/6
    assert average_precision({"a", "b"}, ["a", "x", "b"]) == pytest.approx(5 / 6)


def test_average_precision_zero_when_no_hit() -> None:
    from query_index_eval.metrics import average_precision

    assert average_precision({"a"}, ["b", "c"]) == 0.0


def test_average_precision_zero_when_expected_empty() -> None:
    from query_index_eval.metrics import average_precision

    assert average_precision(set(), ["a"]) == 0.0


# ---------- mean_average_precision ----------

def test_mean_average_precision_averages_per_query_ap() -> None:
    from query_index_eval.metrics import mean_average_precision

    pairs = [
        ({"a"}, ["a", "b"]),    # AP = 1.0
        ({"x"}, ["y", "x"]),    # AP = 1/2
        ({"q"}, ["w", "e", "r"]),  # AP = 0.0
    ]
    # mean of [1.0, 0.5, 0.0] = 0.5
    assert mean_average_precision(pairs) == pytest.approx(0.5)


def test_mean_average_precision_empty_input_is_zero() -> None:
    from query_index_eval.metrics import mean_average_precision

    assert mean_average_precision([]) == 0.0
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_metrics.py -v 2>&1 | tail -15
```

Expected: ~30 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `metrics.py`**

```python
"""Pure IR metric functions over (expected, retrieved) chunk-id collections.

No I/O, no Azure, no global state. Every function accepts a `set[str]` of
expected chunk_ids and a `list[str]` of retrieved chunk_ids in rank order.
"""
from __future__ import annotations

from collections.abc import Iterable


def recall_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return 0.0
    top_k = set(retrieved[:k])
    return len(expected & top_k) / len(expected)


def hit_rate_at_k(expected: set[str], retrieved: list[str], k: int) -> float:
    if not expected:
        return 0.0
    top_k = set(retrieved[:k])
    return 1.0 if expected & top_k else 0.0


def mrr(expected: set[str], retrieved: list[str]) -> float:
    if not expected:
        return 0.0
    for i, item in enumerate(retrieved, start=1):
        if item in expected:
            return 1.0 / i
    return 0.0


def average_precision(expected: set[str], retrieved: list[str]) -> float:
    """Precision averaged at the ranks where each relevant item appears.

    Standard IR definition:
        AP = (1 / |expected|) * sum over k where retrieved[k-1] is relevant
              of (number-of-hits-up-to-k / k)
    """
    if not expected:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for i, item in enumerate(retrieved, start=1):
        if item in expected:
            hits += 1
            precision_sum += hits / i
    return precision_sum / len(expected) if precision_sum else 0.0


def mean_average_precision(
    pairs: Iterable[tuple[set[str], list[str]]],
) -> float:
    pair_list = list(pairs)
    if not pair_list:
        return 0.0
    return sum(average_precision(e, r) for e, r in pair_list) / len(pair_list)
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_metrics.py -v 2>&1 | tail -10
```

Expected: ~30 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/metrics.py features/query-index-eval/tests/test_metrics.py
git commit -m "feat(eval): add pure IR metrics (recall@k, hit@k, MRR, AP, MAP)"
```

---

## Task 22: `runner.py` — `run_eval`

Loads a dataset, runs each non-deprecated example through `query_index.hybrid_search`, computes per-query records and aggregates, and returns a `MetricsReport`. Sample-size flagging is computed here (`indicative` / `preliminary` / `reportable`).

**Files:**
- Create: `features/query-index-eval/src/query_index_eval/runner.py`
- Create: `features/query-index-eval/tests/test_runner.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for query_index_eval.runner.run_eval()."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def _write_dataset(path: Path, rows: list[dict]) -> None:
    import json
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _example_dict(qid: str, expected: list[str], deprecated: bool = False) -> dict:
    return {
        "query_id": qid,
        "query": f"Q? {qid}",
        "expected_chunk_ids": expected,
        "source": "curated",
        "chunk_hashes": {c: f"sha256:hash_{c}" for c in expected},
        "filter": None,
        "deprecated": deprecated,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }


def _hit(chunk_id: str, score: float = 0.5):
    """Build a minimal SearchHit-like object."""
    from query_index.types import SearchHit
    return SearchHit(chunk_id=chunk_id, title="t", chunk="x", score=score)


def test_run_eval_skips_deprecated_examples(tmp_dataset_path: Path, env_vars: dict) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [
            _example_dict("g0001", ["c1"]),
            _example_dict("g0002", ["c2"], deprecated=True),
        ],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert len(report.per_query) == 1
    assert report.per_query[0].query_id == "g0001"
    assert report.metadata.dataset_size_active == 1
    assert report.metadata.dataset_size_deprecated == 1


def test_run_eval_records_ranks_and_hits_per_query(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(tmp_dataset_path, [_example_dict("g0001", ["c2", "c4"])])

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3, 4, 5]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    record = report.per_query[0]
    assert record.expected_chunk_ids == ["c2", "c4"]
    assert record.retrieved_chunk_ids == ["c1", "c2", "c3", "c4", "c5"]
    assert record.ranks == [2, 4]
    assert record.hits == [True, True]


def test_run_eval_records_minus_one_rank_when_expected_not_found(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(tmp_dataset_path, [_example_dict("g0001", ["c99"])])

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    record = report.per_query[0]
    assert record.ranks == [-1]
    assert record.hits == [False]


def test_run_eval_aggregates_metrics_across_queries(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [
            _example_dict("g0001", ["c1"]),  # found at rank 1
            _example_dict("g0002", ["c2"]),  # found at rank 2
            _example_dict("g0003", ["c99"]),  # not found
        ],
    )

    call_to_results = {
        "Q? g0001": [_hit("c1"), _hit("c5"), _hit("c6")],
        "Q? g0002": [_hit("c4"), _hit("c2"), _hit("c6")],
        "Q? g0003": [_hit("c4"), _hit("c5"), _hit("c6")],
    }

    def fake_search(query, top, filter=None, cfg=None):
        return call_to_results[query]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    # Hit rate@1: 1/3 (only g0001 has c1 at rank 1)
    assert report.aggregate.hit_rate_at_1 == pytest.approx(1 / 3)
    # MRR: (1 + 1/2 + 0) / 3 = 0.5
    assert report.aggregate.mrr == pytest.approx(0.5)
    # Recall@5: g0001 1.0, g0002 1.0, g0003 0.0; mean = 2/3
    assert report.aggregate.recall_at_5 == pytest.approx(2 / 3)


def test_run_eval_assigns_size_status_indicative_for_small_n(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [_example_dict(f"g{i:04d}", ["c1"]) for i in range(5)],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.size_status == "indicative"


def test_run_eval_assigns_size_status_preliminary_in_30_to_99(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [_example_dict(f"g{i:04d}", ["c1"]) for i in range(50)],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.size_status == "preliminary"


def test_run_eval_assigns_size_status_reportable_at_100(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [_example_dict(f"g{i:04d}", ["c1"]) for i in range(100)],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.size_status == "reportable"


def test_run_eval_metadata_includes_embedding_and_index_info(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(tmp_dataset_path, [_example_dict("g0001", ["c1"])])

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    md = report.metadata
    assert md.embedding_deployment_name == env_vars["EMBEDDING_DEPLOYMENT_NAME"]
    assert md.embedding_model_version == env_vars["EMBEDDING_MODEL_VERSION"]
    assert md.azure_openai_api_version == env_vars["AZURE_OPENAI_API_VERSION"]
    assert md.search_index_name == env_vars["AI_SEARCH_INDEX_NAME"]
    assert md.run_timestamp_utc.endswith("Z")  # ISO-8601 UTC


def test_run_eval_passes_filter_per_example_when_set(
    tmp_dataset_path: Path, env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    rows = [_example_dict("g0001", ["c1"])]
    rows[0]["filter"] = "category eq 'manual'"
    _write_dataset(tmp_dataset_path, rows)

    captured: dict = {}

    def fake_search(query, top, filter=None, cfg=None):
        captured["filter"] = filter
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        run_eval(tmp_dataset_path, top_k_max=20)

    assert captured["filter"] == "category eq 'manual'"
```

The test file is missing a `pytest` import — add `import pytest` at the top:

```python
"""Tests for query_index_eval.runner.run_eval()."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
```

(Apologies for forgetting — make sure your final test file has it.)

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_runner.py -v 2>&1 | tail -15
```

Expected: 9 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `runner.py`**

```python
"""Evaluation orchestration.

Loads a dataset, runs each non-deprecated example through query_index's
hybrid search, computes per-query records and aggregate metrics, and returns
a MetricsReport ready for serialization.
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from query_index import Config, hybrid_search

from query_index_eval.datasets import load_dataset
from query_index_eval.metrics import (
    average_precision,
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
)
from query_index_eval.schema import (
    AggregateMetrics,
    EvalExample,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
)


SIZE_THRESHOLD_INDICATIVE = 30
SIZE_THRESHOLD_REPORTABLE = 100


def _size_status(n: int) -> str:
    if n < SIZE_THRESHOLD_INDICATIVE:
        return "indicative"
    if n < SIZE_THRESHOLD_REPORTABLE:
        return "preliminary"
    return "reportable"


def _ranks_and_hits(
    expected: list[str], retrieved: list[str]
) -> tuple[list[int], list[bool]]:
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


def run_eval(
    dataset_path: Path,
    top_k_max: int = 20,
    filter_default: str | None = None,
    cfg: Config | None = None,
) -> MetricsReport:
    if cfg is None:
        cfg = Config.from_env()

    all_examples = load_dataset(dataset_path)
    deprecated_count = sum(1 for e in all_examples if e.deprecated)
    active: list[EvalExample] = [e for e in all_examples if not e.deprecated]

    per_query: list[QueryRecord] = []
    latencies: list[float] = []
    failures = 0

    for example in active:
        try:
            t0 = time.perf_counter()
            hits = hybrid_search(
                example.query,
                top=top_k_max,
                filter=example.filter or filter_default,
                cfg=cfg,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            retrieved_ids = [h.chunk_id for h in hits]
            ranks, hit_flags = _ranks_and_hits(example.expected_chunk_ids, retrieved_ids)
            per_query.append(
                QueryRecord(
                    query_id=example.query_id,
                    expected_chunk_ids=list(example.expected_chunk_ids),
                    retrieved_chunk_ids=retrieved_ids,
                    ranks=ranks,
                    hits=hit_flags,
                    latency_ms=latency_ms,
                )
            )
            latencies.append(latency_ms)
        except Exception:  # noqa: BLE001 — operational counter; details preserved by Azure SDK
            failures += 1

    # Aggregate metrics
    pairs = [(set(r.expected_chunk_ids), r.retrieved_chunk_ids) for r in per_query]
    aggregate = AggregateMetrics(
        recall_at_5=_mean(recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 5) for r in per_query),
        recall_at_10=_mean(recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 10) for r in per_query),
        recall_at_20=_mean(recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 20) for r in per_query),
        map_score=mean_average_precision(pairs),
        hit_rate_at_1=_mean(hit_rate_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 1) for r in per_query),
        mrr=_mean(mrr(set(r.expected_chunk_ids), r.retrieved_chunk_ids) for r in per_query),
    )

    operational = OperationalMetrics(
        mean_latency_ms=statistics.fmean(latencies) if latencies else 0.0,
        p95_latency_ms=_p95(latencies),
        total_queries=len(per_query),
        total_embedding_calls=len(per_query),  # one embedding per hybrid_search
        failure_count=failures,
    )

    metadata = RunMetadata(
        dataset_path=str(dataset_path),
        dataset_size_active=len(active),
        dataset_size_deprecated=deprecated_count,
        embedding_deployment_name=cfg.embedding_deployment_name,
        embedding_model_version=cfg.embedding_model_version,
        azure_openai_api_version=cfg.azure_openai_api_version,
        search_index_name=cfg.ai_search_index_name,
        run_timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        size_status=_size_status(len(active)),
    )

    return MetricsReport(
        aggregate=aggregate,
        operational=operational,
        metadata=metadata,
        per_query=per_query,
    )


def _mean(values) -> float:  # type: ignore[no-untyped-def]
    vs = list(values)
    return sum(vs) / len(vs) if vs else 0.0


def _p95(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    sorted_l = sorted(latencies)
    idx = int(0.95 * (len(sorted_l) - 1))
    return sorted_l[idx]
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_runner.py -v 2>&1 | tail -15
```

Expected: 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/runner.py features/query-index-eval/tests/test_runner.py
git commit -m "feat(eval): add run_eval orchestration with sample-size flagging"
```

---

## Task 23: `curate.py` — interactive curation CLI

Refuses to start without an interactive TTY. Substring check guards against accidental copy-paste of chunk text into the user-written query field.

**Files:**
- Create: `features/query-index-eval/src/query_index_eval/curate.py`
- Create: `features/query-index-eval/tests/test_curate.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for query_index_eval.curate.

Most of curate's surface is interactive, so we test the pure-logic helpers
plus the substring check in isolation. The interactive run loop is not
exercised end-to-end here — that's verified manually by the user in their
real workspace.
"""
from __future__ import annotations

import pytest


def test_query_substring_check_flags_long_overlap() -> None:
    from query_index_eval.curate import query_substring_overlap

    chunk = "Der Tragkorbdurchmesser beträgt 850 mm gemäß DIN 15020."
    leaky_query = "Tragkorbdurchmesser beträgt 850 mm gemäß DIN 15020"
    assert query_substring_overlap(leaky_query, chunk) >= 30


def test_query_substring_check_passes_short_keyword_overlap() -> None:
    from query_index_eval.curate import query_substring_overlap

    chunk = "Der Tragkorbdurchmesser beträgt 850 mm gemäß DIN 15020."
    safe_query = "Wo steht der Tragkorbdurchmesser?"
    # Overlap "Tragkorbdurchmesser" is 19 chars — below the 30-char heuristic
    assert query_substring_overlap(safe_query, chunk) < 30


def test_query_substring_check_zero_when_disjoint() -> None:
    from query_index_eval.curate import query_substring_overlap

    assert query_substring_overlap("etwas anderes", "Tragkorb") == 0


def test_require_tty_raises_when_stdin_not_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from query_index_eval.curate import require_interactive_tty

    class FakeStdin:
        def fileno(self) -> int:
            return 999  # non-tty fd

    monkeypatch.setattr("sys.stdin", FakeStdin())
    monkeypatch.setattr("os.isatty", lambda _fd: False)
    with pytest.raises(SystemExit) as excinfo:
        require_interactive_tty()
    assert excinfo.value.code == 1


def test_require_tty_passes_when_stdin_is_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from query_index_eval.curate import require_interactive_tty

    monkeypatch.setattr("os.isatty", lambda _fd: True)
    require_interactive_tty()  # should not raise
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_curate.py -v 2>&1 | tail -10
```

Expected: 5 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `curate.py`**

```python
"""Interactive curation CLI helpers.

Two mechanical safeties for the curation flow:
1. require_interactive_tty() — refuses to run if stdin is not a tty.
   Prevents accidental invocation through a non-interactive shell (in
   particular, an LLM agent's Bash tool would have no tty here).
2. query_substring_overlap() — heuristic detection of accidental copy-paste
   of chunk text into the user-written query.

The full interactive loop is implemented in `interactive_curate()` but is
exercised by the user manually rather than in unit tests.
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from query_index import Config, get_chunk, hybrid_search, sample_chunks

from query_index_eval.datasets import append_example
from query_index_eval.schema import EvalExample


SUBSTRING_OVERLAP_THRESHOLD = 30
"""If a user-written query shares a contiguous substring of this many
characters or more with the chunk text, warn before saving — that's almost
certainly an accidental copy-paste rather than a real user query."""


def require_interactive_tty() -> None:
    """Exit with code 1 if stdin is not an interactive TTY."""
    try:
        is_tty = os.isatty(sys.stdin.fileno())
    except (AttributeError, OSError, ValueError):
        is_tty = False
    if not is_tty:
        print(
            "ERROR: query-eval curate requires an interactive TTY. "
            "Run it in a regular terminal — not through a non-interactive shell, "
            "subprocess, or LLM agent tool.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def query_substring_overlap(query: str, chunk_text: str) -> int:
    """Return the length of the longest contiguous substring of `query` that
    also appears in `chunk_text`. Linear scan over query positions; quadratic
    in the worst case but query is short. Used as a copy-paste heuristic."""
    if not query or not chunk_text:
        return 0
    longest = 0
    n = len(query)
    for start in range(n):
        end = start + longest + 1
        # Try to extend matches starting at `start`
        while end <= n and query[start:end] in chunk_text:
            longest = end - start
            end += 1
    return longest


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def _next_query_id(existing_ids: set[str]) -> str:
    n = 1
    while f"g{n:04d}" in existing_ids:
        n += 1
    return f"g{n:04d}"


def interactive_curate(
    dataset_path: Path,
    chunk_id: str | None = None,
    seed: int | None = None,
    cfg: Config | None = None,
) -> None:
    require_interactive_tty()
    if cfg is None:
        cfg = Config.from_env()

    print(
        "REMINDER: never paste chunk text into Claude or any other shared chat. "
        "Reference chunks only by chunk_id.\n"
    )

    if chunk_id is not None:
        chunk = get_chunk(chunk_id, cfg)
    else:
        seed_val = seed if seed is not None else int(datetime.now(timezone.utc).timestamp())
        [chunk] = sample_chunks(1, seed=seed_val, cfg=cfg)

    print("=" * 70)
    print(f"chunk_id: {chunk.chunk_id}")
    print(f"title:    {chunk.title}")
    print("-" * 70)
    print(chunk.chunk)
    print("=" * 70)

    query = input("Write a query this chunk should answer:\n> ").strip()

    overlap = query_substring_overlap(query, chunk.chunk)
    if overlap >= SUBSTRING_OVERLAP_THRESHOLD:
        print(
            f"WARNING: your query shares a {overlap}-char substring with the chunk "
            "— this looks like accidental copy-paste."
        )
        if input("Save anyway? [y/N] ").strip().lower() != "y":
            print("Aborted; nothing saved.")
            return

    show_search = input("Run hybrid_search on this query to preview top-5? [y/N] ").strip().lower()
    if show_search == "y":
        hits = hybrid_search(query, top=5, cfg=cfg)
        print("Top 5 retrieved:")
        for i, h in enumerate(hits, start=1):
            print(f"  {i}. {h.chunk_id}  (score {h.score:.3f})")

    if input(f"Add example to {dataset_path}? [y/N] ").strip().lower() != "y":
        print("Aborted; nothing saved.")
        return

    # Look up existing ids to avoid collision
    existing_ids: set[str] = set()
    if dataset_path.exists():
        from query_index_eval.datasets import load_dataset
        existing_ids = {e.query_id for e in load_dataset(dataset_path)}

    example = EvalExample(
        query_id=_next_query_id(existing_ids),
        query=query,
        expected_chunk_ids=[chunk.chunk_id],
        source="curated",
        chunk_hashes={chunk.chunk_id: _hash(chunk.chunk)},
        filter=None,
        deprecated=False,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        notes=None,
    )
    append_example(dataset_path, example)
    print(f"Saved {example.query_id} to {dataset_path}")
    print(
        "\nREMINDER: never paste chunk text into Claude or any other shared chat. "
        "Reference chunks only by chunk_id."
    )
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_curate.py -v 2>&1 | tail -10
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/curate.py features/query-index-eval/tests/test_curate.py
git commit -m "feat(eval): add curate CLI with TTY guard and substring-overlap check"
```

---

## Task 24: `cli.py` — entry-point dispatcher

The `query-eval` console script. Subcommands: `curate`, `eval`, `report`, `schema-discovery`. Loads `.env` from repo root once. Tested at the dispatch layer — each subcommand's logic is in its own module already.

**Files:**
- Create: `features/query-index-eval/src/query_index_eval/cli.py`
- Create: `features/query-index-eval/tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for the query-eval CLI dispatcher."""
from __future__ import annotations

from unittest.mock import patch


def test_cli_dispatches_curate(monkeypatch) -> None:
    from query_index_eval.cli import main

    with patch("query_index_eval.cli.interactive_curate") as mock_curate:
        rc = main(["curate", "--dataset", "ds.jsonl"])
    assert rc == 0
    mock_curate.assert_called_once()


def test_cli_dispatches_eval_with_default_top_k(monkeypatch) -> None:
    from query_index_eval.cli import main

    with patch("query_index_eval.cli.run_eval") as mock_run, patch(
        "query_index_eval.cli._write_report"
    ):
        rc = main(["eval", "--dataset", "ds.jsonl"])
    assert rc == 0
    args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 20  # default


def test_cli_dispatches_eval_passes_top_argument(monkeypatch) -> None:
    from query_index_eval.cli import main

    with patch("query_index_eval.cli.run_eval") as mock_run, patch(
        "query_index_eval.cli._write_report"
    ):
        main(["eval", "--dataset", "ds.jsonl", "--top", "10"])
    args, kwargs = mock_run.call_args
    assert kwargs["top_k_max"] == 10


def test_cli_dispatches_schema_discovery(monkeypatch) -> None:
    from query_index_eval.cli import main

    with patch("query_index_eval.cli.print_index_schema") as mock_schema:
        rc = main(["schema-discovery"])
    assert rc == 0
    mock_schema.assert_called_once()


def test_cli_unknown_subcommand_returns_nonzero(monkeypatch) -> None:
    from query_index_eval.cli import main

    rc = main(["unknown-thing"])
    assert rc != 0
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_cli.py -v 2>&1 | tail -10
```

Expected: 5 errors with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `cli.py`**

```python
"""query-eval CLI entry point."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from query_index import Config, print_index_schema as _print_index_schema_impl  # type: ignore[attr-defined]

from query_index_eval.curate import interactive_curate
from query_index_eval.runner import run_eval
from query_index_eval.schema import MetricsReport


# Re-bind for patchability in tests
print_index_schema = _print_index_schema_impl


DEFAULT_DATASET = Path("features/query-index-eval/datasets/golden_v1.jsonl")
DEFAULT_REPORTS_DIR = Path("features/query-index-eval/reports")


def _write_report(report: MetricsReport, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dataset_stem = Path(report.metadata.dataset_path).stem
    out_path = out_dir / f"{timestamp}-{dataset_stem}.json"
    out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    return out_path


def _print_summary(report: MetricsReport, out_path: Path) -> None:
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
    """Load .env from repo root (or current dir as fallback) once."""
    repo_root = Path(__file__).resolve().parents[4]  # src/query_index_eval/cli.py -> repo root
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()  # falls back to default search


def _cmd_curate(args: argparse.Namespace) -> int:
    interactive_curate(
        dataset_path=Path(args.dataset),
        chunk_id=args.chunk_id,
        seed=args.seed,
    )
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    report = run_eval(
        dataset_path=Path(args.dataset),
        top_k_max=args.top,
        cfg=cfg,
    )
    out_path = _write_report(report, DEFAULT_REPORTS_DIR)
    _print_summary(report, out_path)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
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


def _cmd_schema_discovery(args: argparse.Namespace) -> int:
    cfg = Config.from_env()
    print_index_schema(args.index_name or cfg.ai_search_index_name, cfg)
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(prog="query-eval")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_curate = sub.add_parser("curate", help="Interactive curation (TTY required)")
    p_curate.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p_curate.add_argument("--chunk-id", default=None)
    p_curate.add_argument("--seed", type=int, default=None)
    p_curate.set_defaults(func=_cmd_curate)

    p_eval = sub.add_parser("eval", help="Run evaluation, write report")
    p_eval.add_argument("--dataset", default=str(DEFAULT_DATASET))
    p_eval.add_argument("--top", type=int, default=20)
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
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: the `print_index_schema` import alias above is required because `query_index.print_index_schema` is exposed at the submodule level but not in the public `__init__`. Adjust the import based on what's actually exported. If it's NOT in the public API, import it as `from query_index.schema_discovery import print_index_schema as _print_index_schema_impl`.

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_cli.py -v 2>&1 | tail -10
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/cli.py features/query-index-eval/tests/test_cli.py
git commit -m "feat(eval): add query-eval CLI dispatcher (curate/eval/report/schema-discovery)"
```

---

## Task 25: Public API in `query_index_eval/__init__.py`

- [ ] **Step 1: Write failing tests**

Create `features/query-index-eval/tests/test_public_api.py`:

```python
"""Tests for the re-exported public API at query_index_eval.__init__."""
from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index_eval

    expected = {
        "AggregateMetrics",
        "EvalExample",
        "MetricsReport",
        "OperationalMetrics",
        "QueryRecord",
        "RunMetadata",
        "average_precision",
        "hit_rate_at_k",
        "load_dataset",
        "mean_average_precision",
        "mrr",
        "recall_at_k",
        "run_eval",
    }
    missing = expected - set(dir(query_index_eval))
    assert not missing, f"Missing public exports: {missing}"
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_public_api.py -v 2>&1 | tail -10
```

Expected: failure citing missing exports.

- [ ] **Step 3: Populate `__init__.py`**

Replace `features/query-index-eval/src/query_index_eval/__init__.py` content with:

```python
"""Public API for the query_index_eval package."""
from query_index_eval.datasets import load_dataset
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
    EvalExample,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
)

__all__ = [
    "AggregateMetrics",
    "EvalExample",
    "MetricsReport",
    "OperationalMetrics",
    "QueryRecord",
    "RunMetadata",
    "average_precision",
    "hit_rate_at_k",
    "load_dataset",
    "mean_average_precision",
    "mrr",
    "recall_at_k",
    "run_eval",
]
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_public_api.py -v 2>&1 | tail -10
```

Expected: 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/__init__.py features/query-index-eval/tests/test_public_api.py
git commit -m "feat(eval): expose public API"
```

---

## Task 26: Phase-2 acceptance check (verification only)

- [ ] **Step 1: Full test run on the eval package**

```bash
pytest features/query-index-eval/ --cov=query_index_eval --cov-report=term-missing 2>&1 | tail -30
```

Expected: every test passes, coverage ≥ 90 % on `src/query_index_eval/`.

- [ ] **Step 2: Combined test run on both packages**

```bash
pytest features/ 2>&1 | tail -10
```

Expected: ~85+ tests passing total.

- [ ] **Step 3: Lint clean across all features**

```bash
make lint
```

Expected: zero issues.

- [ ] **Step 4: Pre-commit on all files**

```bash
pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 5: Verify the console script works**

```bash
query-eval --help
```

Expected: argparse help text listing the four subcommands.

- [ ] **Step 6: Verify `query-eval schema-discovery` fails gracefully without `.env`**

```bash
query-eval schema-discovery 2>&1 | tail -5
```

Expected: a clear "missing environment variable" error (since no `.env` is present in this development workspace). Returns exit 1, doesn't crash.

End of Phase 2.

---

# Phase 3 — Acceptance and PR

## Task 27: Spec acceptance criteria check

Walk through the seven acceptance criteria from `docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md` (the "Acceptance criteria" section) and confirm each one in turn.

- [ ] **Step 1: AC1 — `bootstrap.sh && make test` ≥ 90 % coverage on both packages**

```bash
./bootstrap.sh
source .venv/bin/activate
make test-cov
```

Expected: both packages report coverage ≥ 90 %, with `query_index_eval/metrics.py` at 100 %.

- [ ] **Step 2: AC2 — `make lint` zero errors**

```bash
make lint
```

Expected: clean.

- [ ] **Step 3: AC3 — `archive/query_index_v0.py` byte-for-byte unchanged from original**

```bash
git log --follow --oneline archive/query_index_v0.py
git show HEAD:query_index.py 2>/dev/null || git log --all --diff-filter=D --pretty=format:'%H %s' -- query_index.py
```

The file's content prior to the rename should be identical. Use `git log -p` on the rename commit to inspect.

- [ ] **Step 4: AC4 — `query-eval curate` refuses to run without an interactive TTY**

```bash
echo "" | query-eval curate 2>&1 | head -3
echo "exit=$?"
```

Expected: error message about TTY, exit code 1.

- [ ] **Step 5: AC5 — `query-eval eval` produces a JSON report (skip — requires real Azure)**

This AC is verified by the user in their separate cloned workspace; we cannot exercise it here without Azure credentials. Note the deferral.

- [ ] **Step 6: AC6 — boundary rule enforced by pre-commit hook**

```bash
mkdir -p features/query-index-eval/src/x
echo 'import azure.search.documents' > features/query-index-eval/src/x/violator.py
git add features/query-index-eval/src/x/violator.py
pre-commit run --files features/query-index-eval/src/x/violator.py 2>&1 | tail -5
echo "boundary check exit=$?"
git rm -f features/query-index-eval/src/x/violator.py
rmdir features/query-index-eval/src/x 2>/dev/null || true
```

Expected: pre-commit fails the boundary hook (exit non-zero), prints the violation. After cleanup, working tree is back to clean.

- [ ] **Step 7: AC7 — README content present and accurate**

```bash
test -f README.md
test -f features/query-index/README.md
test -f features/query-index-eval/README.md
grep -q "workspace separation" README.md
grep -q "Public API" features/query-index/README.md
grep -q "Public API" features/query-index-eval/README.md
echo "README check: ALL PRESENT"
```

Expected: prints `README check: ALL PRESENT`.

- [ ] **Step 8: No commit needed if all checks pass.** If any check produced an inadvertent change, revert it.

---

## Task 28: Final README polish

If the cross-package usage examples in the top-level `README.md` are stale (likely — many implementation details only crystallised during Phase 2), update them.

- [ ] **Step 1: Re-read `README.md`** and confirm:
  - The "Production workflow" section's step ordering matches what the implementation supports (`bootstrap.sh`, then `make schema`, then `make curate`, then `make eval`).
  - The console script name `query-eval` is consistent everywhere.
  - The Documents section's links are valid.

- [ ] **Step 2: If updates needed, edit and commit.** If no updates needed, skip.

```bash
# Only if needed:
git add README.md
git commit -m "docs: refresh top-level README for query-index-eval workflow"
```

---

## Task 29: Open the PR

The PR is the single delivery artifact agreed with the user. Per user instruction, no PR is opened until the system is end-to-end functional, which it now is (modulo the deferred AC5 that requires real Azure).

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/query-index-evaluation
```

Note: if `origin` is not configured, this will fail. In that case, ask the user how they want to publish (skip the push, leave as a local branch, or set up a remote first). Do NOT add a remote autonomously.

- [ ] **Step 2: Open the PR**

```bash
gh pr create --base main --head feat/query-index-evaluation \
  --title "feat: query-index search library + retrieval-quality evaluation pipeline" \
  --body "$(cat <<'EOF'
## Summary

Implements the design at `docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md`. Two-package monorepo:

- `features/query-index/` — Azure AI Search hybrid-query library; the only package allowed to import `azure.*` / `openai`. Public API: `Chunk`, `SearchHit`, `Config`, `hybrid_search`, `get_chunk`, `sample_chunks`, `get_embedding`. Helpers: `print_index_schema`, `populate_index`.
- `features/query-index-eval/` — retrieval-quality evaluation pipeline. Public API: dataclasses (`EvalExample`, `MetricsReport`, ...), pure metrics (`recall_at_k`, `mrr`, `map`, ...), `run_eval`, `load_dataset`. CLI: `query-eval {curate, eval, report, schema-discovery}`.

The existing prototype `query_index.py` is preserved unchanged at `archive/query_index_v0.py`.

## Architecture highlights

- Pre-commit boundary hook enforces that only `features/query-index/` imports `azure.*` / `openai`; catches indented and `if TYPE_CHECKING:`-guarded imports too.
- `golden_v1.jsonl` is gitignored and append-only with one-way deprecation; `datasets.py` enforces this in process.
- Reports include embedding deployment + version + API version + index name; `query-eval report --compare` warns when these differ between runs.
- `query-eval curate` refuses to run without an interactive TTY and warns on long substring overlap between user query and chunk text (accidental copy-paste detector).
- Hybrid `cfg` convention across public functions: optional `cfg=None` defaults to `Config.from_env()`.

## Test plan

- [x] Unit tests pass (`make test`) — both packages
- [x] Coverage ≥ 90 % on both packages, 100 % on `metrics.py`
- [x] Lint clean (`make lint`) — ruff + mypy
- [x] Pre-commit clean (`pre-commit run --all-files`)
- [x] Boundary hook catches a planted violation (verified in Task 27)
- [x] `query-eval --help` lists subcommands
- [x] `query-eval curate` exits 1 without TTY
- [ ] **End-to-end against a real Azure index — verified by user in their separate cloned workspace** (deferred, per spec)

## What's NOT in this PR

- Synthetic test-set generation (deferred to a future iteration; the dataset schema reserves `query_id` prefix `s####` for it).
- CI / GitHub Actions (deferred until a forcing function exists).
- Production-grade ingestion pipeline (`ingest.py` is intentionally minimal).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Print the PR URL**

The `gh pr create` output ends with the URL. Capture it and report back to the user.

- [ ] **Step 4: No commit for Task 29 itself** — the PR is a delivery action, not a code change.

---

## End of plan

After Task 29, this plan is fully executed. Outstanding work after merge:

- The user verifies the system end-to-end in their separate cloned workspace (real `data/`, real `.env`).
- If the user finds Phase-2 implementation issues that only surface against real Azure (field name mismatches, encoding, auth quirks), open a follow-up PR with sanitised reproductions.
- Future work tracked in the spec's "Out of scope" section: synthetic generation, CI, production ingestion, end-to-end answer quality.
