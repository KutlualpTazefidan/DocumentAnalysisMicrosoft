# Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 4-stage CLI ingestion pipeline (`analyze` → `chunk` → `embed` → `upload`) that takes PDFs through Document Intelligence, semantic chunking by section, embedding via Azure OpenAI, and into the Azure AI Search index. Plus a small `query-index` refactor that the ingestion feature depends on, plus eval-CLI updates for per-doc workflows and hash drift detection. All in one feature branch (`feat/ingestion-pipeline`) and one PR against `main`.

**Architecture:** Strict per-package boundary (search/openai stays in `query-index`; documentintelligence allowed in `query-index` or `ingestion`). Per-doc outputs structure (`outputs/{slug}/<stage>/{ts}-{strategy}.<ext>`). Sequential chunk_ids `<slug>-NNN` with active hash-drift check at eval time. Multi-doc cumulative index (delete-by-source_file then upload). Plugin pattern for chunker strategies (V1 ships only `section`).

**Tech Stack:** Python ≥3.11, pip + venv editable installs, pytest with mocked Azure clients, ruff, mypy, pre-commit, `azure-ai-documentintelligence` (new), `tiktoken` (new for token-truncation). Existing `query-index` and `query-index-eval` packages.

**Spec reference:** `docs/superpowers/specs/2026-04-27-ingestion-design.md`

**Small adjustment from spec (discovered during planning):** the spec lists `azure.core.credentials.*` as restricted to `query-index/` only (Check 1). This is impossible in practice because `AzureKeyCredential` is the generic credential primitive that the Document Intelligence client needs in `ingestion/`. The plan loosens this single primitive: `azure.core.credentials` is allowed everywhere within `features/` (it is a credential wrapper, not a search/openai dependency). The other restrictions stand: `azure.search.*`, `azure.identity.*`, `openai.*` remain confined to `query-index/`; `azure.ai.documentintelligence.*` remains confined to `query-index/` OR `ingestion/`.

---

## File structure (lock-in)

This plan creates or modifies the following files. Paths are relative to the repository root.

```
DocumentAnalysisMicrosoft/
├── scripts/
│   └── check_import_boundary.sh                 # MODIFY — extend to two patterns
│
├── .gitignore                                   # MODIFY — add outputs/
│
├── Makefile                                     # MODIFY — add ingest-and-eval target
│
├── features/
│   ├── query-index/
│   │   └── src/query_index/
│   │       ├── __init__.py                      # MODIFY — expose get_search_client, get_search_index_client
│   │       ├── types.py                         # MODIFY — add section_heading, source_file fields
│   │       ├── search.py                        # MODIFY — read r["id"], use chunkVector
│   │       └── chunks.py                        # MODIFY — read r["id"]
│   │   └── tests/
│   │       ├── test_types.py                    # MODIFY
│   │       ├── test_search.py                   # MODIFY
│   │       ├── test_chunks.py                   # MODIFY
│   │       └── test_public_api.py               # MODIFY
│   │
│   ├── query-index-eval/
│   │   └── src/query_index_eval/
│   │       ├── cli.py                           # MODIFY — add --doc, --strategy flags
│   │       └── runner.py                        # MODIFY — hash drift check
│   │   └── tests/
│   │       ├── test_cli.py                      # MODIFY
│   │       └── test_runner.py                   # MODIFY
│   │
│   └── ingestion/                               # ALL NEW
│       ├── pyproject.toml
│       ├── README.md
│       ├── .env.example
│       ├── src/ingestion/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── client.py
│       │   ├── slug.py
│       │   ├── timestamp.py
│       │   ├── analyze.py
│       │   ├── chunkers/
│       │   │   ├── __init__.py
│       │   │   ├── base.py
│       │   │   ├── section.py
│       │   │   └── registry.py
│       │   ├── chunk.py
│       │   ├── embed.py
│       │   ├── upload.py
│       │   └── cli.py
│       └── tests/
│           ├── conftest.py
│           └── unit/
│               ├── test_slug.py
│               ├── test_timestamp.py
│               ├── test_config.py
│               ├── test_client.py
│               ├── test_analyze.py
│               ├── test_chunkers_base.py
│               ├── test_chunkers_section.py
│               ├── test_chunkers_registry.py
│               ├── test_chunk.py
│               ├── test_embed.py
│               ├── test_upload.py
│               ├── test_cli.py
│               └── test_public_api.py
```

---

# Phase 0 — `query-index` pre-refactor

Goal: update the `query-index` package to (1) read the canonical notebook schema (`id`, `chunkVector`, `section_heading`, `source_file`), (2) expose `get_search_client` and `get_search_index_client` in the public API, and (3) maintain ≥ 90% coverage. Pure refactor — no behavior change beyond field-name reads. **Lands as the first commits on `feat/ingestion-pipeline`.**

## Task 1: Extend `Chunk` and `SearchHit` dataclasses

**Files:**
- Modify: `features/query-index/src/query_index/types.py`
- Modify: `features/query-index/tests/test_types.py`

- [ ] **Step 1.1: Write the failing test for new optional fields**

Append to `features/query-index/tests/test_types.py`:

```python
def test_chunk_accepts_optional_section_heading_and_source_file() -> None:
    from query_index.types import Chunk

    c = Chunk(
        chunk_id="c1",
        title="T",
        chunk="body",
        section_heading="3.3 Werkstoffkennwerte",
        source_file="GNB B 147_2001 Rev. 1.pdf",
    )
    assert c.section_heading == "3.3 Werkstoffkennwerte"
    assert c.source_file == "GNB B 147_2001 Rev. 1.pdf"


def test_chunk_section_heading_and_source_file_default_to_none() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="T", chunk="body")
    assert c.section_heading is None
    assert c.source_file is None


def test_searchhit_accepts_optional_section_heading_and_source_file() -> None:
    from query_index.types import SearchHit

    h = SearchHit(
        chunk_id="c1",
        title="T",
        chunk="body",
        score=0.9,
        section_heading="3.3 Werkstoffkennwerte",
        source_file="GNB B 147_2001 Rev. 1.pdf",
    )
    assert h.section_heading == "3.3 Werkstoffkennwerte"
    assert h.source_file == "GNB B 147_2001 Rev. 1.pdf"


def test_searchhit_section_heading_and_source_file_default_to_none() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c1", title="T", chunk="body", score=0.9)
    assert h.section_heading is None
    assert h.source_file is None
```

- [ ] **Step 1.2: Run tests, confirm they fail**

```bash
pytest features/query-index/tests/test_types.py -v 2>&1 | tail -10
```

Expected: 4 failures with `TypeError: __init__() got an unexpected keyword argument 'section_heading'`.

- [ ] **Step 1.3: Update `types.py`**

Replace the content of `features/query-index/src/query_index/types.py` with:

```python
"""Frozen dataclasses passed through the search pipeline.

`chunk` is declared with repr=False so logging or pytest assertion failures
do not emit chunk text — see the spec section on logging hygiene.

`section_heading` and `source_file` are optional fields added to support
the ingestion pipeline's per-section chunking (the heading the chunk came
from) and multi-doc index layout (the original PDF filename for filtering).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    title: str
    chunk: str = field(repr=False)
    section_heading: str | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    title: str
    chunk: str = field(repr=False)
    score: float
    section_heading: str | None = None
    source_file: str | None = None

    def __str__(self) -> str:
        return f"SearchHit(id={self.chunk_id}, score={self.score:.3f})"
```

- [ ] **Step 1.4: Run tests, confirm they pass**

```bash
pytest features/query-index/tests/test_types.py -v 2>&1 | tail -10
```

Expected: all tests pass (the 6 original + 4 new = 10).

- [ ] **Step 1.5: Commit**

```bash
git add features/query-index/src/query_index/types.py features/query-index/tests/test_types.py
git commit -m "refactor(query-index): add optional section_heading and source_file to Chunk and SearchHit"
```

---

## Task 2: Update field-name lookups in `search.py` and `chunks.py`

The new schema reads `id` (not `chunk_id`), `chunkVector` (not `text_vector`), and may include `section_heading`/`source_file`.

**Files:**
- Modify: `features/query-index/src/query_index/search.py`
- Modify: `features/query-index/src/query_index/chunks.py`
- Modify: `features/query-index/tests/test_search.py`
- Modify: `features/query-index/tests/test_chunks.py`

- [ ] **Step 2.1: Update `test_search.py` to use the new schema**

Replace the content of `features/query-index/tests/test_search.py` with:

```python
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
            "id": "c1",
            "title": "Title 1",
            "chunk": "Body 1",
            "section_heading": "Section A",
            "source_file": "doc1.pdf",
            "@search.score": 0.91,
        },
        {
            "id": "c2",
            "title": "Title 2",
            "chunk": "Body 2",
            "section_heading": "Section B",
            "source_file": "doc1.pdf",
            "@search.score": 0.55,
        },
    ]
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.1] * 3072),
    ):
        results = hybrid_search("query text", top=2, cfg=cfg)

    assert len(results) == 2
    assert all(isinstance(r, SearchHit) for r in results)
    assert results[0].chunk_id == "c1"
    assert results[0].section_heading == "Section A"
    assert results[0].source_file == "doc1.pdf"
    assert results[0].score == 0.91


def test_hybrid_search_handles_missing_optional_fields(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """Backwards-compat: indexes without section_heading/source_file still work."""
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = [
        {
            "id": "c1",
            "title": "Title 1",
            "chunk": "Body 1",
            "@search.score": 0.91,
        },
    ]
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.1] * 3072),
    ):
        results = hybrid_search("q", top=1, cfg=cfg)

    assert results[0].section_heading is None
    assert results[0].source_file is None


def test_hybrid_search_passes_text_and_vector_to_searchclient(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.7] * 3072),
    ):
        hybrid_search("the query", top=5, cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["search_text"] == "the query"
    assert kwargs["top"] == 5
    vector_queries = kwargs["vector_queries"]
    assert len(vector_queries) == 1
    assert vector_queries[0].vector == [0.7] * 3072
    assert vector_queries[0].k_nearest_neighbors == 5
    assert vector_queries[0].fields == "chunkVector"


def test_hybrid_search_passes_filter_when_provided(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.0] * 3072),
    ):
        hybrid_search("q", top=3, filter="source_file eq 'doc1.pdf'", cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["filter"] == "source_file eq 'doc1.pdf'"


def test_hybrid_search_omits_filter_when_none(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.0] * 3072),
    ):
        hybrid_search("q", top=3, cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs.get("filter") is None


def test_hybrid_search_returns_empty_list_when_no_results(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.0] * 3072),
    ):
        results = hybrid_search("q", top=3, cfg=cfg)

    assert results == []
```

- [ ] **Step 2.2: Run tests, confirm 2 of them fail (the new schema reads)**

```bash
pytest features/query-index/tests/test_search.py -v 2>&1 | tail -15
```

Expected: `test_hybrid_search_returns_list_of_searchhits` and `test_hybrid_search_passes_text_and_vector_to_searchclient` fail because `search.py` still reads `r["chunk_id"]` and uses `fields="text_vector"`.

- [ ] **Step 2.3: Update `search.py`**

Replace the content of `features/query-index/src/query_index/search.py` with:

```python
"""Hybrid (text + vector) search over the configured Azure AI Search index.

Reads the canonical notebook schema: `id`, `chunk`, `title`, `chunkVector`,
optional `section_heading`, optional `source_file`.
"""
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
    if cfg is None:
        cfg = Config.from_env()
    vector = get_embedding(query, cfg)
    vector_query = VectorizedQuery(
        vector=vector,
        k_nearest_neighbors=top,
        fields="chunkVector",
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
                chunk_id=r["id"],
                title=r["title"],
                chunk=r["chunk"],
                score=float(r.get("@search.score", 0.0)),
                section_heading=r.get("section_heading"),
                source_file=r.get("source_file"),
            )
        )
    return hits
```

- [ ] **Step 2.4: Run search tests, confirm pass**

```bash
pytest features/query-index/tests/test_search.py -v 2>&1 | tail -10
```

Expected: 6 tests pass.

- [ ] **Step 2.5: Update `test_chunks.py` for new schema**

Replace the content of `features/query-index/tests/test_chunks.py` with:

```python
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
        "id": "c42",
        "title": "Section 4.2",
        "chunk": "Tragkorbdurchmesser ...",
        "section_heading": "4.2 Konstruktion",
        "source_file": "doc1.pdf",
    }
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = get_chunk("c42", cfg)

    assert isinstance(result, Chunk)
    assert result.chunk_id == "c42"
    assert result.title == "Section 4.2"
    assert result.chunk == "Tragkorbdurchmesser ..."
    assert result.section_heading == "4.2 Konstruktion"
    assert result.source_file == "doc1.pdf"
    mock_search_client.get_document.assert_called_once_with(key="c42")


def test_get_chunk_handles_missing_optional_fields(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """Backwards-compat for indexes without section_heading/source_file."""
    from query_index.chunks import get_chunk
    from query_index.config import Config

    mock_search_client.get_document.return_value = {
        "id": "c42",
        "title": "T",
        "chunk": "body",
    }
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = get_chunk("c42", cfg)

    assert result.section_heading is None
    assert result.source_file is None


def test_sample_chunks_returns_n_chunks(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config
    from query_index.types import Chunk

    mock_search_client.search.return_value = [
        {"id": f"c{i}", "title": f"T{i}", "chunk": f"body{i}"} for i in range(5)
    ]
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = sample_chunks(n=5, seed=42, cfg=cfg)

    assert len(result) == 5
    assert all(isinstance(c, Chunk) for c in result)


def test_sample_chunks_pulls_a_window_at_least_as_large_as_sample_window(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
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
    from query_index.chunks import sample_chunks
    from query_index.config import Config

    docs = [{"id": f"c{i}", "title": f"T{i}", "chunk": f"b{i}"} for i in range(20)]
    mock_search_client.search.return_value = docs
    cfg = Config.from_env()

    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        run1 = sample_chunks(n=5, seed=12345, cfg=cfg)
    mock_search_client.search.return_value = docs
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

- [ ] **Step 2.6: Run chunks tests, confirm 2 fail (the schema reads)**

```bash
pytest features/query-index/tests/test_chunks.py -v 2>&1 | tail -15
```

Expected: `test_get_chunk_returns_chunk_for_known_id` and `test_get_chunk_handles_missing_optional_fields` fail because `chunks.py` reads `doc["chunk_id"]`.

- [ ] **Step 2.7: Update `chunks.py`**

Replace the content of `features/query-index/src/query_index/chunks.py` with:

```python
"""Chunk-fetching helpers used by curation and synthesis flows.

Reads the canonical notebook schema: `id`, `chunk`, `title`, optional
`section_heading`, optional `source_file`.
"""
from __future__ import annotations

import random

from query_index.client import get_search_client
from query_index.config import Config
from query_index.types import Chunk

SAMPLE_WINDOW = 100
"""Default candidate-window size for sample_chunks.

We pull SAMPLE_WINDOW (or n, whichever is larger) candidates from the index,
then shuffle them with a seeded RNG and take the first n. This gives a
meaningfully random sample — pulling exactly n would just return the top-n by
relevance, which defeats the purpose of sampling.
"""


def get_chunk(chunk_id: str, cfg: Config | None = None) -> Chunk:
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_client(cfg)
    doc = client.get_document(key=chunk_id)
    return Chunk(
        chunk_id=doc["id"],
        title=doc["title"],
        chunk=doc["chunk"],
        section_heading=doc.get("section_heading"),
        source_file=doc.get("source_file"),
    )


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
        Chunk(
            chunk_id=d["id"],
            title=d["title"],
            chunk=d["chunk"],
            section_heading=d.get("section_heading"),
            source_file=d.get("source_file"),
        )
        for d in selected
    ]
```

- [ ] **Step 2.8: Run chunks tests, confirm pass**

```bash
pytest features/query-index/tests/test_chunks.py -v 2>&1 | tail -10
```

Expected: 6 tests pass.

- [ ] **Step 2.9: Run full query-index suite**

```bash
pytest features/query-index/ --cov=query_index --cov-report=term-missing 2>&1 | tail -20
```

Expected: all tests pass; coverage ≥ 90%.

- [ ] **Step 2.10: Commit**

```bash
git add features/query-index/src/query_index/search.py features/query-index/src/query_index/chunks.py features/query-index/tests/test_search.py features/query-index/tests/test_chunks.py
git commit -m "refactor(query-index): read canonical notebook schema (id, chunkVector, section_heading, source_file)"
```

---

## Task 3: Expose `get_search_client` and `get_search_index_client` in public API

**Files:**
- Modify: `features/query-index/src/query_index/__init__.py`
- Modify: `features/query-index/tests/test_public_api.py`

- [ ] **Step 3.1: Update `test_public_api.py`**

Replace the content of `features/query-index/tests/test_public_api.py` with:

```python
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
        "get_search_client",
        "get_search_index_client",
        "hybrid_search",
        "sample_chunks",
    }
    missing = expected - set(dir(query_index))
    assert not missing, f"Missing public exports: {missing}"


def test_public_api_does_not_expose_unintended_helpers() -> None:
    """Internal helpers are intentionally not in the public surface."""
    import query_index

    not_expected = {"get_openai_client"}
    overexposed = not_expected & set(dir(query_index))
    assert not overexposed, f"Helpers leaked into public API: {overexposed}"
```

- [ ] **Step 3.2: Run, confirm fail**

```bash
pytest features/query-index/tests/test_public_api.py -v 2>&1 | tail -10
```

Expected: `test_public_api_exports_expected_names` fails citing missing `get_search_client` and `get_search_index_client`.

- [ ] **Step 3.3: Update `__init__.py`**

Replace the content of `features/query-index/src/query_index/__init__.py` with:

```python
"""Public API for the query_index package.

Exports the search/chunk/embedding interface plus the Azure-client factories
needed by sibling packages (e.g., `ingestion`) under the strict-boundary rule.
The OpenAI client factory remains internal (no consumer outside this package
needs it directly).
"""
from query_index.chunks import get_chunk, sample_chunks
from query_index.client import get_search_client, get_search_index_client
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
    "get_search_client",
    "get_search_index_client",
    "hybrid_search",
    "sample_chunks",
]
```

- [ ] **Step 3.4: Run public-API test, confirm pass**

```bash
pytest features/query-index/tests/test_public_api.py -v 2>&1 | tail -10
```

Expected: 2 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add features/query-index/src/query_index/__init__.py features/query-index/tests/test_public_api.py
git commit -m "feat(query-index): expose get_search_client and get_search_index_client in public API"
```

---

## Task 4: Phase-0 acceptance check

Verify the refactor is complete with no regressions.

- [ ] **Step 4.1: Full test run**

```bash
pytest features/query-index/ --cov=query_index --cov-report=term-missing 2>&1 | tail -25
```

Expected: every test passes; coverage ≥ 90% on `src/query_index/`.

- [ ] **Step 4.2: Lint clean**

```bash
make lint 2>&1 | tail -10
```

Expected: zero ruff/mypy issues.

- [ ] **Step 4.3: Pre-commit on all files**

```bash
pre-commit run --all-files 2>&1 | tail -15
```

Expected: all hooks pass, including the existing import-boundary check.

- [ ] **Step 4.4: Verify the new public API shape end-to-end**

```bash
python -c "from query_index import get_search_client, get_search_index_client, Chunk, SearchHit; print('refactor public API OK')"
```

Expected: prints `refactor public API OK`.

- [ ] **Step 4.5: NO commit** for Task 4 — work is already in.

End of Phase 0.

---

# Phase 1 — Boundary rule extension + ingestion package skeleton

Goal: extend the pre-commit boundary check with the second pattern (Document Intelligence), then scaffold the `ingestion` package.

## Task 5: Extend the import-boundary check

**Files:**
- Modify: `scripts/check_import_boundary.sh`

- [ ] **Step 5.1: Replace `scripts/check_import_boundary.sh` with the two-pattern version**

```bash
#!/usr/bin/env bash
# Enforce per-package import boundaries:
#  1. Search & OpenAI imports (azure.search.*, azure.identity.*,
#     azure.core.credentials.*, openai.*) — only features/query-index/.
#  2. Document Intelligence imports (azure.ai.documentintelligence.*) —
#     only features/query-index/ OR features/ingestion/.
#
# Both checks share the same regex constraints from the original hook:
#  - Match imports at any indentation level (catches TYPE_CHECKING blocks
#    and lazy/conditional imports inside functions).
#  - Anchor the package name so prefix-collisions (e.g. import openai_async)
#    are NOT flagged.
#  - Allow submodule imports and plain top-level forms.

set -euo pipefail

if [ ! -d features ]; then
    exit 0
fi

# --- Check 1: search/openai imports — only query-index ---
violations_search="$(grep -rEn '[[:space:]]*(import|from)[[:space:]]+(azure\.search|azure\.identity|openai)([.[:space:]]|$)' \
    --include='*.py' \
    features/ \
    | grep -v '^features/query-index/' \
    || true)"

if [ -n "$violations_search" ]; then
    echo "BOUNDARY VIOLATION: azure.search.*, azure.identity.*, and openai.* imports are only allowed inside features/query-index/"
    echo "$violations_search"
    exit 1
fi

# --- Check 2: documentintelligence imports — only query-index OR ingestion ---
violations_docintel="$(grep -rEn '[[:space:]]*(import|from)[[:space:]]+azure\.ai\.documentintelligence([.[:space:]]|$)' \
    --include='*.py' \
    features/ \
    | grep -v -E '^features/(query-index|ingestion)/' \
    || true)"

if [ -n "$violations_docintel" ]; then
    echo "BOUNDARY VIOLATION: azure.ai.documentintelligence imports are only allowed inside features/query-index/ or features/ingestion/"
    echo "$violations_docintel"
    exit 1
fi

exit 0
```

- [ ] **Step 5.2: Verify Check 1 still works (existing positive)**

```bash
bash scripts/check_import_boundary.sh; echo "clean=$?"
```

Expected: `clean=0`.

- [ ] **Step 5.3: Verify Check 1 still catches a search-import violation**

```bash
mkdir -p features/query-index-eval/src/x
echo 'import azure.search.documents' > features/query-index-eval/src/x/bad.py
bash scripts/check_import_boundary.sh; echo "exit=$?"
rm -rf features/query-index-eval/src/x
```

Expected: prints "BOUNDARY VIOLATION: azure.search...", exit code 1.

- [ ] **Step 5.4: Verify Check 2 catches a doc-intel violation in eval**

```bash
mkdir -p features/query-index-eval/src/y
echo 'from azure.ai.documentintelligence import DocumentIntelligenceClient' > features/query-index-eval/src/y/bad.py
bash scripts/check_import_boundary.sh; echo "exit=$?"
rm -rf features/query-index-eval/src/y
```

Expected: prints "BOUNDARY VIOLATION: azure.ai.documentintelligence...", exit code 1.

- [ ] **Step 5.5: Verify Check 2 ALLOWS doc-intel imports in (a fictional) ingestion**

```bash
mkdir -p features/ingestion/src/foo
echo 'from azure.ai.documentintelligence import DocumentIntelligenceClient' > features/ingestion/src/foo/ok.py
bash scripts/check_import_boundary.sh; echo "exit=$?"
rm -rf features/ingestion/src/foo
```

Expected: exit 0 (no violation; ingestion is on the allow-list for Check 2).

- [ ] **Step 5.6: Verify final `git status` is clean (no leftover test files)**

```bash
git status
```

Expected: working tree clean (or only the modified `scripts/check_import_boundary.sh`).

- [ ] **Step 5.7: Commit**

```bash
git add scripts/check_import_boundary.sh
git commit -m "chore(boundary): extend import check to allow azure.ai.documentintelligence in ingestion"
```

---

## Task 6: Ingestion package skeleton

**Files:**
- Create: `features/ingestion/pyproject.toml`
- Create: `features/ingestion/.env.example`
- Create: `features/ingestion/README.md`
- Create: `features/ingestion/src/ingestion/__init__.py` (empty)
- Create: `features/ingestion/tests/__init__.py` (empty)
- Create: `features/ingestion/tests/conftest.py`
- Create: `features/ingestion/tests/unit/__init__.py` (empty)

- [ ] **Step 6.1: Create directory tree**

```bash
mkdir -p features/ingestion/src/ingestion/chunkers features/ingestion/tests/unit
```

- [ ] **Step 6.2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ingestion"
version = "0.1.0"
description = "PDF ingestion pipeline: analyze, chunk, embed, upload to Azure AI Search."
requires-python = ">=3.11"
dependencies = [
    "query-index",
    "azure-ai-documentintelligence>=1.0.0",
    "python-dotenv>=1.0.0",
    "tiktoken>=0.7.0",
]

[project.scripts]
ingest = "ingestion.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
addopts = "-q --strict-markers --cov=ingestion --cov-report=term-missing --cov-fail-under=90"
testpaths = ["tests"]
```

- [ ] **Step 6.3: Create `.env.example`**

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

- [ ] **Step 6.4: Create `README.md`**

````markdown
# ingestion

PDF ingestion pipeline for the Azure AI Search index. Four stages, each its own CLI subcommand:

```bash
ingest analyze --in data/foo.pdf
ingest chunk   --in outputs/foo/analyze/{ts}.json --strategy section
ingest embed   --in outputs/foo/chunk/{ts}-section.jsonl
ingest upload  --in outputs/foo/embed/{ts}-section.jsonl
```

## Stages

- **analyze**: Document Intelligence `prebuilt-layout` extracts text + structure. Output: JSON.
- **chunk**: applies a chunker strategy (V1: `section`-based) to the analyze JSON. Output: text-only chunks JSONL.
- **embed**: calls Azure OpenAI to vectorise each chunk. Output: chunks + vectors JSONL.
- **upload**: pushes to Azure AI Search. Multi-doc cumulative — deletes only chunks for the given source_file before uploading.

## Outputs structure

All artefacts live under `outputs/{slug}/<stage>/{ts}-{strategy}.{ext}`. The slug is derived from the input filename (lowercased, hyphenated, sanitised).

## Tests

```bash
pytest features/ingestion/
```

All tests are mocked — they do not call Azure. Live verification is done by the user in their separate cloned workspace.
````

- [ ] **Step 6.5: Create empty marker files**

```bash
: > features/ingestion/src/ingestion/__init__.py
: > features/ingestion/tests/__init__.py
: > features/ingestion/tests/unit/__init__.py
```

- [ ] **Step 6.6: Create `tests/conftest.py`**

```python
"""Shared fixtures for ingestion tests. All Azure clients mocked."""
from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Populate the environment with valid dummy values for both Configs."""
    values = {
        # Document Intelligence
        "DOC_INTEL_ENDPOINT": "https://test-doc-intel.example.com/",
        "DOC_INTEL_KEY": "test-doc-intel-key",
        # query-index pass-through
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
def mock_doc_intel_client() -> MagicMock:
    """A MagicMock that mimics azure.ai.documentintelligence.DocumentIntelligenceClient."""
    return MagicMock()


@pytest.fixture
def mock_search_client() -> MagicMock:
    """A MagicMock that mimics azure.search.documents.SearchClient."""
    client = MagicMock()
    client.search.return_value = []
    return client


@pytest.fixture
def mock_search_index_client() -> MagicMock:
    """A MagicMock that mimics azure.search.documents.indexes.SearchIndexClient."""
    return MagicMock()


@pytest.fixture
def sample_analyze_result() -> dict:
    """A minimal Document Intelligence layout response with title, headings, body, and pageFooter.

    Used by chunker tests to verify the section chunker behaviour without
    needing to mock the full Document Intelligence response shape.
    """
    return {
        "_ingestion_metadata": {
            "source_file": "GNB B 147_2001 Rev. 1.pdf",
            "slug": "gnb-b-147-2001-rev-1",
            "timestamp_utc": "20260427T143000",
        },
        "analyzeResult": {
            "apiVersion": "2024-11-30",
            "modelId": "prebuilt-layout",
            "paragraphs": [
                {"content": "Test Document Title", "role": "title"},
                {"content": "Page header", "role": "pageHeader"},
                {"content": "1. Introduction", "role": "sectionHeading"},
                {"content": "Intro body paragraph 1.", "role": None},
                {"content": "Intro body paragraph 2.", "role": None},
                {"content": "Page 2 / 5", "role": "pageFooter"},
                {"content": "2. Methods", "role": "sectionHeading"},
                {"content": "Methods body paragraph.", "role": None},
                {"content": "Footnote text", "role": "footnote"},
            ],
        },
    }
```

- [ ] **Step 6.7: Install ingestion package in editable mode**

```bash
source .venv/bin/activate
pip install -e features/ingestion
pip show ingestion | head -5
```

Expected: install succeeds; `pip show` reports name `ingestion`, version `0.1.0`.

- [ ] **Step 6.8: Verify package imports**

```bash
python -c "import ingestion; print(ingestion.__file__)"
```

Expected: prints the path to `features/ingestion/src/ingestion/__init__.py`.

- [ ] **Step 6.9: Verify the `ingest` console script is registered (will fail to run because cli.py does not exist yet — that is fine)**

```bash
which ingest
```

Expected: a path inside `.venv/bin/`.

- [ ] **Step 6.10: Update root `.gitignore` to exclude `outputs/`**

Modify the existing `.gitignore` at the repo root by adding the line `outputs/` (after `data_dummy/` if it is there, or just under `data/`). The full block becomes (showing only the relevant section):

```
# Data (workspace separation pattern — production data lives in user's separate clone)
data/
data_dummy/
outputs/
```

- [ ] **Step 6.11: Commit**

```bash
git add features/ingestion/ .gitignore
git commit -m "feat(ingestion): scaffold package (pyproject, README, conftest, console-script registration)"
```

---

# Phase 2 — Helpers (slug, timestamp, config, client)

Goal: build the small pure-Python helpers that the rest of the package depends on. Each is its own TDD cycle.

## Task 7: `slug.py`

**Files:**
- Create: `features/ingestion/src/ingestion/slug.py`
- Create: `features/ingestion/tests/unit/test_slug.py`

- [ ] **Step 7.1: Write failing tests**

Create `features/ingestion/tests/unit/test_slug.py`:

```python
"""Tests for ingestion.slug.slug_from_filename()."""
from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "filename,want",
    [
        ("GNB B 147_2001 Rev. 1.pdf", "gnb-b-147-2001-rev-1"),
        ("IAEA TS-G-1.1.pdf", "iaea-ts-g-1-1"),
        ("simple.pdf", "simple"),
        ("Simple.pdf", "simple"),
        ("with spaces and dots.pdf", "with-spaces-and-dots"),
        ("Mixed_Case-File.PDF", "mixed-case-file"),
        ("trailing-spaces  .pdf", "trailing-spaces"),
        ("---hyphens---in---name.pdf", "hyphens-in-name"),
        ("file_without_extension", "file-without-extension"),
        ("__leading_underscores.pdf", "leading-underscores"),
    ],
)
def test_slug_from_filename(filename, want) -> None:
    from ingestion.slug import slug_from_filename

    assert slug_from_filename(filename) == want


def test_slug_from_filename_strips_unicode_punct() -> None:
    """Non-ASCII punctuation should be replaced or stripped, not preserved."""
    from ingestion.slug import slug_from_filename

    assert slug_from_filename("Bericht (Rev. 1).pdf") == "bericht-rev-1"


def test_slug_from_filename_collapses_runs() -> None:
    from ingestion.slug import slug_from_filename

    assert slug_from_filename("a   b___c...d.pdf") == "a-b-c-d"
```

- [ ] **Step 7.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_slug.py -v 2>&1 | tail -10
```

Expected: 12 failures with `ModuleNotFoundError: No module named 'ingestion.slug'`.

- [ ] **Step 7.3: Implement `slug.py`**

Create `features/ingestion/src/ingestion/slug.py`:

```python
"""Filename → URL-safe slug.

Used to derive per-document folder names under outputs/. Deterministic,
no external dependencies.
"""
from __future__ import annotations

import re

_TRIM_EXTENSION = re.compile(r"\.pdf$", re.IGNORECASE)
_NON_ALNUM_OR_HYPHEN = re.compile(r"[^a-z0-9-]+")
_RUN_OF_HYPHENS = re.compile(r"-+")


def slug_from_filename(filename: str) -> str:
    """Convert a filename to a URL-safe slug.

    Steps:
        1. Strip a trailing `.pdf` extension (case-insensitive).
        2. Lowercase.
        3. Replace any non-(letter|digit|hyphen) run with a single hyphen.
        4. Collapse runs of hyphens into one.
        5. Trim leading and trailing hyphens.

    Examples:
        'GNB B 147_2001 Rev. 1.pdf' -> 'gnb-b-147-2001-rev-1'
        'IAEA TS-G-1.1.pdf'         -> 'iaea-ts-g-1-1'
    """
    base = _TRIM_EXTENSION.sub("", filename)
    lowered = base.lower()
    replaced = _NON_ALNUM_OR_HYPHEN.sub("-", lowered)
    collapsed = _RUN_OF_HYPHENS.sub("-", replaced)
    return collapsed.strip("-")
```

- [ ] **Step 7.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_slug.py -v 2>&1 | tail -10
```

Expected: all 12 tests pass.

- [ ] **Step 7.5: Commit**

```bash
git add features/ingestion/src/ingestion/slug.py features/ingestion/tests/unit/test_slug.py
git commit -m "feat(ingestion): add slug_from_filename helper"
```

---

## Task 8: `timestamp.py`

**Files:**
- Create: `features/ingestion/src/ingestion/timestamp.py`
- Create: `features/ingestion/tests/unit/test_timestamp.py`

- [ ] **Step 8.1: Write failing tests**

Create `features/ingestion/tests/unit/test_timestamp.py`:

```python
"""Tests for ingestion.timestamp helpers."""
from __future__ import annotations

import re
from datetime import datetime, timezone


def test_now_compact_utc_format() -> None:
    from ingestion.timestamp import now_compact_utc

    out = now_compact_utc()
    # YYYYMMDDTHHMMSS
    assert re.fullmatch(r"\d{8}T\d{6}", out), f"Unexpected format: {out!r}"


def test_now_compact_utc_is_recent() -> None:
    """Result should be within ~5 seconds of 'now'."""
    from ingestion.timestamp import now_compact_utc

    before = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = now_compact_utc()
    after = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    assert before <= out <= after


def test_now_compact_utc_is_lexically_chronological() -> None:
    """Two calls in sequence: the second is >= the first lexically."""
    import time

    from ingestion.timestamp import now_compact_utc

    a = now_compact_utc()
    time.sleep(1.1)
    b = now_compact_utc()
    assert a < b


def test_now_compact_utc_uses_utc_not_local_time(monkeypatch) -> None:
    """Ensure the function uses UTC, not local time, regardless of TZ env."""
    from ingestion.timestamp import now_compact_utc

    monkeypatch.setenv("TZ", "America/New_York")
    out = now_compact_utc()
    expected_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    # Allow off-by-one second
    assert abs(int(out[-2:]) - int(expected_utc[-2:])) <= 1 or out[:-2] == expected_utc[:-2]
```

- [ ] **Step 8.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_timestamp.py -v 2>&1 | tail -10
```

Expected: 4 failures with `ModuleNotFoundError`.

- [ ] **Step 8.3: Implement `timestamp.py`**

Create `features/ingestion/src/ingestion/timestamp.py`:

```python
"""Compact UTC ISO-8601 timestamp helpers for filenames.

Format: 'YYYYMMDDTHHMMSS' — sortable as text, equal to chronological order.
No timezone suffix; UTC is implicit by convention.
"""
from __future__ import annotations

from datetime import datetime, timezone


def now_compact_utc() -> str:
    """Return the current UTC time as a compact ISO-8601 string.

    Suitable for filenames (no colons, no whitespace, sortable).
    """
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
```

- [ ] **Step 8.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_timestamp.py -v 2>&1 | tail -10
```

Expected: all 4 tests pass.

- [ ] **Step 8.5: Commit**

```bash
git add features/ingestion/src/ingestion/timestamp.py features/ingestion/tests/unit/test_timestamp.py
git commit -m "feat(ingestion): add now_compact_utc helper for filename timestamps"
```

---

## Task 9: `IngestionConfig`

Doc-Intel-only environment-driven config.

**Files:**
- Create: `features/ingestion/src/ingestion/config.py`
- Create: `features/ingestion/tests/unit/test_config.py`

- [ ] **Step 9.1: Write failing tests**

Create `features/ingestion/tests/unit/test_config.py`:

```python
"""Tests for ingestion.config.IngestionConfig.from_env()."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_from_env_loads_required_fields(env_vars: dict[str, str]) -> None:
    from ingestion.config import IngestionConfig

    cfg = IngestionConfig.from_env()
    assert cfg.doc_intel_endpoint == env_vars["DOC_INTEL_ENDPOINT"]
    assert cfg.doc_intel_key == env_vars["DOC_INTEL_KEY"]


def test_from_env_is_frozen(env_vars: dict[str, str]) -> None:
    from ingestion.config import IngestionConfig

    cfg = IngestionConfig.from_env()
    with pytest.raises(FrozenInstanceError):
        cfg.doc_intel_endpoint = "x"  # type: ignore[misc]


@pytest.mark.parametrize("missing_var", ["DOC_INTEL_ENDPOINT", "DOC_INTEL_KEY"])
def test_from_env_raises_when_required_missing(
    env_vars: dict[str, str], monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    from ingestion.config import IngestionConfig

    monkeypatch.delenv(missing_var, raising=False)
    with pytest.raises(KeyError) as excinfo:
        IngestionConfig.from_env()
    assert missing_var in str(excinfo.value)
```

- [ ] **Step 9.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_config.py -v 2>&1 | tail -10
```

Expected: 4 failures with `ModuleNotFoundError`.

- [ ] **Step 9.3: Implement `config.py`**

Create `features/ingestion/src/ingestion/config.py`:

```python
"""Document Intelligence configuration loaded from environment.

`IngestionConfig.from_env()` is the only way to construct a Config; it reads
required variables from os.environ. Missing variables raise KeyError with a
clear message naming the missing key.

This config is for the analyze stage only. The embed and upload stages use
`query_index.Config` directly because they are talking to AI Search and
AzureOpenAI, not to Document Intelligence.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED_VARS: tuple[str, ...] = (
    "DOC_INTEL_ENDPOINT",
    "DOC_INTEL_KEY",
)


@dataclass(frozen=True)
class IngestionConfig:
    doc_intel_endpoint: str
    doc_intel_key: str

    @classmethod
    def from_env(cls) -> "IngestionConfig":
        for var in _REQUIRED_VARS:
            if var not in os.environ:
                raise KeyError(f"Required environment variable not set: {var}")
        return cls(
            doc_intel_endpoint=os.environ["DOC_INTEL_ENDPOINT"],
            doc_intel_key=os.environ["DOC_INTEL_KEY"],
        )
```

- [ ] **Step 9.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_config.py -v 2>&1 | tail -10
```

Expected: 4 tests pass.

- [ ] **Step 9.5: Commit**

```bash
git add features/ingestion/src/ingestion/config.py features/ingestion/tests/unit/test_config.py
git commit -m "feat(ingestion): add IngestionConfig dataclass loaded from environment"
```

---

## Task 10: `client.py` — Document Intelligence client factory

**Files:**
- Create: `features/ingestion/src/ingestion/client.py`
- Create: `features/ingestion/tests/unit/test_client.py`

- [ ] **Step 10.1: Write failing tests**

Create `features/ingestion/tests/unit/test_client.py`:

```python
"""Tests for ingestion.client lazy-construction helpers."""
from __future__ import annotations

from unittest.mock import patch


def test_get_doc_intel_client_constructs_with_config(env_vars: dict[str, str]) -> None:
    from ingestion.client import get_doc_intel_client
    from ingestion.config import IngestionConfig

    cfg = IngestionConfig.from_env()
    with (
        patch("ingestion.client.DocumentIntelligenceClient") as mock_cls,
        patch("ingestion.client.AzureKeyCredential") as mock_cred,
    ):
        mock_cred.return_value = "credential-instance"
        get_doc_intel_client(cfg)
    mock_cred.assert_called_once_with(cfg.doc_intel_key)
    mock_cls.assert_called_once_with(
        endpoint=cfg.doc_intel_endpoint,
        credential="credential-instance",
    )
```

- [ ] **Step 10.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_client.py -v 2>&1 | tail -10
```

Expected: failure with `ModuleNotFoundError`.

- [ ] **Step 10.3: Implement `client.py`**

Create `features/ingestion/src/ingestion/client.py`:

```python
"""Factory for the Azure Document Intelligence SDK client.

Construction is parameterised on an IngestionConfig — callers pass the
config they have, no module-level singletons. Tests patch the SDK class here.
"""
from __future__ import annotations

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

from ingestion.config import IngestionConfig


def get_doc_intel_client(cfg: IngestionConfig) -> DocumentIntelligenceClient:
    return DocumentIntelligenceClient(
        endpoint=cfg.doc_intel_endpoint,
        credential=AzureKeyCredential(cfg.doc_intel_key),
    )
```

(The boundary script in Task 5 already excludes `azure.core.credentials` from the search-family restriction, so this import is allowed in `ingestion/`. See the "Small adjustment from spec" note at the top of the plan.)

- [ ] **Step 10.4: Run client test, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_client.py -v 2>&1 | tail -10
```

Expected: 1 test passes.

- [ ] **Step 10.5: Verify the boundary still catches a real search-import violation in ingestion**

```bash
mkdir -p features/ingestion/src/ingestion/_boundary_check_only
echo 'import azure.search.documents' > features/ingestion/src/ingestion/_boundary_check_only/bad.py
bash scripts/check_import_boundary.sh; echo "exit=$?"
rm -rf features/ingestion/src/ingestion/_boundary_check_only
```

Expected: prints "BOUNDARY VIOLATION: azure.search.*", exit code 1.

- [ ] **Step 10.6: Commit**

```bash
git add features/ingestion/src/ingestion/client.py features/ingestion/tests/unit/test_client.py
git commit -m "feat(ingestion): add DocumentIntelligenceClient factory"
```

---

# Phase 3 — `analyze` stage (PDF → JSON)

Goal: implement the first pipeline stage. Reads a PDF, calls Document Intelligence `prebuilt-layout`, writes the wrapped JSON (with `_ingestion_metadata` sidecar) to the right outputs path.

## Task 11: `analyze.py`

**Files:**
- Create: `features/ingestion/src/ingestion/analyze.py`
- Create: `features/ingestion/tests/unit/test_analyze.py`

- [ ] **Step 11.1: Write failing tests**

Create `features/ingestion/tests/unit/test_analyze.py`:

```python
"""Tests for ingestion.analyze.analyze_pdf()."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _fake_doc_intel_result() -> MagicMock:
    """Build a MagicMock that pretends to be the result of poller.result().

    The crucial bit is `.as_dict()` returning a dict shaped like a real
    Document Intelligence response.
    """
    result = MagicMock()
    result.as_dict.return_value = {
        "apiVersion": "2024-11-30",
        "modelId": "prebuilt-layout",
        "pages": [{"pageNumber": 1}, {"pageNumber": 2}],
        "paragraphs": [
            {"content": "Title", "role": "title"},
            {"content": "Body", "role": None},
        ],
    }
    return result


def test_analyze_pdf_writes_wrapped_json_to_auto_derived_path(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "Some Doc Name.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    monkeypatch_outputs = tmp_path / "outputs-root"
    with (
        patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client),
        patch(
            "ingestion.analyze._outputs_root",
            return_value=monkeypatch_outputs,
        ),
        patch(
            "ingestion.analyze.now_compact_utc",
            return_value="20260427T143000",
        ),
    ):
        out_path = analyze_pdf(pdf)

    expected_path = monkeypatch_outputs / "some-doc-name" / "analyze" / "20260427T143000.json"
    assert out_path == expected_path
    assert out_path.exists()

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["_ingestion_metadata"]["source_file"] == "Some Doc Name.pdf"
    assert written["_ingestion_metadata"]["slug"] == "some-doc-name"
    assert written["_ingestion_metadata"]["timestamp_utc"] == "20260427T143000"
    assert written["analyzeResult"]["modelId"] == "prebuilt-layout"


def test_analyze_pdf_uses_explicit_out_path_when_given(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    explicit_out = tmp_path / "custom_dir" / "result.json"

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        out_path = analyze_pdf(pdf, out_path=explicit_out)

    assert out_path == explicit_out
    assert out_path.exists()


def test_analyze_pdf_calls_doc_intel_with_prebuilt_layout(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    fake_poller = MagicMock()
    fake_poller.result.return_value = _fake_doc_intel_result()
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        analyze_pdf(pdf, out_path=tmp_path / "out.json")

    mock_client.begin_analyze_document.assert_called_once()
    _, kwargs = mock_client.begin_analyze_document.call_args
    assert kwargs["model_id"] == "prebuilt-layout"
    assert kwargs["content_type"] == "application/pdf"


def test_analyze_pdf_does_not_log_chunk_or_paragraph_content(
    env_vars: dict[str, str], tmp_path: Path, capsys
) -> None:
    """The metadata-only logging discipline: no chunk/paragraph text in stdout/stderr."""
    from ingestion.analyze import analyze_pdf

    pdf = tmp_path / "foo.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    secret = "SECRET-PARAGRAPH-CONTENT"
    fake_result = MagicMock()
    fake_result.as_dict.return_value = {
        "apiVersion": "2024-11-30",
        "modelId": "prebuilt-layout",
        "pages": [{"pageNumber": 1}],
        "paragraphs": [{"content": secret, "role": None}],
    }
    fake_poller = MagicMock()
    fake_poller.result.return_value = fake_result
    mock_client = MagicMock()
    mock_client.begin_analyze_document.return_value = fake_poller

    with patch("ingestion.analyze.get_doc_intel_client", return_value=mock_client):
        analyze_pdf(pdf, out_path=tmp_path / "out.json")

    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
```

- [ ] **Step 11.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_analyze.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 11.3: Implement `analyze.py`**

Create `features/ingestion/src/ingestion/analyze.py`:

```python
"""Analyze a PDF with Document Intelligence and persist the result as JSON.

The output JSON wraps the Document Intelligence response with an
`_ingestion_metadata` sidecar that downstream stages (chunk, embed, upload)
read to derive the slug, source_file, and lineage timestamp without the user
having to re-supply them at each step.
"""
from __future__ import annotations

import json
from pathlib import Path

from ingestion.client import get_doc_intel_client
from ingestion.config import IngestionConfig
from ingestion.slug import slug_from_filename
from ingestion.timestamp import now_compact_utc


def _outputs_root() -> Path:
    """Return the repository's outputs root.

    Discovered by walking up from this file until a directory containing both
    a `pyproject.toml` (root) and the `features/` directory is found.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "features").is_dir():
            return parent / "outputs"
    # Fallback: the cwd
    return Path.cwd() / "outputs"


def analyze_pdf(
    in_path: Path,
    out_path: Path | None = None,
    cfg: IngestionConfig | None = None,
) -> Path:
    """Analyze a PDF; write JSON; return the actual output path.

    If `out_path` is None, derive: `<outputs_root>/<slug>/analyze/<ts>.json`.
    """
    if cfg is None:
        cfg = IngestionConfig.from_env()

    source_file = in_path.name
    slug = slug_from_filename(source_file)
    ts = now_compact_utc()

    if out_path is None:
        out_path = _outputs_root() / slug / "analyze" / f"{ts}.json"

    client = get_doc_intel_client(cfg)

    with in_path.open("rb") as f:
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=f,
            content_type="application/pdf",
        )
    result = poller.result()
    raw = result.as_dict()

    wrapped = {
        "_ingestion_metadata": {
            "source_file": source_file,
            "slug": slug,
            "timestamp_utc": ts,
        },
        "analyzeResult": raw,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")

    page_count = len(raw.get("pages", []))
    paragraph_count = len(raw.get("paragraphs", []))
    print(
        f"Wrote {out_path} ({page_count} pages, {paragraph_count} paragraphs)"
    )

    return out_path
```

- [ ] **Step 11.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_analyze.py -v 2>&1 | tail -10
```

Expected: 4 tests pass.

- [ ] **Step 11.5: Commit**

```bash
git add features/ingestion/src/ingestion/analyze.py features/ingestion/tests/unit/test_analyze.py
git commit -m "feat(ingestion): add analyze_pdf — PDF → wrapped JSON with metadata sidecar"
```

---

## Task 12: Phase-3 Verification (no new code, just check)

- [ ] **Step 12.1: Full ingestion suite so far**

```bash
pytest features/ingestion/ --cov=ingestion --cov-report=term-missing 2>&1 | tail -20
```

Expected: every test passes (slug + timestamp + config + client + analyze ≈ 21 tests). Coverage will be on the modules implemented so far. Some early-life modules will report < 90% in isolation; the package-level cov-fail-under threshold is acceptable to fail at this point because not all code is built yet — but every individual test must pass. If pytest exits non-zero **only because of `--cov-fail-under`**, that is acceptable; if it exits non-zero because of test failures, fix.

- [ ] **Step 12.2: Lint clean**

```bash
make lint 2>&1 | tail -10
```

Expected: zero ruff/mypy issues.

- [ ] **Step 12.3: Pre-commit on all files**

```bash
pre-commit run --all-files 2>&1 | tail -15
```

Expected: all hooks pass, including both boundary patterns.

- [ ] **Step 12.4: NO commit** for Task 12.

End of Phase 3.

---

# Phase 4 — `chunk` stage with chunker plugin

Goal: implement the chunker-plugin scaffolding (`chunkers/base.py`, `chunkers/section.py`, `chunkers/registry.py`) and the CLI-stage handler `chunk.py` that ties it together.

## Task 13: `chunkers/base.py` — `RawChunk` and `Chunker` Protocol

**Files:**
- Create: `features/ingestion/src/ingestion/chunkers/__init__.py` (empty)
- Create: `features/ingestion/src/ingestion/chunkers/base.py`
- Create: `features/ingestion/tests/unit/test_chunkers_base.py`

- [ ] **Step 13.1: Create empty `__init__.py`**

```bash
: > features/ingestion/src/ingestion/chunkers/__init__.py
```

- [ ] **Step 13.2: Write failing tests**

Create `features/ingestion/tests/unit/test_chunkers_base.py`:

```python
"""Tests for ingestion.chunkers.base — RawChunk dataclass and Chunker Protocol."""
from __future__ import annotations

from dataclasses import asdict, FrozenInstanceError

import pytest


def test_raw_chunk_holds_all_fields() -> None:
    from ingestion.chunkers.base import RawChunk

    rc = RawChunk(
        chunk_id="foo-001",
        title="Test Document",
        section_heading="1. Introduction",
        chunk="Body text.",
        source_file="foo.pdf",
    )
    assert rc.chunk_id == "foo-001"
    assert rc.title == "Test Document"
    assert rc.section_heading == "1. Introduction"
    assert rc.chunk == "Body text."
    assert rc.source_file == "foo.pdf"


def test_raw_chunk_round_trip_via_asdict() -> None:
    from ingestion.chunkers.base import RawChunk

    rc = RawChunk("foo-001", "T", "S", "body", "foo.pdf")
    out = asdict(rc)
    assert out == {
        "chunk_id": "foo-001",
        "title": "T",
        "section_heading": "S",
        "chunk": "body",
        "source_file": "foo.pdf",
    }
    rc2 = RawChunk(**out)
    assert rc2 == rc


def test_raw_chunk_is_frozen() -> None:
    from ingestion.chunkers.base import RawChunk

    rc = RawChunk("a", "b", "c", "d", "e")
    with pytest.raises(FrozenInstanceError):
        rc.chunk_id = "x"  # type: ignore[misc]


def test_chunker_protocol_is_runtime_checkable() -> None:
    """A class with the right shape passes isinstance() against Chunker."""
    from ingestion.chunkers.base import Chunker, RawChunk

    class FakeChunker:
        name = "fake"

        def chunk(
            self,
            analyze_result: dict,
            slug: str,
            source_file: str,
        ) -> list[RawChunk]:
            return []

    assert isinstance(FakeChunker(), Chunker)
```

- [ ] **Step 13.3: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_chunkers_base.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 13.4: Implement `chunkers/base.py`**

Create `features/ingestion/src/ingestion/chunkers/base.py`:

```python
"""RawChunk dataclass and Chunker Protocol.

The Chunker Protocol is the plugin point for chunking strategies. Each
strategy implementation declares a `name` (used in CLI --strategy and in
output filenames) and provides a `chunk()` method that yields RawChunks
from a Document Intelligence analyze result dict.

V1 ships only the section chunker (in `section.py`); future strategies
(fixed-size, llm-based) plug in at the same interface without changing
the CLI or downstream stages.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RawChunk:
    """One chunk produced by a chunker.

    Serialised to a JSONL line in the chunk-stage output. The `vector` field
    is added later by the embed stage, but is NOT part of RawChunk.
    """
    chunk_id: str
    title: str
    section_heading: str
    chunk: str
    source_file: str


@runtime_checkable
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

- [ ] **Step 13.5: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_chunkers_base.py -v 2>&1 | tail -10
```

Expected: 4 tests pass.

- [ ] **Step 13.6: Commit**

```bash
git add features/ingestion/src/ingestion/chunkers/__init__.py features/ingestion/src/ingestion/chunkers/base.py features/ingestion/tests/unit/test_chunkers_base.py
git commit -m "feat(ingestion): add RawChunk dataclass and Chunker Protocol"
```

---

## Task 14: `chunkers/section.py` — V1 Section Chunker

**Files:**
- Create: `features/ingestion/src/ingestion/chunkers/section.py`
- Create: `features/ingestion/tests/unit/test_chunkers_section.py`

- [ ] **Step 14.1: Write failing tests**

Create `features/ingestion/tests/unit/test_chunkers_section.py`:

```python
"""Tests for ingestion.chunkers.section.SectionChunker."""
from __future__ import annotations


def test_section_chunker_name() -> None:
    from ingestion.chunkers.section import SectionChunker

    assert SectionChunker.name == "section"


def test_section_chunker_produces_chunks_at_section_heading_boundaries(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="gnb-b-147-2001-rev-1",
        source_file="GNB B 147_2001 Rev. 1.pdf",
    )

    # The fixture has: title, pageHeader (skip), 1. Introduction, body x2,
    # pageFooter (skip), 2. Methods, body, footnote (skip).
    # Expected sections (in order, after title):
    #   1. Introduction → body paragraph 1 + body paragraph 2
    #   2. Methods      → methods body paragraph
    # Plus the title itself becomes a section start (the notebook chunker
    # treats title as a section heading).
    assert len(chunks) == 3  # title (no body), 1. Intro (2 bodies), 2. Methods (1 body)


def test_section_chunker_skips_noise_roles(sample_analyze_result: dict) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="x.pdf",
    )

    all_text = " ".join(c.chunk for c in chunks)
    assert "Page header" not in all_text
    assert "Page 2 / 5" not in all_text
    assert "Footnote text" not in all_text


def test_section_chunker_chunk_id_format(sample_analyze_result: dict) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="my-slug",
        source_file="x.pdf",
    )

    assert chunks[0].chunk_id == "my-slug-001"
    assert chunks[1].chunk_id == "my-slug-002"
    assert chunks[2].chunk_id == "my-slug-003"


def test_section_chunker_carries_title_into_each_chunk(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="x.pdf",
    )

    for c in chunks:
        assert c.title == "Test Document Title"


def test_section_chunker_section_heading_per_chunk(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="x.pdf",
    )

    headings = [c.section_heading for c in chunks]
    assert headings == ["Test Document Title", "1. Introduction", "2. Methods"]


def test_section_chunker_carries_source_file_into_each_chunk(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="my-file.pdf",
    )

    for c in chunks:
        assert c.source_file == "my-file.pdf"


def test_section_chunker_handles_empty_paragraphs() -> None:
    """A document with no paragraphs produces no chunks."""
    from ingestion.chunkers.section import SectionChunker

    empty = {"_ingestion_metadata": {}, "analyzeResult": {"paragraphs": []}}
    chunker = SectionChunker()
    chunks = chunker.chunk(empty, slug="x", source_file="x.pdf")
    assert chunks == []


def test_section_chunker_handles_no_title() -> None:
    """If no paragraph has role='title', title field is empty string."""
    from ingestion.chunkers.section import SectionChunker

    no_title = {
        "_ingestion_metadata": {},
        "analyzeResult": {
            "paragraphs": [
                {"content": "1. Section A", "role": "sectionHeading"},
                {"content": "Body", "role": None},
            ],
        },
    }
    chunker = SectionChunker()
    chunks = chunker.chunk(no_title, slug="x", source_file="x.pdf")
    assert len(chunks) == 1
    assert chunks[0].title == ""
```

- [ ] **Step 14.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_chunkers_section.py -v 2>&1 | tail -15
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 14.3: Implement `chunkers/section.py`**

Create `features/ingestion/src/ingestion/chunkers/section.py`:

```python
"""Section-based chunker — V1 strategy.

Direct port of the logic in `archive/semantic_chunking.ipynb`. Splits the
flat paragraph list from Document Intelligence into one chunk per section,
where a "section" is the run of body paragraphs between two consecutive
sectionHeading/title boundaries. Noise paragraphs (pageHeader, pageFooter,
pageNumber, footnote) are dropped.
"""
from __future__ import annotations

from ingestion.chunkers.base import RawChunk

SKIP_ROLES = frozenset({"pageHeader", "pageFooter", "pageNumber", "footnote"})


class SectionChunker:
    name = "section"

    def chunk(
        self,
        analyze_result: dict,
        slug: str,
        source_file: str,
    ) -> list[RawChunk]:
        result = analyze_result.get("analyzeResult", {})
        paragraphs = result.get("paragraphs", [])

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
        flush()  # don't forget the last section

        return chunks
```

- [ ] **Step 14.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_chunkers_section.py -v 2>&1 | tail -15
```

Expected: 9 tests pass.

- [ ] **Step 14.5: Commit**

```bash
git add features/ingestion/src/ingestion/chunkers/section.py features/ingestion/tests/unit/test_chunkers_section.py
git commit -m "feat(ingestion): add SectionChunker (V1 strategy from notebook)"
```

---

## Task 15: `chunkers/registry.py` — name → Chunker class mapping

**Files:**
- Create: `features/ingestion/src/ingestion/chunkers/registry.py`
- Create: `features/ingestion/tests/unit/test_chunkers_registry.py`

- [ ] **Step 15.1: Write failing tests**

Create `features/ingestion/tests/unit/test_chunkers_registry.py`:

```python
"""Tests for ingestion.chunkers.registry."""
from __future__ import annotations

import pytest


def test_get_chunker_returns_section_chunker() -> None:
    from ingestion.chunkers.registry import get_chunker
    from ingestion.chunkers.section import SectionChunker

    chunker = get_chunker("section")
    assert isinstance(chunker, SectionChunker)
    assert chunker.name == "section"


def test_get_chunker_raises_on_unknown_name() -> None:
    from ingestion.chunkers.registry import get_chunker

    with pytest.raises(ValueError, match="Unknown chunker strategy"):
        get_chunker("does-not-exist")


def test_get_chunker_error_lists_available_strategies() -> None:
    from ingestion.chunkers.registry import get_chunker

    with pytest.raises(ValueError) as excinfo:
        get_chunker("does-not-exist")
    assert "section" in str(excinfo.value)


def test_list_strategies_returns_sorted_names() -> None:
    from ingestion.chunkers.registry import list_strategies

    out = list_strategies()
    assert "section" in out
    assert out == sorted(out)
```

- [ ] **Step 15.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_chunkers_registry.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 15.3: Implement `chunkers/registry.py`**

Create `features/ingestion/src/ingestion/chunkers/registry.py`:

```python
"""Chunker name → class mapping.

To add a new strategy:
  1. Implement a class conforming to the Chunker Protocol in a new module
     under `chunkers/`.
  2. Import it here and add to _REGISTRY.
  3. Add tests for it under `tests/unit/test_chunkers_<name>.py`.

V1 ships only the section chunker.
"""
from __future__ import annotations

from ingestion.chunkers.base import Chunker
from ingestion.chunkers.section import SectionChunker

_REGISTRY: dict[str, type[Chunker]] = {
    "section": SectionChunker,
}


def get_chunker(name: str) -> Chunker:
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown chunker strategy: {name!r}. Available: {available}"
        )
    return _REGISTRY[name]()


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)
```

- [ ] **Step 15.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_chunkers_registry.py -v 2>&1 | tail -10
```

Expected: 4 tests pass.

- [ ] **Step 15.5: Commit**

```bash
git add features/ingestion/src/ingestion/chunkers/registry.py features/ingestion/tests/unit/test_chunkers_registry.py
git commit -m "feat(ingestion): add chunker registry (name -> class mapping)"
```

---

## Task 16: `chunk.py` — CLI-stage handler

**Files:**
- Create: `features/ingestion/src/ingestion/chunk.py`
- Create: `features/ingestion/tests/unit/test_chunk.py`

- [ ] **Step 16.1: Write failing tests**

Create `features/ingestion/tests/unit/test_chunk.py`:

```python
"""Tests for ingestion.chunk.chunk()."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _write_analyze_json(path: Path, slug: str, source_file: str) -> None:
    body = {
        "_ingestion_metadata": {
            "source_file": source_file,
            "slug": slug,
            "timestamp_utc": "20260427T143000",
        },
        "analyzeResult": {
            "paragraphs": [
                {"content": "Title", "role": "title"},
                {"content": "1. Intro", "role": "sectionHeading"},
                {"content": "Body.", "role": None},
            ],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def test_chunk_writes_jsonl_to_auto_derived_path(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "src" / "analyze.json"
    _write_analyze_json(in_path, slug="my-doc", source_file="my-doc.pdf")

    outputs_root = tmp_path / "outputs-root"
    with (
        patch("ingestion.chunk._outputs_root", return_value=outputs_root),
        patch("ingestion.chunk.now_compact_utc", return_value="20260427T143100"),
    ):
        out_path = chunk(in_path, strategy="section")

    expected = outputs_root / "my-doc" / "chunk" / "20260427T143100-section.jsonl"
    assert out_path == expected
    assert out_path.exists()


def test_chunk_writes_one_jsonl_line_per_chunk(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="x", source_file="x.pdf")
    out_path = tmp_path / "out.jsonl"

    chunk(in_path, strategy="section", out_path=out_path)

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2  # title (empty body) + 1. Intro section
    for line in lines:
        record = json.loads(line)
        assert "chunk_id" in record
        assert record["source_file"] == "x.pdf"


def test_chunk_uses_explicit_out_path_when_given(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="x", source_file="x.pdf")
    explicit = tmp_path / "explicit_dir" / "result.jsonl"

    out = chunk(in_path, strategy="section", out_path=explicit)

    assert out == explicit
    assert explicit.exists()


def test_chunk_raises_on_unknown_strategy(tmp_path: Path) -> None:
    import pytest

    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="x", source_file="x.pdf")

    with pytest.raises(ValueError, match="Unknown chunker strategy"):
        chunk(in_path, strategy="bogus", out_path=tmp_path / "out.jsonl")


def test_chunk_reads_slug_and_source_file_from_metadata(tmp_path: Path) -> None:
    """The user does not need to re-supply slug/source_file at chunk stage."""
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="from-meta", source_file="meta-file.pdf")
    out_path = tmp_path / "out.jsonl"

    chunk(in_path, strategy="section", out_path=out_path)
    line = json.loads(out_path.read_text(encoding="utf-8").strip().split("\n")[0])
    assert line["chunk_id"].startswith("from-meta-")
    assert line["source_file"] == "meta-file.pdf"
```

- [ ] **Step 16.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_chunk.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 16.3: Implement `chunk.py`**

Create `features/ingestion/src/ingestion/chunk.py`:

```python
"""CLI-stage handler for the chunk pipeline step.

Reads an analyze JSON (with `_ingestion_metadata` sidecar), runs the named
chunker strategy, writes a JSONL where each line is one RawChunk.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ingestion.chunkers.registry import get_chunker
from ingestion.timestamp import now_compact_utc


def _outputs_root() -> Path:
    """Return the repository's outputs root.

    Matches the discovery in analyze.py for consistency.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "features").is_dir():
            return parent / "outputs"
    return Path.cwd() / "outputs"


def chunk(
    in_path: Path,
    strategy: str,
    out_path: Path | None = None,
) -> Path:
    """Read an analyze JSON; run a chunker strategy; write chunks JSONL.

    Auto-derived `out_path` (if None): `<outputs_root>/<slug>/chunk/<ts>-<strategy>.jsonl`.

    Slug and source_file are read from the analyze JSON's `_ingestion_metadata`.
    """
    analyze_blob = json.loads(in_path.read_text(encoding="utf-8"))
    metadata = analyze_blob.get("_ingestion_metadata", {})
    slug = metadata.get("slug", "")
    source_file = metadata.get("source_file", "")

    chunker = get_chunker(strategy)  # raises ValueError on unknown name
    raw_chunks = chunker.chunk(analyze_blob, slug=slug, source_file=source_file)

    if out_path is None:
        ts = now_compact_utc()
        out_path = _outputs_root() / slug / "chunk" / f"{ts}-{strategy}.jsonl"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rc in raw_chunks:
            f.write(json.dumps(asdict(rc), ensure_ascii=False) + "\n")

    print(f"Wrote {len(raw_chunks)} chunks → {out_path}")
    return out_path
```

- [ ] **Step 16.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_chunk.py -v 2>&1 | tail -10
```

Expected: 5 tests pass.

- [ ] **Step 16.5: Commit**

```bash
git add features/ingestion/src/ingestion/chunk.py features/ingestion/tests/unit/test_chunk.py
git commit -m "feat(ingestion): add chunk CLI handler — analyze JSON → chunks JSONL"
```

---

# Phase 5 — `embed` stage

Goal: read a chunks JSONL, embed each chunk via Azure OpenAI (through `query_index.get_embedding`), write an embedded JSONL with a `vector` field added.

## Task 17: `embed.py`

**Files:**
- Create: `features/ingestion/src/ingestion/embed.py`
- Create: `features/ingestion/tests/unit/test_embed.py`

- [ ] **Step 17.1: Write failing tests**

Create `features/ingestion/tests/unit/test_embed.py`:

```python
"""Tests for ingestion.embed.embed_chunks()."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def _write_chunks_jsonl(path: Path, n: int = 2, *, slug: str = "x", chunk_text: str = "body") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(
                json.dumps({
                    "chunk_id": f"{slug}-{i+1:03d}",
                    "title": "T",
                    "section_heading": f"Section {i+1}",
                    "chunk": chunk_text,
                    "source_file": "x.pdf",
                }) + "\n"
            )


def test_embed_chunks_adds_vector_field_to_each_line(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_chunks_jsonl(in_path, n=3)

    fake_vec = [0.0] * 3072
    with patch("ingestion.embed.get_embedding", return_value=fake_vec):
        result_path = embed_chunks(in_path, out_path=out_path)

    assert result_path == out_path
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert record["vector"] == fake_vec
        assert "chunk_id" in record  # other fields preserved


def test_embed_chunks_passes_section_heading_plus_chunk_to_embedder(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Embed input is `{section_heading} {chunk}` per the notebook convention."""
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_chunks_jsonl(in_path, n=1, chunk_text="some body content")

    captured: dict = {}

    def fake_embed(text, cfg=None):
        captured["text"] = text
        return [0.0] * 3072

    with patch("ingestion.embed.get_embedding", side_effect=fake_embed):
        embed_chunks(in_path, out_path=out_path)

    assert "Section 1" in captured["text"]
    assert "some body content" in captured["text"]


def test_embed_chunks_truncates_long_text_to_8191_tokens(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Texts longer than 8191 tokens are truncated before embedding."""
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    huge = "word " * 50000  # ~50k tokens easily
    _write_chunks_jsonl(in_path, n=1, chunk_text=huge)

    captured: dict = {}

    def fake_embed(text, cfg=None):
        captured["text"] = text
        return [0.0] * 3072

    with patch("ingestion.embed.get_embedding", side_effect=fake_embed):
        embed_chunks(in_path, out_path=out_path)

    # Truncated text should be shorter than the input
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    assert len(enc.encode(captured["text"])) <= 8191


def test_embed_chunks_auto_derives_out_path(env_vars: dict[str, str], tmp_path: Path) -> None:
    from ingestion.embed import embed_chunks

    chunk_dir = tmp_path / "outputs-root" / "myslug" / "chunk"
    chunk_dir.mkdir(parents=True)
    in_path = chunk_dir / "20260427T143100-section.jsonl"
    _write_chunks_jsonl(in_path, n=1)

    with (
        patch("ingestion.embed.get_embedding", return_value=[0.0] * 3072),
        patch("ingestion.embed._outputs_root", return_value=tmp_path / "outputs-root"),
        patch("ingestion.embed.now_compact_utc", return_value="20260427T143200"),
    ):
        out = embed_chunks(in_path)

    expected = tmp_path / "outputs-root" / "myslug" / "embed" / "20260427T143200-section.jsonl"
    assert out == expected
    assert out.exists()
```

- [ ] **Step 17.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_embed.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 17.3: Implement `embed.py`**

Create `features/ingestion/src/ingestion/embed.py`:

```python
"""CLI-stage handler for the embed pipeline step.

Reads a chunks JSONL (text only), embeds each chunk via query_index's
`get_embedding`, writes an embedded JSONL with a `vector` field added.

Token truncation: each chunk's embed input (`{section_heading} {chunk}`)
is truncated to 8191 tokens — the hard limit of the text-embedding-3-large
model. Without truncation, very long sections (appendices, bibliographies)
cause API errors.
"""
from __future__ import annotations

import json
from pathlib import Path

import tiktoken
from query_index import Config, get_embedding

from ingestion.timestamp import now_compact_utc

_MAX_TOKENS = 8191
_ENC = tiktoken.get_encoding("cl100k_base")


def _truncate_for_embedding(text: str) -> str:
    tokens = _ENC.encode(text)
    if len(tokens) <= _MAX_TOKENS:
        return text
    return _ENC.decode(tokens[:_MAX_TOKENS])


def _outputs_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "features").is_dir():
            return parent / "outputs"
    return Path.cwd() / "outputs"


def _derive_out_path(in_path: Path) -> Path:
    """Auto-derive: outputs/<slug>/embed/<ts>-<strategy>.jsonl

    The strategy is taken from the input filename (e.g. '...-section.jsonl').
    The slug is taken from the parent-of-parent directory name.
    """
    # Expected layout: <outputs_root>/<slug>/chunk/<ts>-<strategy>.jsonl
    slug = in_path.parent.parent.name
    # Extract strategy from the filename suffix
    stem = in_path.stem  # e.g. '20260427T143100-section'
    parts = stem.split("-", 1)
    strategy = parts[1] if len(parts) > 1 else "unknown"
    ts = now_compact_utc()
    return _outputs_root() / slug / "embed" / f"{ts}-{strategy}.jsonl"


def embed_chunks(
    in_path: Path,
    out_path: Path | None = None,
    cfg: Config | None = None,
) -> Path:
    """Embed each chunk in `in_path`; write an embedded JSONL to `out_path`."""
    if cfg is None:
        cfg = Config.from_env()

    if out_path is None:
        out_path = _derive_out_path(in_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with in_path.open("r", encoding="utf-8") as src, out_path.open(
        "w", encoding="utf-8"
    ) as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            embed_text = _truncate_for_embedding(
                f"{record['section_heading']} {record['chunk']}"
            )
            record["vector"] = get_embedding(embed_text, cfg)
            dst.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    print(f"Embedded {n} chunks → {out_path}")
    return out_path
```

- [ ] **Step 17.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_embed.py -v 2>&1 | tail -10
```

Expected: 4 tests pass.

- [ ] **Step 17.5: Commit**

```bash
git add features/ingestion/src/ingestion/embed.py features/ingestion/tests/unit/test_embed.py
git commit -m "feat(ingestion): add embed stage with token truncation"
```

---

# Phase 6 — `upload` stage (multi-doc cumulative)

Goal: read an embedded JSONL, ensure the index exists with the right schema, delete only the chunks belonging to this file's `source_file`, then upload the new chunks.

## Task 18: `upload.py`

**Files:**
- Create: `features/ingestion/src/ingestion/upload.py`
- Create: `features/ingestion/tests/unit/test_upload.py`

- [ ] **Step 18.1: Write failing tests**

Create `features/ingestion/tests/unit/test_upload.py`:

```python
"""Tests for ingestion.upload.upload_chunks()."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _write_embedded_jsonl(path: Path, source_file: str = "x.pdf", n: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(
                json.dumps({
                    "chunk_id": f"slug-{i+1:03d}",
                    "title": "T",
                    "section_heading": f"Section {i+1}",
                    "chunk": f"body {i+1}",
                    "source_file": source_file,
                    "vector": [0.0] * 3072,
                }) + "\n"
            )


def _index_missing_response() -> Exception:
    """Build the kind of exception SearchIndexClient raises on missing index."""
    from azure.core.exceptions import ResourceNotFoundError
    return ResourceNotFoundError("not found")


def test_upload_chunks_creates_index_when_missing(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path)

    mock_index_client = MagicMock()
    mock_index_client.get_index.side_effect = _index_missing_response()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    mock_index_client.create_index.assert_called_once()


def test_upload_chunks_deletes_existing_chunks_for_same_source_file(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path, source_file="my-file.pdf")

    mock_index_client = MagicMock()
    mock_index_client.get_index.return_value = MagicMock()  # index exists
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = [
        {"id": "old-1"}, {"id": "old-2"},
    ]
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    # Search query must filter on source_file
    search_kwargs = mock_search_client.search.call_args.kwargs
    assert "source_file eq 'my-file.pdf'" in search_kwargs["filter"]

    # delete_documents called with the IDs from the search
    mock_search_client.delete_documents.assert_called_once()
    deleted_arg = mock_search_client.delete_documents.call_args.kwargs.get("documents") or \
                  mock_search_client.delete_documents.call_args.args[0]
    assert deleted_arg == [{"id": "old-1"}, {"id": "old-2"}]


def test_upload_chunks_does_not_delete_when_no_existing_chunks(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path)

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    mock_search_client.delete_documents.assert_not_called()


def test_upload_chunks_uploads_each_chunk_as_a_document(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path, n=5)

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        n_uploaded = upload_chunks(in_path)

    assert n_uploaded == 5
    docs = mock_search_client.upload_documents.call_args.kwargs.get("documents") or \
           mock_search_client.upload_documents.call_args.args[0]
    assert len(docs) == 5
    # Each document maps the embedded fields to the index schema
    for doc in docs:
        assert "id" in doc
        assert "chunk" in doc
        assert "chunkVector" in doc
        assert "source_file" in doc


def test_upload_chunks_force_recreate_drops_index(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path)

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path, force_recreate=True)

    mock_index_client.delete_index.assert_called_once()
    mock_index_client.create_index.assert_called_once()
    # delete-by-source-file should NOT happen when force_recreate is True
    mock_search_client.delete_documents.assert_not_called()


def test_upload_chunks_escapes_single_quotes_in_source_file(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Filenames with single quotes (e.g. O'Brien.pdf) must be OData-escaped."""
    from ingestion.upload import upload_chunks

    in_path = tmp_path / "embedded.jsonl"
    _write_embedded_jsonl(in_path, source_file="O'Brien.pdf")

    mock_index_client = MagicMock()
    mock_search_client = MagicMock()
    mock_search_client.search.return_value = []
    mock_search_client.upload_documents.return_value = []

    with (
        patch("ingestion.upload.get_search_index_client", return_value=mock_index_client),
        patch("ingestion.upload.get_search_client", return_value=mock_search_client),
    ):
        upload_chunks(in_path)

    filter_arg = mock_search_client.search.call_args.kwargs["filter"]
    assert "O''Brien.pdf" in filter_arg  # doubled single-quote per OData
```

- [ ] **Step 18.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_upload.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 18.3: Implement `upload.py`**

Create `features/ingestion/src/ingestion/upload.py`:

```python
"""CLI-stage handler for the upload pipeline step.

Reads an embedded JSONL, ensures the Azure AI Search index exists with the
canonical schema, deletes only the chunks for this file's source_file, and
uploads the new chunks. Multi-doc cumulative.
"""
from __future__ import annotations

import json
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from query_index import Config, get_search_client, get_search_index_client


_BATCH_SIZE = 100


def _escape_odata_string(s: str) -> str:
    """Per OData rules, single quotes inside a literal are doubled."""
    return s.replace("'", "''")


def _build_index_schema(index_name: str, embedding_dimensions: int) -> SearchIndex:
    """Construct the index definition matching the notebook schema."""
    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchableField(
            name="title",
            type=SearchFieldDataType.String,
            analyzer_name="de.lucene",
        ),
        SearchableField(
            name="section_heading",
            type=SearchFieldDataType.String,
            analyzer_name="de.lucene",
        ),
        SearchableField(
            name="chunk",
            type=SearchFieldDataType.String,
            analyzer_name="de.lucene",
        ),
        SimpleField(
            name="source_file",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="chunkVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=embedding_dimensions,
            vector_search_profile_name="default-vector-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="default-hnsw")],
        profiles=[
            VectorSearchProfile(
                name="default-vector-profile",
                algorithm_configuration_name="default-hnsw",
            )
        ],
    )
    semantic_search = SemanticSearch(configurations=[
        SemanticConfiguration(
            name="default-semantic-config",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="section_heading"),
                content_fields=[SemanticField(field_name="chunk")],
            ),
        ),
    ])
    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def _ensure_index_exists(index_client, index_name: str, embedding_dimensions: int) -> None:
    """Create the index if it does not exist; no-op otherwise."""
    try:
        index_client.get_index(index_name)
    except ResourceNotFoundError:
        index_client.create_index(_build_index_schema(index_name, embedding_dimensions))


def _delete_existing_chunks_for_source(search_client, source_file: str) -> int:
    """Find all chunks where source_file == <given>, delete by their ids."""
    escaped = _escape_odata_string(source_file)
    results = search_client.search(
        search_text="*",
        filter=f"source_file eq '{escaped}'",
        select=["id"],
        top=10000,
    )
    ids = [{"id": r["id"]} for r in results]
    if ids:
        search_client.delete_documents(documents=ids)
    return len(ids)


def _embedded_to_index_doc(record: dict) -> dict:
    """Map the embedded-JSONL line shape to the Azure index document shape."""
    return {
        "id": record["chunk_id"],
        "title": record["title"],
        "section_heading": record["section_heading"],
        "chunk": record["chunk"],
        "source_file": record["source_file"],
        "chunkVector": record["vector"],
    }


def upload_chunks(
    in_path: Path,
    index_name: str | None = None,
    force_recreate: bool = False,
    cfg: Config | None = None,
) -> int:
    """Upload embedded chunks to the Azure AI Search index.

    - If `force_recreate`: drop the entire index, create fresh, upload.
    - Else: ensure index exists (create if not), delete existing chunks where
      source_file matches this file's source_file, then upload.

    Returns the number of chunks uploaded.
    """
    if cfg is None:
        cfg = Config.from_env()
    if index_name is None:
        index_name = cfg.ai_search_index_name

    # Load all records, determine source_file from first line
    records: list[dict] = []
    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print(f"No chunks in {in_path}; nothing uploaded.")
        return 0

    source_file = records[0]["source_file"]
    index_client = get_search_index_client(cfg)
    search_client = get_search_client(cfg)

    deleted = 0
    if force_recreate:
        try:
            index_client.delete_index(index_name)
        except ResourceNotFoundError:
            pass
        index_client.create_index(_build_index_schema(index_name, cfg.embedding_dimensions))
    else:
        _ensure_index_exists(index_client, index_name, cfg.embedding_dimensions)
        deleted = _delete_existing_chunks_for_source(search_client, source_file)

    documents = [_embedded_to_index_doc(r) for r in records]
    for i in range(0, len(documents), _BATCH_SIZE):
        batch = documents[i : i + _BATCH_SIZE]
        search_client.upload_documents(documents=batch)

    print(
        f"Uploaded {len(documents)} chunks ({deleted} replaced) → {index_name}"
    )
    return len(documents)
```

- [ ] **Step 18.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_upload.py -v 2>&1 | tail -15
```

Expected: 6 tests pass.

- [ ] **Step 18.5: Commit**

```bash
git add features/ingestion/src/ingestion/upload.py features/ingestion/tests/unit/test_upload.py
git commit -m "feat(ingestion): add upload stage (multi-doc cumulative, delete-by-source_file)"
```

---

# Phase 7 — Public API + CLI integration

Goal: re-export the public symbols and tie all four subcommands together in `cli.py`.

## Task 19: Public API in `__init__.py`

**Files:**
- Modify: `features/ingestion/src/ingestion/__init__.py`
- Create: `features/ingestion/tests/unit/test_public_api.py`

- [ ] **Step 19.1: Write failing test**

Create `features/ingestion/tests/unit/test_public_api.py`:

```python
"""Tests for the re-exported public API at ingestion.__init__."""
from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import ingestion

    expected = {
        "IngestionConfig",
        "RawChunk",
        "analyze_pdf",
        "chunk",
        "embed_chunks",
        "get_chunker",
        "list_strategies",
        "slug_from_filename",
        "upload_chunks",
    }
    missing = expected - set(dir(ingestion))
    assert not missing, f"Missing public exports: {missing}"
```

- [ ] **Step 19.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_public_api.py -v 2>&1 | tail -10
```

Expected: failure citing missing exports.

- [ ] **Step 19.3: Populate `__init__.py`**

Replace the empty content of `features/ingestion/src/ingestion/__init__.py` with:

```python
"""Public API for the ingestion package."""
from ingestion.analyze import analyze_pdf
from ingestion.chunk import chunk
from ingestion.chunkers.base import RawChunk
from ingestion.chunkers.registry import get_chunker, list_strategies
from ingestion.config import IngestionConfig
from ingestion.embed import embed_chunks
from ingestion.slug import slug_from_filename
from ingestion.upload import upload_chunks

__all__ = [
    "IngestionConfig",
    "RawChunk",
    "analyze_pdf",
    "chunk",
    "embed_chunks",
    "get_chunker",
    "list_strategies",
    "slug_from_filename",
    "upload_chunks",
]
```

- [ ] **Step 19.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_public_api.py -v 2>&1 | tail -5
```

Expected: 1 test passes.

- [ ] **Step 19.5: Commit**

```bash
git add features/ingestion/src/ingestion/__init__.py features/ingestion/tests/unit/test_public_api.py
git commit -m "feat(ingestion): expose public API"
```

---

## Task 20: `cli.py` — Entry point with all four subcommands

**Files:**
- Create: `features/ingestion/src/ingestion/cli.py`
- Create: `features/ingestion/tests/unit/test_cli.py`

- [ ] **Step 20.1: Write failing tests**

Create `features/ingestion/tests/unit/test_cli.py`:

```python
"""Tests for the ingest CLI dispatcher."""
from __future__ import annotations

from unittest.mock import patch


def test_cli_dispatches_analyze() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.analyze_pdf") as mock_fn:
        rc = main(["analyze", "--in", "data/foo.pdf"])
    assert rc == 0
    mock_fn.assert_called_once()


def test_cli_dispatches_chunk_with_strategy() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.chunk") as mock_fn:
        rc = main(["chunk", "--in", "x.json", "--strategy", "section"])
    assert rc == 0
    args, kwargs = mock_fn.call_args
    # strategy passed through
    assert kwargs.get("strategy") == "section" or "section" in args


def test_cli_dispatches_embed() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.embed_chunks") as mock_fn:
        rc = main(["embed", "--in", "x.jsonl"])
    assert rc == 0
    mock_fn.assert_called_once()


def test_cli_dispatches_upload() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.upload_chunks") as mock_fn:
        rc = main(["upload", "--in", "x.jsonl"])
    assert rc == 0
    mock_fn.assert_called_once()


def test_cli_upload_passes_force_recreate_flag() -> None:
    from ingestion.cli import main

    with patch("ingestion.cli.upload_chunks") as mock_fn:
        main(["upload", "--in", "x.jsonl", "--force-recreate"])
    _, kwargs = mock_fn.call_args
    assert kwargs.get("force_recreate") is True


def test_cli_unknown_subcommand_returns_nonzero() -> None:
    from ingestion.cli import main

    rc = main(["unknown-thing"])
    assert rc != 0
```

- [ ] **Step 20.2: Run, confirm fail**

```bash
pytest features/ingestion/tests/unit/test_cli.py -v 2>&1 | tail -10
```

Expected: failures with `ModuleNotFoundError`.

- [ ] **Step 20.3: Implement `cli.py`**

Create `features/ingestion/src/ingestion/cli.py`:

```python
"""ingest CLI entry point. Four subcommands: analyze | chunk | embed | upload."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from ingestion.analyze import analyze_pdf
from ingestion.chunk import chunk
from ingestion.embed import embed_chunks
from ingestion.upload import upload_chunks


def _load_env() -> None:
    """Load .env from repo root once. Walk up from this file to find it."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        env_path = parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            return
    load_dotenv()


def _cmd_analyze(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    analyze_pdf(in_path=Path(args.in_path), out_path=out)
    return 0


def _cmd_chunk(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    chunk(in_path=Path(args.in_path), strategy=args.strategy, out_path=out)
    return 0


def _cmd_embed(args: argparse.Namespace) -> int:
    out = Path(args.out) if args.out else None
    embed_chunks(in_path=Path(args.in_path), out_path=out)
    return 0


def _cmd_upload(args: argparse.Namespace) -> int:
    upload_chunks(
        in_path=Path(args.in_path),
        index_name=args.index,
        force_recreate=args.force_recreate,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    _load_env()

    parser = argparse.ArgumentParser(prog="ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_analyze = sub.add_parser("analyze", help="PDF → analyze JSON")
    p_analyze.add_argument("--in", dest="in_path", required=True)
    p_analyze.add_argument("--out", default=None)
    p_analyze.set_defaults(func=_cmd_analyze)

    p_chunk = sub.add_parser("chunk", help="analyze JSON → chunks JSONL")
    p_chunk.add_argument("--in", dest="in_path", required=True)
    p_chunk.add_argument("--strategy", default="section")
    p_chunk.add_argument("--out", default=None)
    p_chunk.set_defaults(func=_cmd_chunk)

    p_embed = sub.add_parser("embed", help="chunks JSONL → embedded JSONL")
    p_embed.add_argument("--in", dest="in_path", required=True)
    p_embed.add_argument("--out", default=None)
    p_embed.set_defaults(func=_cmd_embed)

    p_upload = sub.add_parser("upload", help="embedded JSONL → Azure AI Search")
    p_upload.add_argument("--in", dest="in_path", required=True)
    p_upload.add_argument("--index", default=None)
    p_upload.add_argument("--force-recreate", action="store_true")
    p_upload.set_defaults(func=_cmd_upload)

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

- [ ] **Step 20.4: Run, confirm pass**

```bash
pytest features/ingestion/tests/unit/test_cli.py -v 2>&1 | tail -10
```

Expected: 6 tests pass.

- [ ] **Step 20.5: Verify the console script works**

```bash
ingest --help 2>&1 | head -20
```

Expected: argparse help text listing all four subcommands.

- [ ] **Step 20.6: Commit**

```bash
git add features/ingestion/src/ingestion/cli.py features/ingestion/tests/unit/test_cli.py
git commit -m "feat(ingestion): add ingest CLI dispatcher (analyze/chunk/embed/upload)"
```

---

# Phase 8 — Eval CLI updates + hash drift check

Goal: extend `query-index-eval`'s CLI to recognise per-doc paths via a new `--doc` flag, accept `--strategy` for report naming, and add an active hash-drift check in the runner.

## Task 21: `query-eval` CLI accepts `--doc` and `--strategy` flags

**Files:**
- Modify: `features/query-index-eval/src/query_index_eval/cli.py`
- Modify: `features/query-index-eval/tests/test_cli.py`

- [ ] **Step 21.1: Write failing tests**

Append to `features/query-index-eval/tests/test_cli.py`:

```python
def test_cli_eval_with_doc_uses_per_doc_dataset_default() -> None:
    """query-eval eval --doc foo defaults --dataset to outputs/foo/datasets/golden_v1.jsonl."""
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    _, kwargs = mock_run.call_args
    assert "outputs/myslug/datasets/golden_v1.jsonl" in str(kwargs["dataset_path"])


def test_cli_eval_with_doc_writes_report_to_per_doc_reports_dir() -> None:
    """query-eval eval --doc foo writes report under outputs/foo/reports/."""
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval") as mock_run,
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        mock_run.return_value = MagicMock()
        main(["eval", "--doc", "myslug", "--strategy", "section"])

    args, _ = mock_write.call_args
    out_dir = args[1]  # _write_report(report, out_dir)
    assert "outputs/myslug/reports" in str(out_dir)


def test_cli_eval_strategy_default_is_unspecified() -> None:
    """When --strategy is not passed, the default is 'unspecified'."""
    from query_index_eval.cli import main

    with (
        patch("query_index_eval.cli.run_eval"),
        patch("query_index_eval.cli._write_report") as mock_write,
        patch("query_index_eval.cli._print_summary"),
        patch("query_index_eval.cli.Config") as mock_cfg,
    ):
        mock_cfg.from_env.return_value = mock_cfg
        main(["eval", "--doc", "myslug"])

    # strategy is used to name the report file; it is passed via _write_report's
    # signature (or via the report.metadata). We check at least that it appears
    # in the eventual filename.
    # If your _write_report signature does not include strategy, the test below
    # may need to inspect the filename via mock_write.call_args.
    args, _ = mock_write.call_args
    # We expect _write_report(report, out_dir, strategy="unspecified")
    # or similar — adjust based on the actual signature.
```

(If the existing `_write_report` does not accept `strategy`, the test will fail and direct the implementation to add the parameter.)

- [ ] **Step 21.2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_cli.py -v 2>&1 | tail -10
```

Expected: 3 new tests fail (no `--doc` argument, no per-doc default).

- [ ] **Step 21.3: Update `cli.py`**

Modify `features/query-index-eval/src/query_index_eval/cli.py`:

1. In the argparse setup for the `eval` subparser, add:
   ```python
   p_eval.add_argument("--doc", default=None, help="Per-doc slug (defaults --dataset and --out under outputs/<slug>/)")
   p_eval.add_argument("--strategy", default="unspecified", help="Chunker strategy name; used in the report filename")
   ```

2. In `_cmd_eval`, derive defaults when `--doc` is given:
   ```python
   def _cmd_eval(args: argparse.Namespace) -> int:
       cfg = Config.from_env()
       if args.doc and not args.dataset:
           args.dataset = f"outputs/{args.doc}/datasets/golden_v1.jsonl"
       reports_dir = Path(f"outputs/{args.doc}/reports") if args.doc else DEFAULT_REPORTS_DIR
       report = run_eval(
           dataset_path=Path(args.dataset),
           top_k_max=args.top,
           cfg=cfg,
       )
       out_path = _write_report(report, reports_dir, strategy=args.strategy)
       _print_summary(report, out_path)
       return 0
   ```

3. Update `_write_report` signature to accept `strategy`:
   ```python
   def _write_report(report: MetricsReport, out_dir: Path, strategy: str = "unspecified") -> Path:  # pragma: no cover
       out_dir.mkdir(parents=True, exist_ok=True)
       timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
       out_path = out_dir / f"{timestamp}-{strategy}.json"
       out_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
       return out_path
   ```

4. Add `--doc` and matching dataset/path-derivation to `curate` and `report` subcommands the same way.

- [ ] **Step 21.4: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_cli.py -v 2>&1 | tail -15
```

Expected: all tests pass (existing + 3 new).

- [ ] **Step 21.5: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/cli.py features/query-index-eval/tests/test_cli.py
git commit -m "feat(eval-cli): add --doc and --strategy flags for per-doc workflows"
```

---

## Task 22: Hash-drift check in `runner.py`

**Files:**
- Modify: `features/query-index-eval/src/query_index_eval/runner.py`
- Modify: `features/query-index-eval/src/query_index_eval/schema.py` — extend MetricsReport.metadata
- Modify: `features/query-index-eval/tests/test_runner.py`

- [ ] **Step 22.1: Write failing tests**

Append to `features/query-index-eval/tests/test_runner.py`:

```python
def test_run_eval_detects_hash_drift_when_chunk_content_changed(
    tmp_dataset_path, env_vars,
) -> None:
    """If an expected chunk's hash no longer matches what is in the index,
    runner records the example's query_id in drifted_query_ids."""
    import json

    from query_index_eval.runner import run_eval

    # One example with a chunk_hash that will not match what get_chunk returns.
    rows = [{
        "query_id": "g0001",
        "query": "Q?",
        "expected_chunk_ids": ["c1"],
        "source": "curated",
        "chunk_hashes": {"c1": "sha256:expected-hash-from-curation-time"},
        "filter": None,
        "deprecated": False,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }]
    tmp_dataset_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk
        return Chunk(chunk_id="c1", title="T", chunk="DIFFERENT CONTENT NOW")

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert "g0001" in report.metadata.drifted_query_ids


def test_run_eval_no_drift_when_hash_matches(
    tmp_dataset_path, env_vars,
) -> None:
    """If the chunk's hash matches, drifted_query_ids stays empty."""
    import hashlib
    import json

    from query_index_eval.runner import run_eval

    chunk_text = "exact same content"
    expected_hash = (
        "sha256:" + hashlib.sha256(" ".join(chunk_text.split()).encode("utf-8")).hexdigest()
    )

    rows = [{
        "query_id": "g0001",
        "query": "Q?",
        "expected_chunk_ids": ["c1"],
        "source": "curated",
        "chunk_hashes": {"c1": expected_hash},
        "filter": None,
        "deprecated": False,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }]
    tmp_dataset_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk
        return Chunk(chunk_id="c1", title="T", chunk=chunk_text)

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.drifted_query_ids == []
```

- [ ] **Step 22.2: Run, confirm fail**

```bash
pytest features/query-index-eval/tests/test_runner.py::test_run_eval_detects_hash_drift_when_chunk_content_changed features/query-index-eval/tests/test_runner.py::test_run_eval_no_drift_when_hash_matches -v 2>&1 | tail -10
```

Expected: both fail (no `drifted_query_ids` field, no get_chunk call).

- [ ] **Step 22.3: Extend `RunMetadata` schema**

Modify `features/query-index-eval/src/query_index_eval/schema.py` so `RunMetadata` includes:

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
    drifted_query_ids: list[str] = field(default_factory=list)
    drift_warning: bool = False
```

(Add `field` import if not already there: `from dataclasses import dataclass, field`.)

- [ ] **Step 22.4: Update `runner.py`**

In `features/query-index-eval/src/query_index_eval/runner.py`:

1. Add import: `from query_index import get_chunk`
2. Add helper for hash check:

```python
import hashlib


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _hash_chunk(text: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def _check_drift(
    examples: list[EvalExample],
    cfg: Config,
) -> list[str]:
    """Return query_ids whose expected chunks no longer match recorded hashes."""
    drifted: list[str] = []
    for example in examples:
        if not example.chunk_hashes:
            continue
        for chunk_id, expected_hash in example.chunk_hashes.items():
            try:
                actual = get_chunk(chunk_id, cfg)
            except Exception:  # noqa: BLE001 — chunk not in index is also a kind of drift
                drifted.append(example.query_id)
                break
            actual_hash = _hash_chunk(actual.chunk)
            if actual_hash != expected_hash:
                drifted.append(example.query_id)
                break
    return drifted
```

3. In `run_eval`, after computing `active`, call `_check_drift(active, cfg)` and pass the result to `RunMetadata`:

```python
drifted_ids = _check_drift(active, cfg)
drift_warning = len(drifted_ids) > max(1, len(active) // 10)  # >10% threshold

metadata = RunMetadata(
    ...,
    drifted_query_ids=drifted_ids,
    drift_warning=drift_warning,
)
```

- [ ] **Step 22.5: Run, confirm pass**

```bash
pytest features/query-index-eval/tests/test_runner.py -v 2>&1 | tail -15
```

Expected: all runner tests pass, including the two new drift tests.

- [ ] **Step 22.6: Commit**

```bash
git add features/query-index-eval/src/query_index_eval/runner.py features/query-index-eval/src/query_index_eval/schema.py features/query-index-eval/tests/test_runner.py
git commit -m "feat(eval): add hash-drift check in runner; extend RunMetadata"
```

---

## Task 23: `Makefile` — `ingest-and-eval` convenience target

**Files:**
- Modify: `Makefile`

- [ ] **Step 23.1: Add the target**

Append to `Makefile`:

```makefile
ingest-and-eval:
	@if [ -z "$(DOC)" ] || [ -z "$(STRATEGY)" ] || [ -z "$(PDF)" ]; then \
	    echo 'Usage: make ingest-and-eval DOC=<slug> STRATEGY=<name> PDF=<path>'; \
	    echo 'Example: make ingest-and-eval DOC=gnb-b-147-2001-rev-1 STRATEGY=section PDF="data/GNB B 147_2001 Rev. 1.pdf"'; \
	    exit 1; \
	fi
	ingest analyze --in "$(PDF)"
	ingest chunk --in $$(ls -1t outputs/$(DOC)/analyze/*.json | head -1) --strategy $(STRATEGY)
	ingest embed --in $$(ls -1t outputs/$(DOC)/chunk/*-$(STRATEGY).jsonl | head -1)
	ingest upload --in $$(ls -1t outputs/$(DOC)/embed/*-$(STRATEGY).jsonl | head -1)
	query-eval eval --doc $(DOC) --strategy $(STRATEGY)
```

Also add to the `.PHONY` list at the top: `ingest-and-eval`.

Also add a help line in the `help:` target:
```
	@echo "  ingest-and-eval Run analyze->chunk->embed->upload->eval for one doc"
```

- [ ] **Step 23.2: Verify usage error message**

```bash
make ingest-and-eval 2>&1 | head -3
```

Expected: prints the "Usage:" hint.

- [ ] **Step 23.3: Commit**

```bash
git add Makefile
git commit -m "feat(makefile): add ingest-and-eval convenience target"
```

---

# Phase 9 — Acceptance + PR

## Task 24: Full system check

- [ ] **Step 24.1: Re-run bootstrap** (in case any new deps were added)

```bash
./bootstrap.sh
source .venv/bin/activate
```

Expected: completes without error; `query-index`, `query-index-eval`, and `ingestion` are all installed in editable mode.

- [ ] **Step 24.2: Full test run with coverage**

```bash
pytest features/ --cov=features --cov-report=term-missing 2>&1 | tail -30
```

Expected: every test passes; combined coverage ≥ 90%; per-package threshold met.

- [ ] **Step 24.3: Lint clean**

```bash
make lint 2>&1 | tail -10
```

Expected: zero ruff/mypy issues across all three packages.

- [ ] **Step 24.4: Pre-commit on all files**

```bash
pre-commit run --all-files 2>&1 | tail -15
```

Expected: all hooks pass, including both boundary patterns.

- [ ] **Step 24.5: Verify all four `ingest` subcommands have help text**

```bash
ingest --help 2>&1 | tail -10
ingest analyze --help 2>&1 | tail -5
ingest chunk --help 2>&1 | tail -5
ingest embed --help 2>&1 | tail -5
ingest upload --help 2>&1 | tail -5
```

Expected: each prints sensible argparse output.

- [ ] **Step 24.6: NO commit** for Task 24.

---

## Task 25: Boundary negative tests (manual verification)

- [ ] **Step 25.1: Plant a search-import violation in eval, verify hook catches it**

```bash
mkdir -p features/query-index-eval/src/_test_violation
echo 'import azure.search.documents' > features/query-index-eval/src/_test_violation/bad.py
git add features/query-index-eval/src/_test_violation/bad.py
pre-commit run --all-files 2>&1 | tail -10
echo "exit=$?"
git rm -f features/query-index-eval/src/_test_violation/bad.py
rmdir features/query-index-eval/src/_test_violation 2>/dev/null || true
git status
```

Expected: hook reports BOUNDARY VIOLATION; non-zero exit. After cleanup, working tree is clean.

- [ ] **Step 25.2: Plant a doc-intel violation in eval, verify hook catches it**

```bash
mkdir -p features/query-index-eval/src/_test_violation
echo 'from azure.ai.documentintelligence import DocumentIntelligenceClient' > features/query-index-eval/src/_test_violation/bad.py
git add features/query-index-eval/src/_test_violation/bad.py
pre-commit run --all-files 2>&1 | tail -10
echo "exit=$?"
git rm -f features/query-index-eval/src/_test_violation/bad.py
rmdir features/query-index-eval/src/_test_violation 2>/dev/null || true
git status
```

Expected: hook reports BOUNDARY VIOLATION (Check 2); non-zero exit. After cleanup, working tree is clean.

- [ ] **Step 25.3: Verify the legitimate ingestion doc-intel import still passes**

```bash
pre-commit run --all-files 2>&1 | tail -5
```

Expected: all hooks pass (the real ingestion code's `from azure.ai.documentintelligence import DocumentIntelligenceClient` is on the allow-list for Check 2).

- [ ] **Step 25.4: NO commit** for Task 25.

---

## Task 26: Final README polish

**Files:**
- Modify: `README.md`

- [ ] **Step 26.1: Update root `README.md` to mention the ingestion package**

In the `## Layout` section, add ingestion:

```
features/
  query-index/          # Azure AI Search wrapper (only package importing azure.search/openai)
  query-index-eval/     # retrieval-quality evaluation pipeline
  ingestion/            # PDF -> JSON -> chunks -> embeddings -> Azure index
archive/
  query_index_v0.py     # original prototype, preserved unchanged
  semantic_chunking.ipynb
  llm_query_index.ipynb
docs/
  superpowers/
    specs/
    plans/
  evaluation/
    metrics-rationale.md
```

In the `## Production workflow` section, add the ingestion-and-eval one-liner:

```bash
# Set up a fresh production workspace:
git clone <this repo> ~/code/DocumentAnalysisMicrosoft-real
cd ~/code/DocumentAnalysisMicrosoft-real
cp .env.example .env  # and fill in real keys
mkdir data && cp <real PDFs> data/
./bootstrap.sh
source .venv/bin/activate

# Ingest a PDF and immediately measure retrieval quality:
make ingest-and-eval DOC=gnb-b-147-2001-rev-1 STRATEGY=section PDF="data/GNB B 147_2001 Rev. 1.pdf"

# Or stage by stage:
ingest analyze --in data/foo.pdf                                      # PDF -> outputs/foo/analyze/<ts>.json
ingest chunk --in outputs/foo/analyze/<ts>.json --strategy section    # -> outputs/foo/chunk/<ts>-section.jsonl
ingest embed --in outputs/foo/chunk/<ts>-section.jsonl                # -> outputs/foo/embed/<ts>-section.jsonl
ingest upload --in outputs/foo/embed/<ts>-section.jsonl               # -> Azure AI Search index
query-eval curate --doc foo                                            # build outputs/foo/datasets/golden_v1.jsonl
query-eval eval --doc foo --strategy section                           # -> outputs/foo/reports/<ts>-section.json
```

- [ ] **Step 26.2: Commit**

```bash
git add README.md
git commit -m "docs: refresh top-level README with ingestion workflow"
```

---

## Task 27: Push branch and open PR

- [ ] **Step 27.1: Push the branch**

```bash
git push -u origin feat/ingestion-pipeline
```

Expected: branch is created on origin; tracking is set up.

- [ ] **Step 27.2: Open the PR**

```bash
gh pr create --base main --head feat/ingestion-pipeline \
  --title "feat: ingestion pipeline (analyze, chunk, embed, upload) + eval integration" \
  --body "$(cat <<'EOF'
## Summary

Implements `docs/superpowers/specs/2026-04-27-ingestion-design.md`. New `features/ingestion/` package providing four CLI stages (`ingest analyze | chunk | embed | upload`), plus eval-CLI updates (`--doc`, `--strategy` flags, hash drift check), plus a small refactor of `query-index` to adopt the canonical notebook schema.

## Architecture highlights

- **Strict per-package boundary**: `azure.search.*`/`azure.identity.*`/`openai.*` only in `query-index`; `azure.ai.documentintelligence.*` in `query-index` OR `ingestion`. `azure.core.credentials.AzureKeyCredential` allowed everywhere (credential primitive).
- **Per-doc outputs**: `outputs/{slug}/{stage}/{ts}-{strategy}.{ext}`. Multiple PDFs and chunker strategies coexist.
- **Multi-doc cumulative index**: `upload` deletes only chunks matching this file's `source_file` before uploading; multiple PDFs share the index.
- **Chunker plugin pattern**: `chunkers/base.py` Protocol + `chunkers/registry.py` lookup. V1 ships only `section` (port of notebook logic). New strategies plug in without touching CLI/upstream/downstream.
- **Hash drift detection**: `runner.py` actively compares `chunk_hashes` from golden against current index content; `RunMetadata.drifted_query_ids` lists examples with stale references.
- **Token truncation**: embed-stage truncates to 8191 tokens (text-embedding-3-large hard limit) via tiktoken.
- **Hybrid `cfg` convention** carries from `query-index`: every public function takes optional `cfg=None` defaulting to `*.from_env()`.

## Test plan

- [x] Unit tests pass (`make test`) — three packages, target ~150 tests
- [x] Coverage ≥ 90% per package
- [x] Lint clean (`make lint`) — ruff + mypy zero issues
- [x] Pre-commit clean (`pre-commit run --all-files`)
- [x] Boundary check catches a planted `azure.search` violation in `query-index-eval/`
- [x] Boundary check catches a planted `azure.ai.documentintelligence` violation in `query-index-eval/`
- [x] Boundary check ALLOWS `azure.ai.documentintelligence` in `ingestion/`
- [x] `ingest --help` lists all four subcommands
- [x] `query-eval --help` shows `--doc` and `--strategy` flags
- [x] Hash-drift test: planted hash mismatch is detected
- [ ] **End-to-end against a real Azure setup — verified by user in their separate cloned workspace** (per spec; AC11)

## What's NOT in this PR (deferred)

- Synthetic / LLM-based chunkers (plugin slot reserved)
- Audio/video ingestion (Document Intelligence is document-only)
- Production-scale parallelism
- CI / GitHub Actions (deferred until forcing function exists)

## Reference docs

- Spec: `docs/superpowers/specs/2026-04-27-ingestion-design.md`
- Plan: `docs/superpowers/plans/2026-04-27-ingestion-pipeline.md`
- Original prototypes preserved in `archive/`: `semantic_chunking.ipynb`, `llm_query_index.ipynb`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 27.3: Print the PR URL**

The `gh pr create` output ends with the URL. Capture it and report back to the user.

- [ ] **Step 27.4: NO commit** for Task 27 — the PR is a delivery action, not a code change.

---

## End of plan

After Task 27 the plan is fully executed. Outstanding work after merge is the same as before: the user verifies the system end-to-end in their separate cloned workspace with real Azure credentials, real PDFs, and a real (perhaps newly-created) Document Intelligence resource.

Future work tracked in the spec's "Out of scope" section: synthetic generation, fixed-size and LLM chunkers, audio/video ingestion via Content Understanding, CI workflows, production-scale parallelism.
