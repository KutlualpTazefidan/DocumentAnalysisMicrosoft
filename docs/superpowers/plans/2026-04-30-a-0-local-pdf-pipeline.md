# Local PDF Pipeline (Phase A.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a local, opinionated PDF-to-`SourceElement` pipeline (DocLayout-YOLO segmentation, MinerU 3 extraction, human-in-the-loop visual review UI) at `features/pipelines/local-pdf/` whose output drops into the existing goldens system without downstream changes.

**Architecture:** FastAPI backend mirroring A-Plus.1 (X-Auth-Token, 127.0.0.1 bind, NDJSON streaming, fcntl-locked sidecar JSON files in `data/raw-pdfs/<slug>/`) + React/Vite SPA mirroring A-Plus.2 (PDF.js page rendering, DOM-overlay box editor, Tiptap WYSIWYG with CodeMirror raw-mode, TanStack Query, hash routing). Three routes: `/inbox`, `/doc/<slug>/segment`, `/doc/<slug>/extract`. One doc at a time, single-user, auto-save with 300ms debounce.

**Tech Stack:** Python 3.11+ · FastAPI ≥0.110 · pydantic-settings 2 · uvicorn · pdfplumber · doclayout-yolo (opendatalab) · mineru (3.x) · pytest · httpx ‖ TypeScript 5 · React 18 · Vite 5 · TanStack Query 5 · Tailwind 3 · pdfjs-dist 4 · @tiptap/react 2 · @codemirror/view 6 · Vitest · React Testing Library · msw 2 · Playwright

**Spec:** `docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md`
**Prerequisites:** A-Plus.1 backend merged (provides `goldens.api.auth`, `goldens.api.identity`, `goldens.storage.log`); A-Plus.2 frontend merged (provides `frontend/src/api/client.ts` and `frontend/src/auth/`); SourceElement schema (PR #12) merged in `goldens.schemas.base`.

---

## File Map

**Created (production backend):**
- `features/pipelines/local-pdf/pyproject.toml`
- `features/pipelines/local-pdf/README.md`
- `features/pipelines/local-pdf/src/local_pdf/__init__.py`
- `features/pipelines/local-pdf/src/local_pdf/api/__init__.py`
- `features/pipelines/local-pdf/src/local_pdf/api/app.py`
- `features/pipelines/local-pdf/src/local_pdf/api/auth.py`
- `features/pipelines/local-pdf/src/local_pdf/api/config.py`
- `features/pipelines/local-pdf/src/local_pdf/api/schemas.py`
- `features/pipelines/local-pdf/src/local_pdf/api/routers/__init__.py`
- `features/pipelines/local-pdf/src/local_pdf/api/routers/docs.py`
- `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`
- `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`
- `features/pipelines/local-pdf/src/local_pdf/storage/__init__.py`
- `features/pipelines/local-pdf/src/local_pdf/storage/sidecar.py`
- `features/pipelines/local-pdf/src/local_pdf/storage/slug.py`
- `features/pipelines/local-pdf/src/local_pdf/workers/__init__.py`
- `features/pipelines/local-pdf/src/local_pdf/workers/yolo.py`
- `features/pipelines/local-pdf/src/local_pdf/workers/mineru.py`
- `features/pipelines/local-pdf/src/local_pdf/convert/__init__.py`
- `features/pipelines/local-pdf/src/local_pdf/convert/source_elements.py`

**Created (production frontend):**
- `frontend/src/local-pdf/routes/inbox.tsx`
- `frontend/src/local-pdf/routes/segment.tsx`
- `frontend/src/local-pdf/routes/extract.tsx`
- `frontend/src/local-pdf/components/PdfPage.tsx`
- `frontend/src/local-pdf/components/BoxOverlay.tsx`
- `frontend/src/local-pdf/components/PropertiesSidebar.tsx`
- `frontend/src/local-pdf/components/HtmlEditor.tsx`
- `frontend/src/local-pdf/components/StatusBadge.tsx`
- `frontend/src/local-pdf/api/client.ts`
- `frontend/src/local-pdf/api/docs.ts`
- `frontend/src/local-pdf/api/ndjson.ts`
- `frontend/src/local-pdf/hooks/usePdfPage.ts`
- `frontend/src/local-pdf/hooks/useBoxHotkeys.ts`
- `frontend/src/local-pdf/hooks/useDocs.ts`
- `frontend/src/local-pdf/hooks/useSegments.ts`
- `frontend/src/local-pdf/hooks/useExtract.ts`
- `frontend/src/local-pdf/types/domain.ts`
- `frontend/src/local-pdf/styles/box-colors.css`

**Modified:**
- `features/evaluators/chunk_match/src/query_index_eval/cli.py` — add `segment` subparser with `serve` action
- `frontend/src/App.tsx` — register three new routes under `/local-pdf/...`
- `frontend/src/components/TopBar.tsx` — add "Local PDF" nav link
- root `pyproject.toml` (workspace) or `Makefile` — register the new package install path

**Created (tests, backend):**
- `features/pipelines/local-pdf/tests/__init__.py`
- `features/pipelines/local-pdf/tests/conftest.py`
- `features/pipelines/local-pdf/tests/test_schemas.py`
- `features/pipelines/local-pdf/tests/test_config.py`
- `features/pipelines/local-pdf/tests/test_auth.py`
- `features/pipelines/local-pdf/tests/test_app.py`
- `features/pipelines/local-pdf/tests/test_storage_sidecar.py`
- `features/pipelines/local-pdf/tests/test_storage_slug.py`
- `features/pipelines/local-pdf/tests/test_workers_yolo.py`
- `features/pipelines/local-pdf/tests/test_workers_mineru.py`
- `features/pipelines/local-pdf/tests/test_routers_docs.py`
- `features/pipelines/local-pdf/tests/test_routers_segments.py`
- `features/pipelines/local-pdf/tests/test_routers_extract.py`
- `features/pipelines/local-pdf/tests/test_convert_source_elements.py`
- `features/pipelines/local-pdf/tests/test_cli_serve.py`

**Created (tests, frontend):**
- `frontend/tests/local-pdf/api/docs.test.ts`
- `frontend/tests/local-pdf/api/ndjson.test.ts`
- `frontend/tests/local-pdf/hooks/usePdfPage.test.ts`
- `frontend/tests/local-pdf/hooks/useBoxHotkeys.test.ts`
- `frontend/tests/local-pdf/components/BoxOverlay.test.tsx`
- `frontend/tests/local-pdf/components/HtmlEditor.test.tsx`
- `frontend/tests/local-pdf/routes/inbox.test.tsx`
- `frontend/tests/local-pdf/routes/segment.test.tsx`
- `frontend/tests/local-pdf/routes/extract.test.tsx`
- `frontend/tests/local-pdf/e2e/local-pdf-happy-path.spec.ts`

---

## Task 1: Add backend dependencies + scaffold package

**Files:**
- Create: `features/pipelines/local-pdf/pyproject.toml`
- Create: `features/pipelines/local-pdf/src/local_pdf/__init__.py`
- Create: `features/pipelines/local-pdf/README.md`

- [ ] **Step 1: Create `features/pipelines/local-pdf/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "local-pdf"
version = "0.1.0"
description = "Local PDF pipeline (DocLayout-YOLO + MinerU 3) producing canonical SourceElement JSON."
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110,<1.0",
    "pydantic>=2.5,<3",
    "pydantic-settings>=2.0,<3",
    "uvicorn[standard]>=0.27,<1.0",
    "pdfplumber>=0.11,<0.12",
    "doclayout-yolo>=0.0.4",
    "mineru>=3.0,<4",
    "python-multipart>=0.0.9",
    "goldens",
]

[project.optional-dependencies]
test = [
    "pytest>=8",
    "pytest-cov>=4",
    "httpx>=0.25",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = "src"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --cov=src/local_pdf --cov-report=term-missing"
```

- [ ] **Step 2: Create `features/pipelines/local-pdf/src/local_pdf/__init__.py`**

```python
"""Local PDF pipeline (Phase A.0).

DocLayout-YOLO segmentation + MinerU 3 extraction with a human-in-the-loop
visual review UI. Produces canonical SourceElement JSON drop-in compatible
with the existing goldens system.

See docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md.
"""

__all__: list[str] = []
```

- [ ] **Step 3: Create `features/pipelines/local-pdf/README.md`** (short — quickstart)

```markdown
# local-pdf

Phase A.0 — local, free-tools PDF → SourceElement pipeline.

## Quickstart

```bash
source .venv/bin/activate
uv pip install -e features/pipelines/local-pdf
export GOLDENS_API_TOKEN=$(openssl rand -hex 16)
export LOCAL_PDF_DATA_ROOT=$PWD/data/raw-pdfs
query-eval segment serve --port 8001
```

Then open http://127.0.0.1:5173/#/local-pdf/inbox in the dev frontend.

See `docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md`.
```

- [ ] **Step 4: Install + verify imports**

Run:
```bash
source .venv/bin/activate && uv pip install -e features/pipelines/local-pdf && python -c "import local_pdf; print('ok')"
```

Expected: `ok` printed; install succeeds.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/pyproject.toml features/pipelines/local-pdf/src/local_pdf/__init__.py features/pipelines/local-pdf/README.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf): scaffold package with deps (doclayout-yolo, mineru, fastapi, pdfplumber)"
```

---

## Task 2: Pydantic schemas (Doc, Segment, Box, Status, Kind)

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/__init__.py`
- Create: `features/pipelines/local-pdf/src/local_pdf/api/schemas.py`
- Create: `features/pipelines/local-pdf/tests/__init__.py`
- Create: `features/pipelines/local-pdf/tests/conftest.py`
- Create: `features/pipelines/local-pdf/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_schemas.py
"""Schema validation tests for local-pdf API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_box_kind_enum_has_eight_values() -> None:
    from local_pdf.api.schemas import BoxKind

    expected = {"heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "discard"}
    assert {k.value for k in BoxKind} == expected


def test_doc_status_enum_transitions() -> None:
    from local_pdf.api.schemas import DocStatus

    expected = {"raw", "segmenting", "extracting", "done", "needs_ocr"}
    assert {s.value for s in DocStatus} == expected


def test_segment_box_requires_positive_page_and_4tuple_bbox() -> None:
    from local_pdf.api.schemas import SegmentBox

    ok = SegmentBox(box_id="b-1", page=1, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.92)
    assert ok.box_id == "b-1"
    assert ok.bbox == (10, 20, 100, 200)

    with pytest.raises(ValidationError):
        SegmentBox(box_id="b-2", page=0, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.5)
    with pytest.raises(ValidationError):
        SegmentBox(box_id="b-3", page=1, bbox=(10, 20, 100), kind="paragraph", confidence=0.5)
    with pytest.raises(ValidationError):
        SegmentBox(box_id="", page=1, bbox=(10, 20, 100, 200), kind="paragraph", confidence=0.5)


def test_doc_meta_round_trip() -> None:
    from local_pdf.api.schemas import DocMeta, DocStatus

    m = DocMeta(
        slug="bam-tragkorb-2024",
        filename="BAM_Tragkorb_2024.pdf",
        pages=42,
        status=DocStatus.raw,
        last_touched_utc="2026-04-30T10:00:00Z",
    )
    j = m.model_dump(mode="json")
    assert j["status"] == "raw"
    assert DocMeta.model_validate(j) == m


def test_extract_event_discriminator() -> None:
    from pydantic import TypeAdapter
    from local_pdf.api.schemas import (
        ExtractCompleteLine,
        ExtractElementLine,
        ExtractErrorLine,
        ExtractLine,
        ExtractStartLine,
    )

    adapter: TypeAdapter[ExtractStartLine | ExtractElementLine | ExtractCompleteLine | ExtractErrorLine] = TypeAdapter(ExtractLine)
    assert isinstance(adapter.validate_python({"type": "start", "total_boxes": 12}), ExtractStartLine)
    assert isinstance(
        adapter.validate_python({"type": "element", "box_id": "b-1", "html_snippet": "<p>x</p>"}),
        ExtractElementLine,
    )
    assert isinstance(adapter.validate_python({"type": "complete", "boxes_extracted": 12}), ExtractCompleteLine)
    assert isinstance(adapter.validate_python({"type": "error", "box_id": "b-1", "reason": "vlm-timeout"}), ExtractErrorLine)


def test_update_box_request_kind_must_be_in_enum() -> None:
    from local_pdf.api.schemas import UpdateBoxRequest

    ok = UpdateBoxRequest(kind="heading", bbox=(10, 20, 100, 200))
    assert ok.kind == "heading"
    with pytest.raises(ValidationError):
        UpdateBoxRequest(kind="banana", bbox=(10, 20, 100, 200))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_schemas.py -v`

Expected: ImportError on `local_pdf.api.schemas`.

- [ ] **Step 3: Create empty conftest + api package**

```python
# features/pipelines/local-pdf/tests/__init__.py
```

```python
# features/pipelines/local-pdf/tests/conftest.py
"""Shared fixtures for local-pdf tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    return root
```

```python
# features/pipelines/local-pdf/src/local_pdf/api/__init__.py
"""HTTP API for local-pdf. See docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md."""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args, **kwargs):  # noqa: D401
    from local_pdf.api.app import create_app as real

    return real(*args, **kwargs)
```

- [ ] **Step 4: Implement `features/pipelines/local-pdf/src/local_pdf/api/schemas.py`**

```python
"""Pydantic schemas for the local-pdf HTTP API."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BoxKind(str, Enum):
    heading = "heading"
    paragraph = "paragraph"
    table = "table"
    figure = "figure"
    caption = "caption"
    formula = "formula"
    list_item = "list_item"
    discard = "discard"


class DocStatus(str, Enum):
    raw = "raw"
    segmenting = "segmenting"
    extracting = "extracting"
    done = "done"
    needs_ocr = "needs_ocr"


class SegmentBox(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_id: str
    page: int
    bbox: tuple[float, float, float, float]
    kind: BoxKind
    confidence: float = Field(ge=0.0, le=1.0)
    reading_order: int = 0

    @field_validator("box_id", mode="after")
    @classmethod
    def _box_id_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("box_id must be non-empty")
        return v

    @field_validator("page", mode="after")
    @classmethod
    def _page_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("page must be >= 1")
        return v


class SegmentsFile(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    boxes: list[SegmentBox]


class DocMeta(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str
    filename: str
    pages: int = Field(ge=1)
    status: DocStatus
    last_touched_utc: str
    box_count: int = 0


class UpdateBoxRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: BoxKind | None = None
    bbox: tuple[float, float, float, float] | None = None
    reading_order: int | None = None


class MergeBoxesRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_ids: list[str] = Field(min_length=2)


class SplitBoxRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_id: str
    split_y: float


class CreateBoxRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    page: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    kind: BoxKind = BoxKind.paragraph


class ExtractRegionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    box_id: str


class HtmlPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    html: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal["ok"] = "ok"
    data_root: str


# ── Streaming NDJSON line types ────────────────────────────────────────


class SegmentStartLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["start"] = "start"
    total_pages: int


class SegmentPageLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["page"] = "page"
    page: int
    boxes_found: int


class SegmentCompleteLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["complete"] = "complete"
    boxes_total: int


class SegmentErrorLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["error"] = "error"
    reason: str


SegmentLine = Annotated[
    SegmentStartLine | SegmentPageLine | SegmentCompleteLine | SegmentErrorLine,
    Field(discriminator="type"),
]


class ExtractStartLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["start"] = "start"
    total_boxes: int


class ExtractElementLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["element"] = "element"
    box_id: str
    html_snippet: str


class ExtractCompleteLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["complete"] = "complete"
    boxes_extracted: int


class ExtractErrorLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["error"] = "error"
    box_id: str | None = None
    reason: str


ExtractLine = Annotated[
    ExtractStartLine | ExtractElementLine | ExtractCompleteLine | ExtractErrorLine,
    Field(discriminator="type"),
]
```

- [ ] **Step 5: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_schemas.py -v`

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/__init__.py features/pipelines/local-pdf/src/local_pdf/api/schemas.py features/pipelines/local-pdf/tests/__init__.py features/pipelines/local-pdf/tests/conftest.py features/pipelines/local-pdf/tests/test_schemas.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): pydantic schemas (BoxKind, DocStatus, SegmentBox, NDJSON lines)"
```

---

## Task 3: ApiConfig (env-var settings)

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/config.py`
- Create: `features/pipelines/local-pdf/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_config.py
from __future__ import annotations

from pathlib import Path

import pytest


def test_config_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-xyz")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path / "raw-pdfs"))
    monkeypatch.setenv("LOCAL_PDF_LOG_LEVEL", "debug")
    monkeypatch.setenv("LOCAL_PDF_YOLO_WEIGHTS", str(tmp_path / "weights/doclayout.pt"))
    from local_pdf.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.api_token == "tok-xyz"
    assert cfg.data_root == tmp_path / "raw-pdfs"
    assert cfg.log_level == "debug"
    assert cfg.yolo_weights == tmp_path / "weights/doclayout.pt"


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.delenv("LOCAL_PDF_DATA_ROOT", raising=False)
    monkeypatch.delenv("LOCAL_PDF_LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOCAL_PDF_YOLO_WEIGHTS", raising=False)
    from local_pdf.api.config import ApiConfig

    cfg = ApiConfig()
    assert cfg.data_root == Path("data/raw-pdfs")
    assert cfg.log_level == "info"
    assert cfg.yolo_weights is None


def test_config_missing_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOLDENS_API_TOKEN", raising=False)
    from pydantic import ValidationError
    from local_pdf.api.config import ApiConfig

    with pytest.raises(ValidationError):
        ApiConfig()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_config.py -v`

Expected: ImportError on `local_pdf.api.config`.

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/api/config.py`**

```python
"""Runtime config sourced from env vars (via pydantic-settings).

Token comes from `GOLDENS_API_TOKEN` so a single token works across the
goldens API and this pipeline (matches A-Plus.1's env-var name).
Pipeline-specific knobs use the `LOCAL_PDF_` prefix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    api_token: str = Field(min_length=1, validation_alias="GOLDENS_API_TOKEN")
    data_root: Path = Field(default=Path("data/raw-pdfs"), validation_alias="LOCAL_PDF_DATA_ROOT")
    log_level: Literal["debug", "info", "warning", "error"] = Field(default="info", validation_alias="LOCAL_PDF_LOG_LEVEL")
    yolo_weights: Path | None = Field(default=None, validation_alias="LOCAL_PDF_YOLO_WEIGHTS")
    mineru_binary: str = Field(default="mineru", validation_alias="LOCAL_PDF_MINERU_BIN")
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_config.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/config.py features/pipelines/local-pdf/tests/test_config.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): ApiConfig pulls token + data_root + yolo_weights from env"
```

---

## Task 4: Auth middleware (X-Auth-Token, copied from A-Plus.1)

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/auth.py`
- Create: `features/pipelines/local-pdf/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_auth.py
from __future__ import annotations


def test_auth_allows_correct_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _p() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-good"})
    assert resp.status_code == 200


def test_auth_rejects_missing_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _p() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/protected")
    assert resp.status_code == 401
    assert "missing or invalid" in resp.json()["detail"].lower()


def test_auth_rejects_wrong_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _p() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-bad"})
    assert resp.status_code == 401


def test_auth_lets_health_through() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/health")
    def _h() -> dict:
        return {"status": "ok"}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_auth_lets_source_pdf_through_with_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/docs/{slug}/source.pdf")
    def _s(slug: str) -> dict:
        return {"slug": slug}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/docs/bam/source.pdf", headers={"X-Auth-Token": "tok-good"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_auth.py -v`

Expected: ImportError on `local_pdf.api.auth`.

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/api/auth.py`**

```python
"""X-Auth-Token middleware. Copied verbatim from goldens.api.auth (A-Plus.1).

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
        if path in _ALLOWLIST or any(path.startswith(prefix + "/") for prefix in _ALLOWLIST):
            return await call_next(request)
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

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_auth.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/auth.py features/pipelines/local-pdf/tests/test_auth.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): X-Auth-Token middleware (copied from A-Plus.1)"
```

---

## Task 5: Slug generator + storage helpers

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/storage/__init__.py`
- Create: `features/pipelines/local-pdf/src/local_pdf/storage/slug.py`
- Create: `features/pipelines/local-pdf/tests/test_storage_slug.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_storage_slug.py
from __future__ import annotations

from pathlib import Path


def test_slugify_filename_basic() -> None:
    from local_pdf.storage.slug import slugify_filename

    assert slugify_filename("BAM Tragkorb 2024.pdf") == "bam-tragkorb-2024"
    assert slugify_filename("DIN_EN_12100.pdf") == "din-en-12100"
    assert slugify_filename("normative.PDF") == "normative"


def test_slugify_strips_non_ascii() -> None:
    from local_pdf.storage.slug import slugify_filename

    assert slugify_filename("Prüfverfahren.pdf") == "prufverfahren"


def test_unique_slug_appends_counter_when_collision(tmp_path: Path) -> None:
    from local_pdf.storage.slug import unique_slug

    (tmp_path / "report").mkdir()
    (tmp_path / "report-2").mkdir()
    out = unique_slug(tmp_path, "Report.pdf")
    assert out == "report-3"


def test_unique_slug_no_collision_returns_base(tmp_path: Path) -> None:
    from local_pdf.storage.slug import unique_slug

    out = unique_slug(tmp_path, "Spec.pdf")
    assert out == "spec"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_storage_slug.py -v`

Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# features/pipelines/local-pdf/src/local_pdf/storage/__init__.py
"""Sidecar JSON storage for per-PDF state."""
```

```python
# features/pipelines/local-pdf/src/local_pdf/storage/slug.py
"""Deterministic slug derivation from a filename.

Slug rules:
- Lowercased, ASCII-only (Unicode NFKD-decomposed, non-ASCII stripped)
- Underscores and spaces become hyphens
- Trailing `.pdf` extension dropped
- On collision against an existing directory, append `-2`, `-3`, ...
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def slugify_filename(filename: str) -> str:
    """Return a slug suitable for `data/raw-pdfs/<slug>/`."""
    stem = filename
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    decomposed = unicodedata.normalize("NFKD", stem)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    hyphenated = re.sub(r"[\s_]+", "-", lowered)
    cleaned = re.sub(r"[^a-z0-9-]", "", hyphenated)
    collapsed = re.sub(r"-+", "-", cleaned).strip("-")
    return collapsed or "untitled"


def unique_slug(parent_dir: Path, filename: str) -> str:
    """Return a slug guaranteed not to collide with an existing subdir of parent_dir."""
    base = slugify_filename(filename)
    if not (parent_dir / base).exists():
        return base
    n = 2
    while (parent_dir / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_storage_slug.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/storage/__init__.py features/pipelines/local-pdf/src/local_pdf/storage/slug.py features/pipelines/local-pdf/tests/test_storage_slug.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/storage): slugify_filename + unique_slug for deterministic doc dirs"
```

---

## Task 6: Sidecar I/O wrapper (fcntl-locked read/write)

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/storage/sidecar.py`
- Create: `features/pipelines/local-pdf/tests/test_storage_sidecar.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_storage_sidecar.py
from __future__ import annotations

import json
from pathlib import Path


def test_write_and_read_meta(data_root: Path) -> None:
    from local_pdf.api.schemas import DocMeta, DocStatus
    from local_pdf.storage.sidecar import doc_dir, read_meta, write_meta

    slug = "report"
    doc_dir(data_root, slug).mkdir()
    meta = DocMeta(slug=slug, filename="Report.pdf", pages=10, status=DocStatus.raw, last_touched_utc="2026-04-30T10:00:00Z")
    write_meta(data_root, slug, meta)
    loaded = read_meta(data_root, slug)
    assert loaded == meta


def test_read_meta_returns_none_when_missing(data_root: Path) -> None:
    from local_pdf.storage.sidecar import read_meta

    assert read_meta(data_root, "missing") is None


def test_write_segments_round_trips(data_root: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.storage.sidecar import doc_dir, read_segments, write_segments

    slug = "rep"
    doc_dir(data_root, slug).mkdir()
    boxes = [SegmentBox(box_id="b-1", page=1, bbox=(10, 20, 100, 200), kind=BoxKind.paragraph, confidence=0.9)]
    write_segments(data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
    loaded = read_segments(data_root, slug)
    assert loaded is not None
    assert loaded.boxes == boxes


def test_read_segments_returns_none_when_missing(data_root: Path) -> None:
    from local_pdf.storage.sidecar import read_segments

    assert read_segments(data_root, "nope") is None


def test_write_html_and_read_back(data_root: Path) -> None:
    from local_pdf.storage.sidecar import doc_dir, read_html, write_html

    slug = "rep"
    doc_dir(data_root, slug).mkdir()
    write_html(data_root, slug, "<h1>Hello</h1>")
    assert read_html(data_root, slug) == "<h1>Hello</h1>"


def test_write_meta_uses_lock_and_overwrites_atomically(data_root: Path) -> None:
    """Two sequential writes leave only the latest content (no partial JSON)."""
    from local_pdf.api.schemas import DocMeta, DocStatus
    from local_pdf.storage.sidecar import doc_dir, read_meta, write_meta

    slug = "rep"
    doc_dir(data_root, slug).mkdir()
    a = DocMeta(slug=slug, filename="A.pdf", pages=1, status=DocStatus.raw, last_touched_utc="2026-04-30T10:00:00Z")
    b = DocMeta(slug=slug, filename="A.pdf", pages=1, status=DocStatus.segmenting, last_touched_utc="2026-04-30T10:01:00Z")
    write_meta(data_root, slug, a)
    write_meta(data_root, slug, b)
    out = read_meta(data_root, slug)
    assert out == b
    raw = json.loads((doc_dir(data_root, slug) / "meta.json").read_text(encoding="utf-8"))
    assert raw["status"] == "segmenting"


def test_doc_dir_path_layout(data_root: Path) -> None:
    from local_pdf.storage.sidecar import doc_dir

    assert doc_dir(data_root, "alpha") == data_root / "alpha"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_storage_sidecar.py -v`

Expected: ImportError on `local_pdf.storage.sidecar`.

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/storage/sidecar.py`**

```python
"""fcntl-locked read/write of per-PDF sidecar files.

Each PDF lives in `<data_root>/<slug>/` containing:
  - source.pdf          (immutable after upload)
  - meta.json           (DocMeta)
  - yolo.json           (raw DocLayout-YOLO output, immutable)
  - segments.json       (user-edited, SegmentsFile)
  - mineru-out.json     (raw MinerU output, immutable)
  - html.html           (user-edited HTML)
  - sourceelements.json (final canonical export)

All writes are LOCK_EX + write-then-fsync. Reads are tolerant: a missing
file returns None.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path

from local_pdf.api.schemas import DocMeta, SegmentsFile


def doc_dir(data_root: Path, slug: str) -> Path:
    return data_root / slug


def _meta_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "meta.json"


def _segments_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "segments.json"


def _html_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "html.html"


def _yolo_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "yolo.json"


def _mineru_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "mineru-out.json"


def _source_elements_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "sourceelements.json"


def _write_locked_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    os.replace(tmp, path)


def _read_text_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_meta(data_root: Path, slug: str, meta: DocMeta) -> None:
    payload = json.dumps(meta.model_dump(mode="json"), ensure_ascii=False, indent=2)
    _write_locked_text(_meta_path(data_root, slug), payload)


def read_meta(data_root: Path, slug: str) -> DocMeta | None:
    raw = _read_text_or_none(_meta_path(data_root, slug))
    if raw is None:
        return None
    return DocMeta.model_validate(json.loads(raw))


def write_segments(data_root: Path, slug: str, segments: SegmentsFile) -> None:
    payload = json.dumps(segments.model_dump(mode="json"), ensure_ascii=False, indent=2)
    _write_locked_text(_segments_path(data_root, slug), payload)


def read_segments(data_root: Path, slug: str) -> SegmentsFile | None:
    raw = _read_text_or_none(_segments_path(data_root, slug))
    if raw is None:
        return None
    return SegmentsFile.model_validate(json.loads(raw))


def write_html(data_root: Path, slug: str, html: str) -> None:
    _write_locked_text(_html_path(data_root, slug), html)


def read_html(data_root: Path, slug: str) -> str | None:
    return _read_text_or_none(_html_path(data_root, slug))


def write_yolo(data_root: Path, slug: str, payload: dict) -> None:
    _write_locked_text(_yolo_path(data_root, slug), json.dumps(payload, ensure_ascii=False, indent=2))


def read_yolo(data_root: Path, slug: str) -> dict | None:
    raw = _read_text_or_none(_yolo_path(data_root, slug))
    return json.loads(raw) if raw else None


def write_mineru(data_root: Path, slug: str, payload: dict) -> None:
    _write_locked_text(_mineru_path(data_root, slug), json.dumps(payload, ensure_ascii=False, indent=2))


def read_mineru(data_root: Path, slug: str) -> dict | None:
    raw = _read_text_or_none(_mineru_path(data_root, slug))
    return json.loads(raw) if raw else None


def write_source_elements(data_root: Path, slug: str, payload: dict) -> None:
    _write_locked_text(_source_elements_path(data_root, slug), json.dumps(payload, ensure_ascii=False, indent=2))


def read_source_elements(data_root: Path, slug: str) -> dict | None:
    raw = _read_text_or_none(_source_elements_path(data_root, slug))
    return json.loads(raw) if raw else None
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_storage_sidecar.py -v`

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/storage/sidecar.py features/pipelines/local-pdf/tests/test_storage_sidecar.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/storage): fcntl-locked sidecar I/O for meta/segments/html/yolo/mineru"
```

---

## Task 7: App factory + health endpoint + exception handlers

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/api/app.py`
- Create: `features/pipelines/local-pdf/src/local_pdf/api/routers/__init__.py`
- Create: `features/pipelines/local-pdf/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_app.py
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make():
        root = tmp_path / "raw-pdfs"
        root.mkdir()
        monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
        monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
        from local_pdf.api.app import create_app

        return create_app(), root

    return _make


def test_health_no_auth_required(make_app) -> None:
    from fastapi.testclient import TestClient

    app, root = make_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data_root"] == str(root)


def test_unknown_route_returns_404(make_app) -> None:
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/nope", headers={"X-Auth-Token": "tok-test"})
    assert resp.status_code == 404


def test_protected_routes_require_token(make_app) -> None:
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/docs")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_app.py -v`

Expected: ImportError on `local_pdf.api.app`.

- [ ] **Step 3: Implement**

```python
# features/pipelines/local-pdf/src/local_pdf/api/routers/__init__.py
"""Routers for local-pdf HTTP API."""
```

```python
# features/pipelines/local-pdf/src/local_pdf/api/app.py
"""FastAPI app factory for local-pdf.

create_app() loads ApiConfig, installs the X-Auth-Token middleware, mounts
the docs/segments/extract routers, and registers exception handlers.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_pdf.api.auth import install_auth_middleware
from local_pdf.api.config import ApiConfig
from local_pdf.api.schemas import HealthResponse


def create_app() -> FastAPI:
    cfg = ApiConfig()
    cfg.data_root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="local-pdf-api",
        version="0.1.0",
        description="Local PDF pipeline API (DocLayout-YOLO + MinerU 3).",
    )
    app.state.config = cfg

    install_auth_middleware(app, token=cfg.api_token)

    @app.exception_handler(FileNotFoundError)
    async def _file_not_found(_req: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_req: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health", response_model=HealthResponse)
    async def _health() -> HealthResponse:
        return HealthResponse(data_root=str(cfg.data_root))

    from local_pdf.api.routers.docs import router as docs_router
    from local_pdf.api.routers.extract import router as extract_router
    from local_pdf.api.routers.segments import router as segments_router

    app.include_router(docs_router)
    app.include_router(segments_router)
    app.include_router(extract_router)

    return app
```

Stub the routers so create_app can import (they get implemented in later tasks):

```python
# features/pipelines/local-pdf/src/local_pdf/api/routers/docs.py
"""Doc-level routes (inbox, upload, source.pdf serving). See Tasks 14-16."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
```

```python
# features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py
"""Segmenting routes (run YOLO, list/update/merge/split/delete boxes). See Tasks 8-12."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
```

```python
# features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py
"""Extraction routes (MinerU full + region, html GET/PUT, export). See Tasks 13, 17-19."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_app.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/app.py features/pipelines/local-pdf/src/local_pdf/api/routers/__init__.py features/pipelines/local-pdf/src/local_pdf/api/routers/docs.py features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py features/pipelines/local-pdf/tests/test_app.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): app factory + /api/health + auth middleware + router stubs"
```

---

## Task 8: DocLayout-YOLO worker module

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/workers/__init__.py`
- Create: `features/pipelines/local-pdf/src/local_pdf/workers/yolo.py`
- Create: `features/pipelines/local-pdf/tests/test_workers_yolo.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_workers_yolo.py
"""Tests for the DocLayout-YOLO worker wrapper.

The actual model is heavy and gated behind an env var. We test the wrapper's
input handling, deterministic box-id generation, and result conversion using
a fake `predict` callable injected via the public API.
"""

from __future__ import annotations

from pathlib import Path


def test_yolo_class_to_kind_mapping_covers_doclaynet_classes() -> None:
    from local_pdf.workers.yolo import YOLO_CLASS_TO_BOX_KIND

    # DocLayNet class names DocLayout-YOLO uses.
    for name in ("title", "plain text", "figure", "table", "list", "formula", "figure_caption", "abandon"):
        assert name in YOLO_CLASS_TO_BOX_KIND


def test_box_id_is_deterministic_per_page_and_index() -> None:
    from local_pdf.workers.yolo import make_box_id

    assert make_box_id(page=1, index=0) == "p1-b0"
    assert make_box_id(page=12, index=37) == "p12-b37"


def test_run_yolo_with_injected_predict(tmp_path: Path) -> None:
    """Run end-to-end with a fake predict() that returns one synthetic box."""
    from local_pdf.api.schemas import BoxKind
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox, run_yolo

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")

    def fake_predict(_path: Path) -> list[YOLOPagePrediction]:
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                    YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
                ],
            )
        ]

    boxes = run_yolo(pdf, predict_fn=fake_predict)
    assert len(boxes) == 2
    assert boxes[0].box_id == "p1-b0"
    assert boxes[0].kind == BoxKind.heading
    assert boxes[0].confidence == 0.95
    assert boxes[1].kind == BoxKind.paragraph
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_workers_yolo.py -v`

Expected: ImportError on `local_pdf.workers.yolo`.

- [ ] **Step 3: Implement**

```python
# features/pipelines/local-pdf/src/local_pdf/workers/__init__.py
"""Workers wrapping DocLayout-YOLO (segmentation) and MinerU 3 (extraction)."""
```

```python
# features/pipelines/local-pdf/src/local_pdf/workers/yolo.py
"""DocLayout-YOLO segmentation wrapper.

Public entry point: `run_yolo(pdf_path, *, predict_fn=None)`. When
`predict_fn` is None, the default loads the doclayout_yolo package and
the configured weights (LOCAL_PDF_YOLO_WEIGHTS) and runs inference.
Tests inject a fake predict_fn to avoid loading the real model.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from local_pdf.api.schemas import BoxKind, SegmentBox


# DocLayNet class names from DocLayout-YOLO -> our BoxKind enum.
YOLO_CLASS_TO_BOX_KIND: dict[str, BoxKind] = {
    "title": BoxKind.heading,
    "plain text": BoxKind.paragraph,
    "figure": BoxKind.figure,
    "figure_caption": BoxKind.caption,
    "table": BoxKind.table,
    "table_caption": BoxKind.caption,
    "table_footnote": BoxKind.caption,
    "list": BoxKind.list_item,
    "formula": BoxKind.formula,
    "formula_caption": BoxKind.caption,
    "abandon": BoxKind.discard,
}


class YOLOPredictedBox(NamedTuple):
    class_name: str
    bbox: tuple[float, float, float, float]
    confidence: float


class YOLOPagePrediction(NamedTuple):
    page: int
    width: int
    height: int
    boxes: list[YOLOPredictedBox]


PredictFn = Callable[[Path], list[YOLOPagePrediction]]


def make_box_id(page: int, index: int) -> str:
    return f"p{page}-b{index}"


def _default_predict(pdf_path: Path) -> list[YOLOPagePrediction]:
    """Real DocLayout-YOLO inference. Lazy-imports the heavy deps."""
    from doclayout_yolo import YOLOv10  # type: ignore[import-untyped]
    import pdfplumber  # type: ignore[import-untyped]
    from PIL import Image  # type: ignore[import-untyped]
    import io
    import os

    weights = os.environ.get("LOCAL_PDF_YOLO_WEIGHTS")
    if not weights:
        raise RuntimeError("LOCAL_PDF_YOLO_WEIGHTS env var not set")

    model = YOLOv10(weights)
    out: list[YOLOPagePrediction] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            im = page.to_image(resolution=144).original
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            img = Image.open(io.BytesIO(buf.getvalue()))
            res = model.predict(img, imgsz=1024, conf=0.2)[0]
            preds: list[YOLOPredictedBox] = []
            for cls_id, box, conf in zip(res.boxes.cls.tolist(), res.boxes.xyxy.tolist(), res.boxes.conf.tolist(), strict=True):
                name = res.names[int(cls_id)]
                preds.append(YOLOPredictedBox(class_name=name, bbox=tuple(box), confidence=float(conf)))
            out.append(YOLOPagePrediction(page=i, width=im.width, height=im.height, boxes=preds))
    return out


def run_yolo(pdf_path: Path, *, predict_fn: PredictFn | None = None) -> list[SegmentBox]:
    """Run DocLayout-YOLO on a PDF and return canonical SegmentBox list."""
    fn = predict_fn or _default_predict
    pages = fn(pdf_path)
    out: list[SegmentBox] = []
    for page_pred in pages:
        for idx, b in enumerate(page_pred.boxes):
            kind = YOLO_CLASS_TO_BOX_KIND.get(b.class_name, BoxKind.paragraph)
            out.append(
                SegmentBox(
                    box_id=make_box_id(page_pred.page, idx),
                    page=page_pred.page,
                    bbox=b.bbox,
                    kind=kind,
                    confidence=b.confidence,
                    reading_order=idx,
                )
            )
    return out
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_workers_yolo.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/workers/__init__.py features/pipelines/local-pdf/src/local_pdf/workers/yolo.py features/pipelines/local-pdf/tests/test_workers_yolo.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/workers): DocLayout-YOLO wrapper with injectable predict_fn for tests"
```

---

## Task 9: MinerU 3 worker module

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/workers/mineru.py`
- Create: `features/pipelines/local-pdf/tests/test_workers_mineru.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_workers_mineru.py
"""Tests for the MinerU 3 worker wrapper.

The real MinerU CLI is heavy + slow; we inject a fake `extract_fn` to
verify the wrapper's box-by-box dispatch and result-mapping behaviour.
"""

from __future__ import annotations

from pathlib import Path


def test_run_mineru_per_box_uses_injected_extract_fn(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, run_mineru

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.heading, confidence=0.95),
        SegmentBox(box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.88),
    ]

    def fake_extract(_pdf: Path, box: SegmentBox) -> MinerUResult:
        return MinerUResult(box_id=box.box_id, html=f"<{'h1' if box.kind == BoxKind.heading else 'p'}>{box.box_id}</{'h1' if box.kind == BoxKind.heading else 'p'}>")

    out = list(run_mineru(pdf, boxes, extract_fn=fake_extract))
    assert len(out) == 2
    assert out[0].box_id == "p1-b0"
    assert out[0].html == "<h1>p1-b0</h1>"
    assert out[1].html == "<p>p1-b1</p>"


def test_run_mineru_skips_discard_kind(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, run_mineru

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    boxes = [
        SegmentBox(box_id="p1-b0", page=1, bbox=(10, 20, 100, 60), kind=BoxKind.discard, confidence=0.5),
        SegmentBox(box_id="p1-b1", page=1, bbox=(10, 70, 100, 200), kind=BoxKind.paragraph, confidence=0.9),
    ]

    def fake(_p: Path, box: SegmentBox) -> MinerUResult:
        return MinerUResult(box_id=box.box_id, html=f"<p>{box.box_id}</p>")

    out = list(run_mineru(pdf, boxes, extract_fn=fake))
    assert [r.box_id for r in out] == ["p1-b1"]


def test_run_mineru_region_calls_extract_once(tmp_path: Path) -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox
    from local_pdf.workers.mineru import MinerUResult, run_mineru_region

    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF\n")
    box = SegmentBox(box_id="p2-b3", page=2, bbox=(50, 50, 200, 200), kind=BoxKind.table, confidence=0.7)

    calls: list[str] = []

    def fake(_p: Path, b: SegmentBox) -> MinerUResult:
        calls.append(b.box_id)
        return MinerUResult(box_id=b.box_id, html="<table><tr><td>x</td></tr></table>")

    out = run_mineru_region(pdf, box, extract_fn=fake)
    assert calls == ["p2-b3"]
    assert out.html.startswith("<table>")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_workers_mineru.py -v`

Expected: ImportError on `local_pdf.workers.mineru`.

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/workers/mineru.py`**

```python
"""MinerU 3 extraction wrapper.

Per spec D5/D17: full-doc extract walks every non-discard box and yields a
MinerUResult per box. region extract runs MinerU on a single bbox.

The default extract_fn invokes the `mineru` CLI (configurable via env
LOCAL_PDF_MINERU_BIN). Tests inject a fake to avoid the heavy VLM.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from local_pdf.api.schemas import BoxKind, SegmentBox


@dataclass(frozen=True)
class MinerUResult:
    box_id: str
    html: str


ExtractFn = Callable[[Path, SegmentBox], MinerUResult]


def _default_extract(pdf_path: Path, box: SegmentBox) -> MinerUResult:
    """Real MinerU 3 invocation. Crops the page region and runs the CLI."""
    binary = os.environ.get("LOCAL_PDF_MINERU_BIN", "mineru")
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        cmd = [
            binary,
            "-p", str(pdf_path),
            "-o", str(out_dir),
            "--page", str(box.page),
            "--bbox", f"{box.bbox[0]},{box.bbox[1]},{box.bbox[2]},{box.bbox[3]}",
            "--format", "html",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"mineru failed: {proc.stderr}")
        out_html = out_dir / "result.html"
        out_json = out_dir / "result.json"
        if out_html.exists():
            html = out_html.read_text(encoding="utf-8")
        elif out_json.exists():
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            html = payload.get("html", "")
        else:
            html = proc.stdout
        return MinerUResult(box_id=box.box_id, html=html)


def run_mineru(
    pdf_path: Path,
    boxes: list[SegmentBox],
    *,
    extract_fn: ExtractFn | None = None,
) -> Iterator[MinerUResult]:
    """Yield one MinerUResult per non-discard box, in input order."""
    fn = extract_fn or _default_extract
    for box in boxes:
        if box.kind == BoxKind.discard:
            continue
        yield fn(pdf_path, box)


def run_mineru_region(
    pdf_path: Path,
    box: SegmentBox,
    *,
    extract_fn: ExtractFn | None = None,
) -> MinerUResult:
    """Extract a single bbox region (re-extract path; spec D17)."""
    fn = extract_fn or _default_extract
    return fn(pdf_path, box)
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_workers_mineru.py -v`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/workers/mineru.py features/pipelines/local-pdf/tests/test_workers_mineru.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/workers): MinerU 3 wrapper with full-doc + region modes (injectable extract_fn)"
```

---

## Task 10: POST /api/docs (upload) + GET /api/docs (inbox listing)

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/docs.py`
- Create: `features/pipelines/local-pdf/tests/test_routers_docs.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_routers_docs.py
from __future__ import annotations

import io
from pathlib import Path

import pytest


@pytest.fixture
def client_and_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient

    from local_pdf.api.app import create_app

    return TestClient(create_app()), root


def _pdf_bytes() -> bytes:
    # Minimal valid-ish PDF header. pdfplumber will fail to parse this so the
    # upload route only checks magic + persists; page count comes from a
    # tolerant counter implemented in the router (or fallback to 0).
    return b"%PDF-1.4\n%%EOF\n"


def test_upload_pdf_creates_slug_dir(client_and_root) -> None:
    client, root = client_and_root
    files = {"file": ("BAM Tragkorb 2024.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    resp = client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "bam-tragkorb-2024"
    assert body["status"] == "raw"
    assert (root / "bam-tragkorb-2024" / "source.pdf").exists()
    assert (root / "bam-tragkorb-2024" / "meta.json").exists()


def test_upload_collision_appends_counter(client_and_root) -> None:
    client, root = client_and_root
    (root / "report").mkdir()
    files = {"file": ("Report.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    resp = client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert resp.status_code == 201
    assert resp.json()["slug"] == "report-2"


def test_upload_rejects_non_pdf(client_and_root) -> None:
    client, _ = client_and_root
    files = {"file": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
    resp = client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    assert resp.status_code == 400


def test_inbox_lists_uploaded_docs(client_and_root) -> None:
    client, _ = client_and_root
    files1 = {"file": ("A.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    files2 = {"file": ("B.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files1)
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files2)
    resp = client.get("/api/docs", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    slugs = {d["slug"] for d in resp.json()}
    assert slugs == {"a", "b"}


def test_get_doc_returns_meta(client_and_root) -> None:
    client, _ = client_and_root
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    resp = client.get("/api/docs/spec", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    assert resp.json()["slug"] == "spec"


def test_get_unknown_doc_returns_404(client_and_root) -> None:
    client, _ = client_and_root
    resp = client.get("/api/docs/nonexistent", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_source_pdf_serves_bytes(client_and_root) -> None:
    client, _ = client_and_root
    files = {"file": ("Spec.pdf", io.BytesIO(_pdf_bytes()), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    resp = client.get("/api/docs/spec/source.pdf", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == _pdf_bytes()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_docs.py -v`

Expected: 7 failures (route returns 404 because router is currently empty).

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/api/routers/docs.py`**

```python
"""Doc-level routes: inbox listing, upload, metadata, source PDF serving."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from local_pdf.api.schemas import DocMeta, DocStatus
from local_pdf.storage.sidecar import doc_dir, read_meta, write_meta
from local_pdf.storage.slug import unique_slug

router = APIRouter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_pages(pdf_path) -> int:
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(str(pdf_path)) as p:
            return len(p.pages)
    except Exception:
        return 1


@router.get("/api/docs")
async def list_docs(request: Request) -> list[dict]:
    cfg = request.app.state.config
    out: list[dict] = []
    if not cfg.data_root.exists():
        return out
    for entry in sorted(cfg.data_root.iterdir()):
        if not entry.is_dir():
            continue
        meta = read_meta(cfg.data_root, entry.name)
        if meta is not None:
            out.append(meta.model_dump(mode="json"))
    return out


@router.post("/api/docs", status_code=201)
async def upload_doc(request: Request, file: UploadFile) -> JSONResponse:
    cfg = request.app.state.config
    filename = file.filename or "untitled.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF uploads accepted")
    blob = await file.read()
    if not blob.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="not a PDF (missing %PDF magic)")

    slug = unique_slug(cfg.data_root, filename)
    target = doc_dir(cfg.data_root, slug)
    target.mkdir(parents=True, exist_ok=True)
    pdf_path = target / "source.pdf"
    pdf_path.write_bytes(blob)
    pages = _count_pages(pdf_path)
    meta = DocMeta(
        slug=slug,
        filename=filename,
        pages=max(pages, 1),
        status=DocStatus.raw,
        last_touched_utc=_now_iso(),
    )
    write_meta(cfg.data_root, slug, meta)
    return JSONResponse(status_code=201, content=meta.model_dump(mode="json"))


@router.get("/api/docs/{slug}")
async def get_doc(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    meta = read_meta(cfg.data_root, slug)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    return meta.model_dump(mode="json")


@router.get("/api/docs/{slug}/source.pdf")
async def get_source_pdf(slug: str, request: Request) -> FileResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    return FileResponse(str(pdf), media_type="application/pdf")
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_docs.py -v`

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/docs.py features/pipelines/local-pdf/tests/test_routers_docs.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): inbox + upload + meta + source.pdf serving routes"
```

---

## Task 11: POST /api/docs/{slug}/segment (NDJSON streaming) + GET segments

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`
- Create: `features/pipelines/local-pdf/tests/test_routers_segments.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_routers_segments.py
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def app_with_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    # Inject fake YOLO predict_fn via a module-level hook on the segments router.
    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox
    import local_pdf.api.routers.segments as seg_mod

    def fake_predict(_pdf):
        return [
            YOLOPagePrediction(
                page=1,
                width=600,
                height=800,
                boxes=[
                    YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                    YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
                ],
            ),
            YOLOPagePrediction(
                page=2,
                width=600,
                height=800,
                boxes=[YOLOPredictedBox(class_name="table", bbox=(15, 30, 580, 700), confidence=0.91)],
            ),
        ]

    seg_mod._YOLO_PREDICT_FN = fake_predict

    from fastapi.testclient import TestClient

    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    yield client, root, "doc"

    seg_mod._YOLO_PREDICT_FN = None


def test_segment_streams_ndjson_and_persists(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream("POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}) as resp:
        assert resp.status_code == 200
        lines = [json.loads(l) for l in resp.iter_lines() if l]
    assert lines[0] == {"type": "start", "total_pages": 2}
    assert {l["type"] for l in lines} == {"start", "page", "complete"}
    assert lines[-1]["type"] == "complete"
    assert lines[-1]["boxes_total"] == 3

    seg_path = root / slug / "segments.json"
    assert seg_path.exists()
    payload = json.loads(seg_path.read_text(encoding="utf-8"))
    assert len(payload["boxes"]) == 3
    assert {b["page"] for b in payload["boxes"]} == {1, 2}


def test_segment_writes_yolo_json_immutable(app_with_doc) -> None:
    client, root, slug = app_with_doc
    with client.stream("POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    assert (root / slug / "yolo.json").exists()


def test_get_segments_returns_persisted_boxes(app_with_doc) -> None:
    client, _, slug = app_with_doc
    with client.stream("POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    resp = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == slug
    assert len(body["boxes"]) == 3


def test_get_segments_404_when_not_yet_run(app_with_doc) -> None:
    client, _, slug = app_with_doc
    resp = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404


def test_segment_unknown_slug_404(app_with_doc) -> None:
    client, _, _ = app_with_doc
    resp = client.post("/api/docs/missing/segment", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_segments.py -v`

Expected: failures (router stub has no routes).

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`**

```python
"""Segmenter routes: run YOLO + CRUD on boxes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    DocStatus,
    SegmentCompleteLine,
    SegmentPageLine,
    SegmentStartLine,
    SegmentsFile,
)
from local_pdf.storage.sidecar import (
    doc_dir,
    read_meta,
    read_segments,
    write_meta,
    write_segments,
    write_yolo,
)
from local_pdf.workers.yolo import run_yolo

router = APIRouter()

# Test hook: assign a fake predict_fn here from tests.
_YOLO_PREDICT_FN = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bump_meta(data_root, slug: str, status: DocStatus) -> None:
    meta = read_meta(data_root, slug)
    if meta is None:
        return
    meta = meta.model_copy(update={"status": status, "last_touched_utc": _now_iso()})
    write_meta(data_root, slug, meta)


@router.post("/api/docs/{slug}/segment")
async def run_segment(slug: str, request: Request) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    _bump_meta(cfg.data_root, slug, DocStatus.segmenting)

    def stream():
        boxes = run_yolo(pdf, predict_fn=_YOLO_PREDICT_FN)
        pages = sorted({b.page for b in boxes})
        yield json.dumps(SegmentStartLine(total_pages=len(pages)).model_dump(mode="json")) + "\n"
        for p in pages:
            count = sum(1 for b in boxes if b.page == p)
            yield json.dumps(SegmentPageLine(page=p, boxes_found=count).model_dump(mode="json")) + "\n"
        write_yolo(cfg.data_root, slug, {"boxes": [b.model_dump(mode="json") for b in boxes]})
        write_segments(cfg.data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
        meta = read_meta(cfg.data_root, slug)
        if meta is not None:
            write_meta(cfg.data_root, slug, meta.model_copy(update={"box_count": len(boxes), "last_touched_utc": _now_iso()}))
        yield json.dumps(SegmentCompleteLine(boxes_total=len(boxes)).model_dump(mode="json")) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/api/docs/{slug}/segments")
async def get_segments(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"no segments yet for {slug}")
    return seg.model_dump(mode="json")
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_segments.py -v`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py features/pipelines/local-pdf/tests/test_routers_segments.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): POST /segment NDJSON streaming + GET /segments endpoint"
```

---

## Task 12: Box CRUD — PUT /update, POST /merge, POST /split, DELETE, POST /create

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`
- Modify: `features/pipelines/local-pdf/tests/test_routers_segments.py` (append)

- [ ] **Step 1: Append failing tests** to `features/pipelines/local-pdf/tests/test_routers_segments.py`

```python
def _ensure_segmented(client, slug):
    with client.stream("POST", f"/api/docs/{slug}/segment", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())


def test_put_box_updates_kind_and_persists(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p1-b0",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "list_item"},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b0")
    assert target["kind"] == "list_item"


def test_put_box_updates_bbox(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p1-b0",
        headers={"X-Auth-Token": "tok"},
        json={"bbox": [11, 22, 99, 199]},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b0")
    assert target["bbox"] == [11.0, 22.0, 99.0, 199.0]


def test_put_unknown_box_returns_404(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.put(
        f"/api/docs/{slug}/segments/p9-b9",
        headers={"X-Auth-Token": "tok"},
        json={"kind": "heading"},
    )
    assert resp.status_code == 404


def test_delete_box_assigns_discard_kind(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.delete(f"/api/docs/{slug}/segments/p1-b1", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    target = next(b for b in body["boxes"] if b["box_id"] == "p1-b1")
    assert target["kind"] == "discard"


def test_merge_boxes_creates_one_with_union_bbox(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/merge",
        headers={"X-Auth-Token": "tok"},
        json={"box_ids": ["p1-b0", "p1-b1"]},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    page1 = [b for b in body["boxes"] if b["page"] == 1]
    assert len(page1) == 1
    merged = page1[0]
    # Union of (10,20,100,50) and (10,60,100,200) is (10,20,100,200).
    assert merged["bbox"] == [10.0, 20.0, 100.0, 200.0]


def test_merge_rejects_cross_page(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments/merge",
        headers={"X-Auth-Token": "tok"},
        json={"box_ids": ["p1-b0", "p2-b0"]},
    )
    assert resp.status_code == 400


def test_split_box_at_y(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    # p1-b1 has bbox (10, 60, 100, 200). Split at y=130.
    resp = client.post(
        f"/api/docs/{slug}/segments/split",
        headers={"X-Auth-Token": "tok"},
        json={"box_id": "p1-b1", "split_y": 130},
    )
    assert resp.status_code == 200
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    page1 = [b for b in body["boxes"] if b["page"] == 1]
    # Original p1-b1 disappears, replaced by 2 new boxes.
    assert "p1-b1" not in {b["box_id"] for b in page1}
    new = [b for b in page1 if b["box_id"] != "p1-b0"]
    assert len(new) == 2
    ys = sorted([(b["bbox"][1], b["bbox"][3]) for b in new])
    assert ys == [(60.0, 130.0), (130.0, 200.0)]


def test_create_box(app_with_doc) -> None:
    client, _, slug = app_with_doc
    _ensure_segmented(client, slug)
    resp = client.post(
        f"/api/docs/{slug}/segments",
        headers={"X-Auth-Token": "tok"},
        json={"page": 1, "bbox": [200, 300, 400, 500], "kind": "heading"},
    )
    assert resp.status_code == 201
    body = client.get(f"/api/docs/{slug}/segments", headers={"X-Auth-Token": "tok"}).json()
    new_boxes = [b for b in body["boxes"] if b["bbox"] == [200.0, 300.0, 400.0, 500.0]]
    assert len(new_boxes) == 1
    assert new_boxes[0]["kind"] == "heading"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_segments.py -v -k "put_box or delete_box or merge or split or create_box"`

Expected: failures (no CRUD routes yet).

- [ ] **Step 3: Append CRUD routes to `features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py`**

```python
import secrets

from fastapi import status

from local_pdf.api.schemas import (
    BoxKind,
    CreateBoxRequest,
    MergeBoxesRequest,
    SegmentBox,
    SplitBoxRequest,
    UpdateBoxRequest,
)


def _replace_segments(data_root, slug: str, boxes: list[SegmentBox]) -> None:
    write_segments(data_root, slug, SegmentsFile(slug=slug, boxes=boxes))
    meta = read_meta(data_root, slug)
    if meta is not None:
        write_meta(data_root, slug, meta.model_copy(update={"box_count": len([b for b in boxes if b.kind != BoxKind.discard]), "last_touched_utc": _now_iso()}))


def _load_boxes_or_404(data_root, slug: str) -> list[SegmentBox]:
    seg = read_segments(data_root, slug)
    if seg is None:
        raise HTTPException(status_code=404, detail=f"no segments for {slug}")
    return list(seg.boxes)


@router.put("/api/docs/{slug}/segments/{box_id}")
async def update_box(slug: str, box_id: str, body: UpdateBoxRequest, request: Request) -> dict:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            updates = {}
            if body.kind is not None:
                updates["kind"] = body.kind
            if body.bbox is not None:
                updates["bbox"] = body.bbox
            if body.reading_order is not None:
                updates["reading_order"] = body.reading_order
            boxes[i] = b.model_copy(update=updates)
            _replace_segments(cfg.data_root, slug, boxes)
            return boxes[i].model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")


@router.delete("/api/docs/{slug}/segments/{box_id}")
async def delete_box(slug: str, box_id: str, request: Request) -> dict:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == box_id:
            boxes[i] = b.model_copy(update={"kind": BoxKind.discard})
            _replace_segments(cfg.data_root, slug, boxes)
            return boxes[i].model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"box not found: {box_id}")


@router.post("/api/docs/{slug}/segments/merge")
async def merge_boxes(slug: str, body: MergeBoxesRequest, request: Request) -> dict:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    by_id = {b.box_id: b for b in boxes}
    targets = []
    for bid in body.box_ids:
        if bid not in by_id:
            raise HTTPException(status_code=404, detail=f"box not found: {bid}")
        targets.append(by_id[bid])
    pages = {t.page for t in targets}
    if len(pages) != 1:
        raise HTTPException(status_code=400, detail="merge requires same page")
    page = pages.pop()
    x0 = min(t.bbox[0] for t in targets)
    y0 = min(t.bbox[1] for t in targets)
    x1 = max(t.bbox[2] for t in targets)
    y1 = max(t.bbox[3] for t in targets)
    merged = SegmentBox(
        box_id=f"p{page}-m{secrets.token_hex(3)}",
        page=page,
        bbox=(x0, y0, x1, y1),
        kind=targets[0].kind,
        confidence=min(t.confidence for t in targets),
        reading_order=min(t.reading_order for t in targets),
    )
    keep = [b for b in boxes if b.box_id not in body.box_ids]
    keep.append(merged)
    keep.sort(key=lambda b: (b.page, b.reading_order))
    _replace_segments(cfg.data_root, slug, keep)
    return merged.model_dump(mode="json")


@router.post("/api/docs/{slug}/segments/split")
async def split_box(slug: str, body: SplitBoxRequest, request: Request) -> dict:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    for i, b in enumerate(boxes):
        if b.box_id == body.box_id:
            x0, y0, x1, y1 = b.bbox
            if not (y0 < body.split_y < y1):
                raise HTTPException(status_code=400, detail="split_y must lie strictly inside the bbox")
            top = b.model_copy(update={"box_id": f"p{b.page}-s{secrets.token_hex(3)}", "bbox": (x0, y0, x1, body.split_y)})
            bot = b.model_copy(update={"box_id": f"p{b.page}-s{secrets.token_hex(3)}", "bbox": (x0, body.split_y, x1, y1)})
            new_boxes = boxes[:i] + [top, bot] + boxes[i+1:]
            _replace_segments(cfg.data_root, slug, new_boxes)
            return {"top": top.model_dump(mode="json"), "bottom": bot.model_dump(mode="json")}
    raise HTTPException(status_code=404, detail=f"box not found: {body.box_id}")


@router.post("/api/docs/{slug}/segments", status_code=status.HTTP_201_CREATED)
async def create_box(slug: str, body: CreateBoxRequest, request: Request) -> dict:
    cfg = request.app.state.config
    boxes = _load_boxes_or_404(cfg.data_root, slug)
    new = SegmentBox(
        box_id=f"p{body.page}-u{secrets.token_hex(3)}",
        page=body.page,
        bbox=body.bbox,
        kind=body.kind,
        confidence=1.0,
        reading_order=max((b.reading_order for b in boxes if b.page == body.page), default=-1) + 1,
    )
    boxes.append(new)
    _replace_segments(cfg.data_root, slug, boxes)
    return new.model_dump(mode="json")
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_segments.py -v`

Expected: 13 passed (5 from Task 11 + 8 new).

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/segments.py features/pipelines/local-pdf/tests/test_routers_segments.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): box CRUD (PUT update, DELETE, POST merge/split/create)"
```

---

## Task 13: POST /extract (NDJSON streaming) + POST /extract/region

**Files:**
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`
- Create: `features/pipelines/local-pdf/tests/test_routers_extract.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_routers_extract.py
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def app_with_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    from local_pdf.workers.yolo import YOLOPagePrediction, YOLOPredictedBox
    import local_pdf.api.routers.segments as seg_mod
    import local_pdf.api.routers.extract as ext_mod
    from local_pdf.workers.mineru import MinerUResult

    seg_mod._YOLO_PREDICT_FN = lambda _p: [
        YOLOPagePrediction(
            page=1,
            width=600,
            height=800,
            boxes=[
                YOLOPredictedBox(class_name="title", bbox=(10, 20, 100, 50), confidence=0.95),
                YOLOPredictedBox(class_name="plain text", bbox=(10, 60, 100, 200), confidence=0.88),
            ],
        )
    ]

    def fake_extract(_pdf, box):
        tag = "h1" if box.kind.value == "heading" else "p"
        return MinerUResult(box_id=box.box_id, html=f"<{tag} data-source-box=\"{box.box_id}\">{box.box_id}</{tag}>")

    ext_mod._MINERU_EXTRACT_FN = fake_extract

    from fastapi.testclient import TestClient

    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    files = {"file": ("Doc.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")}
    client.post("/api/docs", headers={"X-Auth-Token": "tok"}, files=files)
    with client.stream("POST", "/api/docs/doc/segment", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    yield client, root, "doc"

    seg_mod._YOLO_PREDICT_FN = None
    ext_mod._MINERU_EXTRACT_FN = None


def test_extract_streams_one_element_per_box(app_with_segments) -> None:
    client, _, slug = app_with_segments
    with client.stream("POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}) as resp:
        assert resp.status_code == 200
        lines = [json.loads(l) for l in resp.iter_lines() if l]
    types = [l["type"] for l in lines]
    assert types[0] == "start"
    assert types[-1] == "complete"
    elements = [l for l in lines if l["type"] == "element"]
    assert len(elements) == 2
    assert elements[0]["box_id"] == "p1-b0"


def test_extract_persists_html_and_mineru_out(app_with_segments) -> None:
    client, root, slug = app_with_segments
    with client.stream("POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    assert (root / slug / "html.html").exists()
    assert (root / slug / "mineru-out.json").exists()
    html = (root / slug / "html.html").read_text(encoding="utf-8")
    assert 'data-source-box="p1-b0"' in html
    assert 'data-source-box="p1-b1"' in html


def test_extract_region_runs_one_box_only(app_with_segments) -> None:
    client, root, slug = app_with_segments
    # First do a full extract so html exists.
    with client.stream("POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    resp = client.post(
        f"/api/docs/{slug}/extract/region",
        headers={"X-Auth-Token": "tok"},
        json={"box_id": "p1-b0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["box_id"] == "p1-b0"
    assert body["html"].startswith("<h1")


def test_extract_unknown_slug_404(app_with_segments) -> None:
    client, _, _ = app_with_segments
    resp = client.post("/api/docs/missing/extract", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_extract.py -v`

Expected: failures.

- [ ] **Step 3: Implement `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`**

```python
"""Extraction routes: full-doc + region MinerU runs, html GET/PUT, export."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from local_pdf.api.schemas import (
    BoxKind,
    DocStatus,
    ExtractCompleteLine,
    ExtractElementLine,
    ExtractRegionRequest,
    ExtractStartLine,
    HtmlPayload,
)
from local_pdf.storage.sidecar import (
    doc_dir,
    read_html,
    read_meta,
    read_segments,
    write_html,
    write_meta,
    write_mineru,
)
from local_pdf.workers.mineru import run_mineru, run_mineru_region

router = APIRouter()

# Test hook for MinerU.
_MINERU_EXTRACT_FN = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wrap_html(elements: list[dict]) -> str:
    body = "\n".join(e["html_snippet"] for e in elements)
    return f"<!DOCTYPE html>\n<html><body>\n{body}\n</body></html>\n"


@router.post("/api/docs/{slug}/extract")
async def run_extract(slug: str, request: Request) -> StreamingResponse:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"status": DocStatus.extracting, "last_touched_utc": _now_iso()}))

    targets = [b for b in seg.boxes if b.kind != BoxKind.discard]

    def stream():
        yield json.dumps(ExtractStartLine(total_boxes=len(targets)).model_dump(mode="json")) + "\n"
        elements: list[dict] = []
        for r in run_mineru(pdf, targets, extract_fn=_MINERU_EXTRACT_FN):
            line = ExtractElementLine(box_id=r.box_id, html_snippet=r.html)
            elements.append(line.model_dump(mode="json"))
            yield json.dumps(line.model_dump(mode="json")) + "\n"
        write_mineru(cfg.data_root, slug, {"elements": elements})
        write_html(cfg.data_root, slug, _wrap_html(elements))
        yield json.dumps(ExtractCompleteLine(boxes_extracted=len(elements)).model_dump(mode="json")) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/api/docs/{slug}/extract/region")
async def run_extract_region(slug: str, body: ExtractRegionRequest, request: Request) -> dict:
    cfg = request.app.state.config
    pdf = doc_dir(cfg.data_root, slug) / "source.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail=f"pdf not found: {slug}")
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    target = next((b for b in seg.boxes if b.box_id == body.box_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"box not found: {body.box_id}")
    result = run_mineru_region(pdf, target, extract_fn=_MINERU_EXTRACT_FN)
    return {"box_id": result.box_id, "html": result.html}


@router.get("/api/docs/{slug}/html")
async def get_html(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=404, detail=f"no html for {slug}")
    return {"html": html}


@router.put("/api/docs/{slug}/html")
async def put_html(slug: str, body: HtmlPayload, request: Request) -> dict:
    cfg = request.app.state.config
    if not (doc_dir(cfg.data_root, slug)).exists():
        raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
    write_html(cfg.data_root, slug, body.html)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"last_touched_utc": _now_iso()}))
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_routers_extract.py -v`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py features/pipelines/local-pdf/tests/test_routers_extract.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/api): /extract NDJSON streaming + /extract/region + /html GET/PUT"
```

---

## Task 14: SourceElement converter + POST /export

**Files:**
- Create: `features/pipelines/local-pdf/src/local_pdf/convert/__init__.py`
- Create: `features/pipelines/local-pdf/src/local_pdf/convert/source_elements.py`
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py` (append /export route)
- Create: `features/pipelines/local-pdf/tests/test_convert_source_elements.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_convert_source_elements.py
from __future__ import annotations


def test_convert_html_and_segments_to_source_elements_payload() -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.convert.source_elements import build_source_elements_payload

    segments = SegmentsFile(
        slug="rep",
        boxes=[
            SegmentBox(box_id="p1-b0", page=1, bbox=(10, 20, 100, 50), kind=BoxKind.heading, confidence=0.95),
            SegmentBox(box_id="p1-b1", page=1, bbox=(10, 60, 100, 200), kind=BoxKind.paragraph, confidence=0.88),
            SegmentBox(box_id="p1-b2", page=1, bbox=(10, 210, 100, 250), kind=BoxKind.discard, confidence=0.4),
        ],
    )
    html = (
        "<!DOCTYPE html><html><body>"
        "<h1 data-source-box=\"p1-b0\">3 Prüfverfahren</h1>"
        "<p data-source-box=\"p1-b1\">Die Prüfung des Tragkorbs.</p>"
        "<p data-source-box=\"p1-b2\">discarded</p>"
        "</body></html>"
    )
    payload = build_source_elements_payload(slug="rep", segments=segments, html=html)
    assert payload["doc_slug"] == "rep"
    assert payload["source_pipeline"] == "local-pdf"
    elements = payload["elements"]
    assert len(elements) == 2
    assert elements[0] == {
        "kind": "heading",
        "page": 1,
        "bbox": [10.0, 20.0, 100.0, 50.0],
        "text": "3 Prüfverfahren",
        "level": 1,
        "box_id": "p1-b0",
    }
    assert elements[1]["kind"] == "paragraph"
    assert elements[1]["text"] == "Die Prüfung des Tragkorbs."


def test_converter_strips_html_tags_inside_text() -> None:
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.convert.source_elements import build_source_elements_payload

    segments = SegmentsFile(
        slug="x",
        boxes=[SegmentBox(box_id="p1-b0", page=1, bbox=(0, 0, 1, 1), kind=BoxKind.paragraph, confidence=0.9)],
    )
    html = "<p data-source-box=\"p1-b0\">Hello <em>world</em>!</p>"
    payload = build_source_elements_payload(slug="x", segments=segments, html=html)
    assert payload["elements"][0]["text"] == "Hello world!"


def test_export_writes_sourceelements_json(tmp_path) -> None:
    """End-to-end: build payload + write_source_elements stores correct JSON."""
    import json
    from local_pdf.api.schemas import BoxKind, SegmentBox, SegmentsFile
    from local_pdf.convert.source_elements import build_source_elements_payload
    from local_pdf.storage.sidecar import doc_dir, write_source_elements

    slug = "rep"
    doc_dir(tmp_path, slug).mkdir()
    segments = SegmentsFile(
        slug=slug,
        boxes=[SegmentBox(box_id="p1-b0", page=1, bbox=(0, 0, 1, 1), kind=BoxKind.paragraph, confidence=0.9)],
    )
    html = '<p data-source-box="p1-b0">Hi</p>'
    payload = build_source_elements_payload(slug=slug, segments=segments, html=html)
    write_source_elements(tmp_path, slug, payload)
    loaded = json.loads((doc_dir(tmp_path, slug) / "sourceelements.json").read_text(encoding="utf-8"))
    assert loaded == payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_convert_source_elements.py -v`

Expected: ImportError.

- [ ] **Step 3: Implement converter**

```python
# features/pipelines/local-pdf/src/local_pdf/convert/__init__.py
"""Converters from MinerU/HTML output to canonical SourceElement JSON."""
```

```python
# features/pipelines/local-pdf/src/local_pdf/convert/source_elements.py
"""Build canonical SourceElement payload from user-edited segments + html.

Output shape matches features/pipelines/microsoft/ pipeline (PR #12 schema)
plus a `source_pipeline: "local-pdf"` discriminator field. Boxes whose
kind == "discard" are skipped.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

from local_pdf.api.schemas import BoxKind, SegmentsFile


class _TextExtractor(HTMLParser):
    """Capture raw text between balanced tags, indexed by data-source-box."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str | None] = []
        self._buf: list[str] = []
        self._capture: str | None = None
        self.results: dict[str, str] = {}
        self.tags: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        bid = attrs_d.get("data-source-box")
        if bid and self._capture is None:
            self._capture = bid
            self._buf = []
            self._stack.append(bid)
            self.tags[bid] = tag
        else:
            self._stack.append(None)

    def handle_endtag(self, tag):
        if not self._stack:
            return
        top = self._stack.pop()
        if top is not None and top == self._capture:
            self.results[self._capture] = "".join(self._buf).strip()
            self._capture = None
            self._buf = []

    def handle_data(self, data):
        if self._capture is not None:
            self._buf.append(data)


def _heading_level(tag: str) -> int:
    m = re.match(r"h([1-6])$", tag.lower())
    return int(m.group(1)) if m else 1


def build_source_elements_payload(*, slug: str, segments: SegmentsFile, html: str) -> dict:
    parser = _TextExtractor()
    parser.feed(html)
    elements: list[dict] = []
    for box in segments.boxes:
        if box.kind == BoxKind.discard:
            continue
        text = parser.results.get(box.box_id, "")
        tag = parser.tags.get(box.box_id, "p")
        entry: dict = {
            "kind": box.kind.value,
            "page": box.page,
            "bbox": list(box.bbox),
            "text": text,
            "box_id": box.box_id,
        }
        if box.kind == BoxKind.heading:
            entry["level"] = _heading_level(tag)
        elements.append(entry)
    return {
        "doc_slug": slug,
        "source_pipeline": "local-pdf",
        "elements": elements,
    }
```

Then append the `/export` route to `features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py`:

```python
from local_pdf.convert.source_elements import build_source_elements_payload
from local_pdf.storage.sidecar import write_source_elements


@router.post("/api/docs/{slug}/export")
async def run_export(slug: str, request: Request) -> dict:
    cfg = request.app.state.config
    seg = read_segments(cfg.data_root, slug)
    if seg is None:
        raise HTTPException(status_code=400, detail="run /segment first")
    html = read_html(cfg.data_root, slug)
    if html is None:
        raise HTTPException(status_code=400, detail="run /extract first")
    payload = build_source_elements_payload(slug=slug, segments=seg, html=html)
    write_source_elements(cfg.data_root, slug, payload)
    meta = read_meta(cfg.data_root, slug)
    if meta is not None:
        write_meta(cfg.data_root, slug, meta.model_copy(update={"status": DocStatus.done, "last_touched_utc": _now_iso()}))
    return payload
```

- [ ] **Step 4: Add an export-route test** to `features/pipelines/local-pdf/tests/test_routers_extract.py`:

```python
def test_export_writes_sourceelements_and_marks_done(app_with_segments) -> None:
    client, root, slug = app_with_segments
    with client.stream("POST", f"/api/docs/{slug}/extract", headers={"X-Auth-Token": "tok"}) as resp:
        list(resp.iter_lines())
    resp = client.post(f"/api/docs/{slug}/export", headers={"X-Auth-Token": "tok"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_pipeline"] == "local-pdf"
    assert (root / slug / "sourceelements.json").exists()
    meta = client.get(f"/api/docs/{slug}", headers={"X-Auth-Token": "tok"}).json()
    assert meta["status"] == "done"
```

- [ ] **Step 5: Run all backend tests**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/ -v`

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add features/pipelines/local-pdf/src/local_pdf/convert/__init__.py features/pipelines/local-pdf/src/local_pdf/convert/source_elements.py features/pipelines/local-pdf/src/local_pdf/api/routers/extract.py features/pipelines/local-pdf/tests/test_convert_source_elements.py features/pipelines/local-pdf/tests/test_routers_extract.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(local-pdf/convert): build SourceElement payload + POST /export route"
```

---

## Task 15: CLI subcommand `query-eval segment serve`

**Files:**
- Modify: `features/evaluators/chunk_match/src/query_index_eval/cli.py`
- Create: `features/pipelines/local-pdf/tests/test_cli_serve.py`

- [ ] **Step 1: Write the failing test**

```python
# features/pipelines/local-pdf/tests/test_cli_serve.py
from __future__ import annotations

import subprocess
import sys


def test_segment_serve_help_shows_options() -> None:
    """`query-eval segment serve --help` prints --port / --host."""
    proc = subprocess.run(
        [sys.executable, "-m", "query_index_eval.cli", "segment", "serve", "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--port" in proc.stdout
    assert "--host" in proc.stdout


def test_segment_serve_loads_app_factory(monkeypatch) -> None:
    """The handler imports local_pdf.api.create_app and would call uvicorn.run."""
    captured: dict = {}

    def fake_run(app, host, port, log_level):
        captured["host"] = host
        captured["port"] = port
        captured["app"] = app

    import uvicorn

    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")

    from query_index_eval.cli import cmd_segment_serve

    cmd_segment_serve(host="127.0.0.1", port=8001, log_level="info")
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8001
    assert captured["app"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd features/pipelines/local-pdf && python -m pytest tests/test_cli_serve.py -v`

Expected: ImportError on `query_index_eval.cli.cmd_segment_serve` (or AttributeError).

- [ ] **Step 3: Modify `features/evaluators/chunk_match/src/query_index_eval/cli.py`**

Add at the bottom (after existing subparsers):

```python
def cmd_segment_serve(*, host: str, port: int, log_level: str) -> int:
    """Start the local-pdf FastAPI app via uvicorn."""
    import uvicorn

    from local_pdf.api import create_app

    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level=log_level)
    return 0


def _add_segment_subparser(subparsers) -> None:
    seg = subparsers.add_parser("segment", help="local-pdf pipeline commands")
    seg_sub = seg.add_subparsers(dest="segment_cmd", required=True)
    serve = seg_sub.add_parser("serve", help="run the local-pdf HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8001)
    serve.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])
    serve.set_defaults(handler=lambda args: cmd_segment_serve(host=args.host, port=args.port, log_level=args.log_level))
```

Then in the existing `build_parser()` function, after the existing `subparsers = parser.add_subparsers(...)` block, add:

```python
    _add_segment_subparser(subparsers)
```

- [ ] **Step 4: Run tests**

Run:
```bash
source .venv/bin/activate
cd features/pipelines/local-pdf && python -m pytest tests/test_cli_serve.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add features/evaluators/chunk_match/src/query_index_eval/cli.py features/pipelines/local-pdf/tests/test_cli_serve.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat(cli): add `query-eval segment serve` subcommand to launch local-pdf API"
```

---

## Task 16: Frontend domain types + API client wrapper

**Files:**
- Create: `frontend/src/local-pdf/types/domain.ts`
- Create: `frontend/src/local-pdf/api/client.ts`
- Create: `frontend/src/local-pdf/api/docs.ts`
- Create: `frontend/tests/local-pdf/api/docs.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/local-pdf/api/docs.test.ts
import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { listDocs, uploadDoc, getDoc, getSegments, updateBox } from "../../../src/local-pdf/api/docs";

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs", () =>
    HttpResponse.json([
      { slug: "rep", filename: "Rep.pdf", pages: 4, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 },
    ]),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep", () =>
    HttpResponse.json({ slug: "rep", filename: "Rep.pdf", pages: 4, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 }),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({ slug: "rep", boxes: [{ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.9, reading_order: 0 }] }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/segments/p1-b0", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "paragraph", confidence: 0.9, reading_order: 0 }),
  ),
  http.post("http://127.0.0.1:8001/api/docs", () =>
    HttpResponse.json({ slug: "new", filename: "New.pdf", pages: 1, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 }, { status: 201 }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("local-pdf docs api", () => {
  it("listDocs returns inbox", async () => {
    const out = await listDocs("tok");
    expect(out).toHaveLength(1);
    expect(out[0].slug).toBe("rep");
  });

  it("getDoc returns metadata", async () => {
    const m = await getDoc("rep", "tok");
    expect(m.pages).toBe(4);
  });

  it("getSegments returns boxes", async () => {
    const s = await getSegments("rep", "tok");
    expect(s.boxes[0].kind).toBe("heading");
  });

  it("updateBox sends PUT", async () => {
    const out = await updateBox("rep", "p1-b0", { kind: "paragraph" }, "tok");
    expect(out.kind).toBe("paragraph");
  });

  it("uploadDoc sends multipart", async () => {
    const blob = new Blob([new Uint8Array([0x25, 0x50, 0x44, 0x46])], { type: "application/pdf" });
    const file = new File([blob], "New.pdf", { type: "application/pdf" });
    const out = await uploadDoc(file, "tok");
    expect(out.slug).toBe("new");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/api/docs.test.ts`

Expected: import errors.

- [ ] **Step 3: Implement**

```ts
// frontend/src/local-pdf/types/domain.ts
export type BoxKind =
  | "heading"
  | "paragraph"
  | "table"
  | "figure"
  | "caption"
  | "formula"
  | "list_item"
  | "discard";

export type DocStatus = "raw" | "segmenting" | "extracting" | "done" | "needs_ocr";

export interface SegmentBox {
  box_id: string;
  page: number;
  bbox: [number, number, number, number];
  kind: BoxKind;
  confidence: number;
  reading_order: number;
}

export interface SegmentsFile {
  slug: string;
  boxes: SegmentBox[];
}

export interface DocMeta {
  slug: string;
  filename: string;
  pages: number;
  status: DocStatus;
  last_touched_utc: string;
  box_count: number;
}

export type ExtractLine =
  | { type: "start"; total_boxes: number }
  | { type: "element"; box_id: string; html_snippet: string }
  | { type: "complete"; boxes_extracted: number }
  | { type: "error"; box_id?: string; reason: string };

export type SegmentLine =
  | { type: "start"; total_pages: number }
  | { type: "page"; page: number; boxes_found: number }
  | { type: "complete"; boxes_total: number }
  | { type: "error"; reason: string };

export interface SourceElementsPayload {
  doc_slug: string;
  source_pipeline: "local-pdf";
  elements: Array<{
    kind: Exclude<BoxKind, "discard">;
    page: number;
    bbox: [number, number, number, number];
    text: string;
    box_id: string;
    level?: number;
  }>;
}
```

```ts
// frontend/src/local-pdf/api/client.ts
const BASE = (import.meta.env.VITE_LOCAL_PDF_API_BASE ?? "http://127.0.0.1:8001") as string;

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function authHeaders(token: string): HeadersInit {
  return { "X-Auth-Token": token };
}

export async function apiFetch(path: string, token: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers ?? {});
  headers.set("X-Auth-Token", token);
  const resp = await fetch(`${BASE}${path}`, { ...init, headers });
  if (resp.status === 401) {
    window.dispatchEvent(new CustomEvent("local-pdf:401"));
    throw new ApiError(401, "unauthorized");
  }
  if (!resp.ok) {
    const text = await resp.text();
    throw new ApiError(resp.status, text || resp.statusText);
  }
  return resp;
}

export function apiBase(): string {
  return BASE;
}
```

```ts
// frontend/src/local-pdf/api/docs.ts
import { apiFetch } from "./client";
import type { DocMeta, SegmentBox, SegmentsFile, SourceElementsPayload, BoxKind } from "../types/domain";

export async function listDocs(token: string): Promise<DocMeta[]> {
  const r = await apiFetch("/api/docs", token);
  return r.json();
}

export async function uploadDoc(file: File, token: string): Promise<DocMeta> {
  const fd = new FormData();
  fd.set("file", file);
  const r = await apiFetch("/api/docs", token, { method: "POST", body: fd });
  return r.json();
}

export async function getDoc(slug: string, token: string): Promise<DocMeta> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}`, token);
  return r.json();
}

export async function getSegments(slug: string, token: string): Promise<SegmentsFile> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/segments`, token);
  return r.json();
}

export async function updateBox(
  slug: string,
  boxId: string,
  patch: { kind?: BoxKind; bbox?: [number, number, number, number]; reading_order?: number },
  token: string,
): Promise<SegmentBox> {
  const r = await apiFetch(
    `/api/docs/${encodeURIComponent(slug)}/segments/${encodeURIComponent(boxId)}`,
    token,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) },
  );
  return r.json();
}

export async function deleteBox(slug: string, boxId: string, token: string): Promise<SegmentBox> {
  const r = await apiFetch(
    `/api/docs/${encodeURIComponent(slug)}/segments/${encodeURIComponent(boxId)}`,
    token,
    { method: "DELETE" },
  );
  return r.json();
}

export async function mergeBoxes(slug: string, boxIds: string[], token: string): Promise<SegmentBox> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/segments/merge`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box_ids: boxIds }),
  });
  return r.json();
}

export async function splitBox(slug: string, boxId: string, splitY: number, token: string): Promise<{ top: SegmentBox; bottom: SegmentBox }> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/segments/split`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box_id: boxId, split_y: splitY }),
  });
  return r.json();
}

export async function createBox(slug: string, page: number, bbox: [number, number, number, number], kind: BoxKind, token: string): Promise<SegmentBox> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/segments`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page, bbox, kind }),
  });
  return r.json();
}

export async function getHtml(slug: string, token: string): Promise<string> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/html`, token);
  const j = (await r.json()) as { html: string };
  return j.html;
}

export async function putHtml(slug: string, html: string, token: string): Promise<void> {
  await apiFetch(`/api/docs/${encodeURIComponent(slug)}/html`, token, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });
}

export async function exportSourceElements(slug: string, token: string): Promise<SourceElementsPayload> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/export`, token, { method: "POST" });
  return r.json();
}

export async function extractRegion(slug: string, boxId: string, token: string): Promise<{ box_id: string; html: string }> {
  const r = await apiFetch(`/api/docs/${encodeURIComponent(slug)}/extract/region`, token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ box_id: boxId }),
  });
  return r.json();
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/api/docs.test.ts`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/types/domain.ts frontend/src/local-pdf/api/client.ts frontend/src/local-pdf/api/docs.ts frontend/tests/local-pdf/api/docs.test.ts
git commit -m "feat(frontend/local-pdf): TS domain types + REST client wrapper for /api/docs"
```

---

## Task 17: NDJSON streaming reader

**Files:**
- Create: `frontend/src/local-pdf/api/ndjson.ts`
- Create: `frontend/tests/local-pdf/api/ndjson.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/local-pdf/api/ndjson.test.ts
import { describe, expect, it } from "vitest";

import { readNdjsonLines } from "../../../src/local-pdf/api/ndjson";

function bodyFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const ch of chunks) c.enqueue(enc.encode(ch));
      c.close();
    },
  });
}

describe("readNdjsonLines", () => {
  it("splits on newline and parses JSON per line", async () => {
    const stream = bodyFrom(['{"type":"start","total_boxes":2}\n', '{"type":"element","box_id":"b1","html_snippet":"<p/>"}\n', '{"type":"complete","boxes_extracted":1}\n']);
    const out: any[] = [];
    for await (const obj of readNdjsonLines<any>(stream)) out.push(obj);
    expect(out).toHaveLength(3);
    expect(out[0].type).toBe("start");
    expect(out[2].boxes_extracted).toBe(1);
  });

  it("buffers partial lines across chunks", async () => {
    const stream = bodyFrom(['{"type":"start",', '"total_boxes":7}\n']);
    const out: any[] = [];
    for await (const obj of readNdjsonLines<any>(stream)) out.push(obj);
    expect(out).toEqual([{ type: "start", total_boxes: 7 }]);
  });

  it("ignores trailing empty line", async () => {
    const stream = bodyFrom(['{"type":"start","total_boxes":1}\n\n']);
    const out: any[] = [];
    for await (const obj of readNdjsonLines<any>(stream)) out.push(obj);
    expect(out).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/api/ndjson.test.ts`

Expected: import error.

- [ ] **Step 3: Implement**

```ts
// frontend/src/local-pdf/api/ndjson.ts
export async function* readNdjsonLines<T>(body: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl = buf.indexOf("\n");
    while (nl !== -1) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) yield JSON.parse(line) as T;
      nl = buf.indexOf("\n");
    }
  }
  buf += dec.decode();
  const tail = buf.trim();
  if (tail) yield JSON.parse(tail) as T;
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/api/ndjson.test.ts`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/api/ndjson.ts frontend/tests/local-pdf/api/ndjson.test.ts
git commit -m "feat(frontend/local-pdf): NDJSON streaming reader (TextDecoder + line buffer)"
```

---

## Task 18: PDF.js page-rendering hook

**Files:**
- Modify: `frontend/package.json` (add `pdfjs-dist`)
- Create: `frontend/src/local-pdf/hooks/usePdfPage.ts`
- Create: `frontend/tests/local-pdf/hooks/usePdfPage.test.ts`

- [ ] **Step 1: Add the dep + write the failing test**

In `frontend/package.json` `dependencies`, add `"pdfjs-dist": "^4.6.0"`. Then run `cd frontend && npm install`.

```ts
// frontend/tests/local-pdf/hooks/usePdfPage.test.ts
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePdfPage } from "../../../src/local-pdf/hooks/usePdfPage";

vi.mock("pdfjs-dist/build/pdf.mjs", () => ({
  getDocument: vi.fn(() => ({
    promise: Promise.resolve({
      numPages: 3,
      getPage: vi.fn(async (n: number) => ({
        getViewport: ({ scale }: { scale: number }) => ({ width: 100 * scale, height: 200 * scale }),
        render: vi.fn(() => ({ promise: Promise.resolve() })),
      })),
    }),
  })),
  GlobalWorkerOptions: { workerSrc: "" },
}));

describe("usePdfPage", () => {
  it("loads document and exposes numPages + viewport", async () => {
    const { result } = renderHook(() => usePdfPage("/api/docs/x/source.pdf", "tok", 1, 1.5));
    await waitFor(() => expect(result.current.numPages).toBe(3));
    expect(result.current.viewport).toEqual({ width: 150, height: 300 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/hooks/usePdfPage.test.ts`

Expected: import error on `usePdfPage`.

- [ ] **Step 3: Implement**

```ts
// frontend/src/local-pdf/hooks/usePdfPage.ts
import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist/build/pdf.mjs";

GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.mjs", import.meta.url).toString();

export interface PageState {
  numPages: number;
  viewport: { width: number; height: number };
  canvasRef: React.RefObject<HTMLCanvasElement>;
  loading: boolean;
  error: string | null;
}

export function usePdfPage(url: string, token: string, page: number, scale: number): PageState {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [numPages, setNumPages] = useState(0);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const task = getDocument({ url, httpHeaders: { "X-Auth-Token": token }, withCredentials: false });
        const pdf = await task.promise;
        if (cancelled) return;
        setNumPages(pdf.numPages);
        const p = await pdf.getPage(page);
        const vp = p.getViewport({ scale });
        setViewport({ width: vp.width, height: vp.height });
        if (canvasRef.current) {
          const canvas = canvasRef.current;
          canvas.width = vp.width;
          canvas.height = vp.height;
          await p.render({ canvasContext: canvas.getContext("2d")!, viewport: vp }).promise;
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url, token, page, scale]);

  return { numPages, viewport, canvasRef, loading, error };
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/hooks/usePdfPage.test.ts`

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/local-pdf/hooks/usePdfPage.ts frontend/tests/local-pdf/hooks/usePdfPage.test.ts
git commit -m "feat(frontend/local-pdf): usePdfPage hook (PDF.js rendering with X-Auth-Token)"
```

---

## Task 19: Box hotkey hook (h/p/t/f/c/q/l/x for kind, m/n/// for actions)

**Files:**
- Create: `frontend/src/local-pdf/hooks/useBoxHotkeys.ts`
- Create: `frontend/tests/local-pdf/hooks/useBoxHotkeys.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/tests/local-pdf/hooks/useBoxHotkeys.test.ts
import { renderHook } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useBoxHotkeys } from "../../../src/local-pdf/hooks/useBoxHotkeys";

describe("useBoxHotkeys", () => {
  it("invokes setKind for h/p/t/f/c/q/l/x", () => {
    const setKind = vi.fn();
    const merge = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, merge, split, newBox, del }));
    for (const [key, kind] of [
      ["h", "heading"],
      ["p", "paragraph"],
      ["t", "table"],
      ["f", "figure"],
      ["c", "caption"],
      ["q", "formula"],
      ["l", "list_item"],
      ["x", "discard"],
    ] as const) {
      fireEvent.keyDown(window, { key });
      expect(setKind).toHaveBeenLastCalledWith(kind);
    }
  });

  it("m/n//// + Backspace map to merge / newBox / split / delete", () => {
    const setKind = vi.fn();
    const merge = vi.fn();
    const split = vi.fn();
    const newBox = vi.fn();
    const del = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, merge, split, newBox, del }));
    fireEvent.keyDown(window, { key: "m" });
    expect(merge).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "n" });
    expect(newBox).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "/" });
    expect(split).toHaveBeenCalled();
    fireEvent.keyDown(window, { key: "Backspace" });
    expect(del).toHaveBeenCalled();
  });

  it("ignores keystrokes when enabled is false", () => {
    const setKind = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: false, setKind, merge: vi.fn(), split: vi.fn(), newBox: vi.fn(), del: vi.fn() }));
    fireEvent.keyDown(window, { key: "h" });
    expect(setKind).not.toHaveBeenCalled();
  });

  it("ignores keystrokes when target is an input", () => {
    const setKind = vi.fn();
    renderHook(() => useBoxHotkeys({ enabled: true, setKind, merge: vi.fn(), split: vi.fn(), newBox: vi.fn(), del: vi.fn() }));
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();
    fireEvent.keyDown(input, { key: "h" });
    expect(setKind).not.toHaveBeenCalled();
    input.remove();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/hooks/useBoxHotkeys.test.ts`

Expected: import error.

- [ ] **Step 3: Implement**

```ts
// frontend/src/local-pdf/hooks/useBoxHotkeys.ts
import { useEffect } from "react";
import type { BoxKind } from "../types/domain";

export interface BoxHotkeyHandlers {
  enabled: boolean;
  setKind: (k: BoxKind) => void;
  merge: () => void;
  split: () => void;
  newBox: () => void;
  del: () => void;
}

const KIND_KEYS: Record<string, BoxKind> = {
  h: "heading",
  p: "paragraph",
  t: "table",
  f: "figure",
  c: "caption",
  q: "formula",
  l: "list_item",
  x: "discard",
};

export function useBoxHotkeys(h: BoxHotkeyHandlers): void {
  useEffect(() => {
    if (!h.enabled) return;
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const k = KIND_KEYS[e.key];
      if (k) {
        e.preventDefault();
        h.setKind(k);
        return;
      }
      if (e.key === "m") {
        e.preventDefault();
        h.merge();
      } else if (e.key === "n") {
        e.preventDefault();
        h.newBox();
      } else if (e.key === "/") {
        e.preventDefault();
        h.split();
      } else if (e.key === "Backspace" || e.key === "Delete") {
        e.preventDefault();
        h.del();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [h.enabled, h.setKind, h.merge, h.split, h.newBox, h.del]);
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/hooks/useBoxHotkeys.test.ts`

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/hooks/useBoxHotkeys.ts frontend/tests/local-pdf/hooks/useBoxHotkeys.test.ts
git commit -m "feat(frontend/local-pdf): useBoxHotkeys (h/p/t/f/c/q/l/x kinds + m/n/// + Backspace)"
```

---

## Task 20: BoxOverlay component (drag/resize handles)

**Files:**
- Create: `frontend/src/local-pdf/styles/box-colors.css`
- Create: `frontend/src/local-pdf/components/BoxOverlay.tsx`
- Create: `frontend/tests/local-pdf/components/BoxOverlay.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/local-pdf/components/BoxOverlay.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BoxOverlay } from "../../../src/local-pdf/components/BoxOverlay";

const box = {
  box_id: "p1-b0",
  page: 1,
  bbox: [10, 20, 100, 200] as [number, number, number, number],
  kind: "paragraph" as const,
  confidence: 0.92,
  reading_order: 0,
};

describe("BoxOverlay", () => {
  it("renders kind label + confidence", () => {
    render(<BoxOverlay box={box} selected={false} onSelect={() => {}} onChange={() => {}} scale={1} />);
    expect(screen.getByText(/paragraph/)).toBeInTheDocument();
    expect(screen.getByText(/0\.92/)).toBeInTheDocument();
  });

  it("calls onSelect when clicked", () => {
    const onSelect = vi.fn();
    render(<BoxOverlay box={box} selected={false} onSelect={onSelect} onChange={() => {}} scale={1} />);
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    expect(onSelect).toHaveBeenCalledWith("p1-b0", false);
  });

  it("emits shift-click via onSelect with multi=true", () => {
    const onSelect = vi.fn();
    render(<BoxOverlay box={box} selected={false} onSelect={onSelect} onChange={() => {}} scale={1} />);
    fireEvent.click(screen.getByTestId("box-p1-b0"), { shiftKey: true });
    expect(onSelect).toHaveBeenCalledWith("p1-b0", true);
  });

  it("renders 4 corner handles when selected", () => {
    render(<BoxOverlay box={box} selected={true} onSelect={() => {}} onChange={() => {}} scale={1} />);
    expect(screen.getAllByTestId(/handle-/)).toHaveLength(4);
  });

  it("flashes yellow when confidence < 0.7", () => {
    const lowBox = { ...box, confidence: 0.5 };
    render(<BoxOverlay box={lowBox} selected={false} onSelect={() => {}} onChange={() => {}} scale={1} />);
    const el = screen.getByTestId("box-p1-b0");
    expect(el.className).toMatch(/low-confidence/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/components/BoxOverlay.test.tsx`

Expected: import error.

- [ ] **Step 3: Implement**

```css
/* frontend/src/local-pdf/styles/box-colors.css */
.box-heading    { --box-color: #2563eb; }
.box-paragraph  { --box-color: #16a34a; }
.box-table      { --box-color: #ea580c; }
.box-figure     { --box-color: #0d9488; }
.box-caption    { --box-color: #9333ea; }
.box-formula    { --box-color: #db2777; }
.box-list_item  { --box-color: #4f46e5; }
.box-discard    { --box-color: #6b7280; }

.box-outline {
  position: absolute;
  border: 2px solid var(--box-color);
  background: color-mix(in srgb, var(--box-color) 8%, transparent);
  cursor: pointer;
}

.box-outline.selected { outline: 2px dashed #ef4444; outline-offset: 2px; }
.box-outline.low-confidence { animation: box-pulse 1.4s ease-in-out infinite; }

@keyframes box-pulse {
  50% { background: color-mix(in srgb, #facc15 25%, transparent); }
}

.box-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  background: #ef4444;
  border: 1px solid white;
}

.box-label {
  position: absolute;
  top: -18px;
  left: 0;
  padding: 1px 4px;
  font-size: 10px;
  background: var(--box-color);
  color: white;
  border-radius: 2px;
  pointer-events: none;
}
```

```tsx
// frontend/src/local-pdf/components/BoxOverlay.tsx
import { useEffect, useRef, useState } from "react";
import type { SegmentBox } from "../types/domain";
import "../styles/box-colors.css";

interface Props {
  box: SegmentBox;
  selected: boolean;
  onSelect: (boxId: string, multi: boolean) => void;
  onChange: (boxId: string, bbox: [number, number, number, number]) => void;
  scale: number;
}

export function BoxOverlay({ box, selected, onSelect, onChange, scale }: Props): JSX.Element {
  const [x0, y0, x1, y1] = box.bbox;
  const [drag, setDrag] = useState<{ corner: string; sx: number; sy: number; orig: [number, number, number, number] } | null>(null);

  const style: React.CSSProperties = {
    left: x0 * scale,
    top: y0 * scale,
    width: (x1 - x0) * scale,
    height: (y1 - y0) * scale,
  };
  const cls = ["box-outline", `box-${box.kind}`];
  if (selected) cls.push("selected");
  if (box.confidence < 0.7) cls.push("low-confidence");

  useEffect(() => {
    if (!drag) return;
    function onMove(e: MouseEvent) {
      const dx = (e.clientX - drag!.sx) / scale;
      const dy = (e.clientY - drag!.sy) / scale;
      const [ox0, oy0, ox1, oy1] = drag!.orig;
      let n: [number, number, number, number] = [ox0, oy0, ox1, oy1];
      if (drag!.corner === "tl") n = [ox0 + dx, oy0 + dy, ox1, oy1];
      else if (drag!.corner === "tr") n = [ox0, oy0 + dy, ox1 + dx, oy1];
      else if (drag!.corner === "bl") n = [ox0 + dx, oy0, ox1, oy1 + dy];
      else if (drag!.corner === "br") n = [ox0, oy0, ox1 + dx, oy1 + dy];
      else n = [ox0 + dx, oy0 + dy, ox1 + dx, oy1 + dy];
      onChange(box.box_id, n);
    }
    function onUp() {
      setDrag(null);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [drag, scale, onChange, box.box_id]);

  function startDrag(corner: string, e: React.MouseEvent) {
    e.stopPropagation();
    setDrag({ corner, sx: e.clientX, sy: e.clientY, orig: box.bbox });
  }

  return (
    <div
      data-testid={`box-${box.box_id}`}
      className={cls.join(" ")}
      style={style}
      onClick={(e) => onSelect(box.box_id, e.shiftKey)}
      onMouseDown={(e) => selected && startDrag("center", e)}
    >
      <span className="box-label">
        {box.kind} · {box.confidence.toFixed(2)}
      </span>
      {selected && (
        <>
          <div data-testid="handle-tl" className="box-handle" style={{ left: -5, top: -5 }} onMouseDown={(e) => startDrag("tl", e)} />
          <div data-testid="handle-tr" className="box-handle" style={{ right: -5, top: -5 }} onMouseDown={(e) => startDrag("tr", e)} />
          <div data-testid="handle-bl" className="box-handle" style={{ left: -5, bottom: -5 }} onMouseDown={(e) => startDrag("bl", e)} />
          <div data-testid="handle-br" className="box-handle" style={{ right: -5, bottom: -5 }} onMouseDown={(e) => startDrag("br", e)} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/components/BoxOverlay.test.tsx`

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/styles/box-colors.css frontend/src/local-pdf/components/BoxOverlay.tsx frontend/tests/local-pdf/components/BoxOverlay.test.tsx
git commit -m "feat(frontend/local-pdf): BoxOverlay with drag/resize handles + kind colors + low-confidence flash"
```

---

## Task 21: PropertiesSidebar + StatusBadge components

**Files:**
- Create: `frontend/src/local-pdf/components/PropertiesSidebar.tsx`
- Create: `frontend/src/local-pdf/components/StatusBadge.tsx`

- [ ] **Step 1: Implement** (no test — these are thin presentational shells covered by route tests)

```tsx
// frontend/src/local-pdf/components/StatusBadge.tsx
import type { DocStatus } from "../types/domain";

const COLORS: Record<DocStatus, string> = {
  raw: "bg-gray-200 text-gray-800",
  segmenting: "bg-amber-200 text-amber-900",
  extracting: "bg-blue-200 text-blue-900",
  done: "bg-green-200 text-green-900",
  needs_ocr: "bg-red-200 text-red-900",
};

export function StatusBadge({ status }: { status: DocStatus }): JSX.Element {
  return (
    <span className={`inline-block px-2 py-0.5 text-xs rounded ${COLORS[status]}`}>
      {status}
    </span>
  );
}
```

```tsx
// frontend/src/local-pdf/components/PropertiesSidebar.tsx
import type { BoxKind, SegmentBox } from "../types/domain";

const KINDS: BoxKind[] = ["heading", "paragraph", "table", "figure", "caption", "formula", "list_item", "discard"];

interface Props {
  selected: SegmentBox | null;
  pageBoxCount: number;
  onChangeKind: (k: BoxKind) => void;
  onMerge: () => void;
  onDelete: () => void;
  onRunExtract: () => void;
  extractEnabled: boolean;
}

export function PropertiesSidebar({ selected, pageBoxCount, onChangeKind, onMerge, onDelete, onRunExtract, extractEnabled }: Props): JSX.Element {
  return (
    <aside className="w-1/4 border-l p-4 flex flex-col gap-3 text-sm">
      <h2 className="font-semibold">Properties</h2>
      {selected ? (
        <>
          <div>
            <label className="block text-xs text-gray-500">Kind</label>
            <select className="w-full border rounded p-1" value={selected.kind} onChange={(e) => onChangeKind(e.target.value as BoxKind)}>
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
          <div>
            <span className="text-xs text-gray-500">bbox</span>
            <pre className="text-xs">{JSON.stringify(selected.bbox)}</pre>
          </div>
          <div>
            <span className="text-xs text-gray-500">confidence</span>{" "}
            <span>{selected.confidence.toFixed(3)}</span>
          </div>
          <div className="flex gap-2">
            <button className="px-2 py-1 border rounded" onClick={onMerge}>Merge (m)</button>
            <button className="px-2 py-1 border rounded" onClick={onDelete}>Delete</button>
          </div>
        </>
      ) : (
        <p className="text-gray-400">Select a box.</p>
      )}
      <div className="border-t pt-3 mt-3">
        <p className="text-xs text-gray-500">{pageBoxCount} boxes on page</p>
      </div>
      <button
        className="mt-auto bg-blue-600 text-white py-2 rounded disabled:bg-gray-300"
        disabled={!extractEnabled}
        onClick={onRunExtract}
      >
        Run extraction →
      </button>
    </aside>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/local-pdf/components/PropertiesSidebar.tsx frontend/src/local-pdf/components/StatusBadge.tsx
git commit -m "feat(frontend/local-pdf): StatusBadge + PropertiesSidebar (kind picker, merge/delete, run-extract)"
```

---

## Task 22: Tiptap HTML editor with raw-mode CodeMirror toggle

**Files:**
- Modify: `frontend/package.json` — add `@tiptap/react`, `@tiptap/starter-kit`, `@codemirror/view`, `@codemirror/state`, `@codemirror/lang-html`, `codemirror`
- Create: `frontend/src/local-pdf/components/HtmlEditor.tsx`
- Create: `frontend/tests/local-pdf/components/HtmlEditor.test.tsx`

- [ ] **Step 1: Add deps + write the failing test**

Add to `frontend/package.json` `dependencies`:
```json
"@tiptap/react": "^2.6.0",
"@tiptap/starter-kit": "^2.6.0",
"@codemirror/view": "^6.30.0",
"@codemirror/state": "^6.4.0",
"@codemirror/lang-html": "^6.4.0",
"codemirror": "^6.0.0",
```
Then `cd frontend && npm install`.

```tsx
// frontend/tests/local-pdf/components/HtmlEditor.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HtmlEditor } from "../../../src/local-pdf/components/HtmlEditor";

describe("HtmlEditor", () => {
  it("renders WYSIWYG by default and toggles to raw HTML mode", () => {
    const onChange = vi.fn();
    render(<HtmlEditor html="<p>hi</p>" onChange={onChange} onClickElement={() => {}} />);
    expect(screen.getByRole("button", { name: /raw html/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /raw html/i }));
    expect(screen.getByRole("button", { name: /wysiwyg/i })).toBeInTheDocument();
  });

  it("calls onClickElement when a data-source-box element is clicked in WYSIWYG", () => {
    const onClick = vi.fn();
    render(<HtmlEditor html='<p data-source-box="b-1">x</p>' onChange={() => {}} onClickElement={onClick} />);
    const p = document.querySelector('[data-source-box="b-1"]')!;
    fireEvent.click(p);
    expect(onClick).toHaveBeenCalledWith("b-1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/components/HtmlEditor.test.tsx`

Expected: import error.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/local-pdf/components/HtmlEditor.tsx
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef, useState } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { html as htmlLang } from "@codemirror/lang-html";

interface Props {
  html: string;
  onChange: (html: string) => void;
  onClickElement: (boxId: string) => void;
}

export function HtmlEditor({ html, onChange, onClickElement }: Props): JSX.Element {
  const [mode, setMode] = useState<"wysiwyg" | "raw">("wysiwyg");
  const cmHostRef = useRef<HTMLDivElement>(null);
  const cmRef = useRef<EditorView | null>(null);

  const editor = useEditor({
    extensions: [StarterKit],
    content: html,
    editorProps: {
      handleClick(view, _pos, evt) {
        const t = evt.target as HTMLElement;
        const el = t.closest("[data-source-box]") as HTMLElement | null;
        if (el) {
          onClickElement(el.getAttribute("data-source-box")!);
          return true;
        }
        return false;
      },
    },
    onUpdate({ editor }) {
      onChange(editor.getHTML());
    },
  });

  useEffect(() => {
    if (mode !== "raw" || !cmHostRef.current) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: html,
        extensions: [keymap.of(defaultKeymap), htmlLang(), EditorView.updateListener.of((v) => {
          if (v.docChanged) onChange(v.state.doc.toString());
        })],
      }),
      parent: cmHostRef.current,
    });
    cmRef.current = view;
    return () => {
      view.destroy();
      cmRef.current = null;
    };
  }, [mode, html, onChange]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center p-2 border-b">
        <span className="text-sm font-semibold">HTML editor</span>
        <button
          type="button"
          className="text-xs underline"
          onClick={() => setMode((m) => (m === "wysiwyg" ? "raw" : "wysiwyg"))}
        >
          view: {mode === "wysiwyg" ? "WYSIWYG ▾" : "Raw HTML ▾"}
        </button>
      </div>
      <div className="flex-1 overflow-auto p-2">
        {mode === "wysiwyg" ? <EditorContent editor={editor} /> : <div ref={cmHostRef} />}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/components/HtmlEditor.test.tsx`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/local-pdf/components/HtmlEditor.tsx frontend/tests/local-pdf/components/HtmlEditor.test.tsx
git commit -m "feat(frontend/local-pdf): HtmlEditor (Tiptap WYSIWYG + CodeMirror raw toggle, click-to-link emit)"
```

---

## Task 23: useDocs / useSegments / useExtract data hooks (TanStack Query)

**Files:**
- Create: `frontend/src/local-pdf/hooks/useDocs.ts`
- Create: `frontend/src/local-pdf/hooks/useSegments.ts`
- Create: `frontend/src/local-pdf/hooks/useExtract.ts`

- [ ] **Step 1: Implement (covered by route tests in later tasks; skipping unit-test here is intentional — hooks are 4-line wrappers)**

```ts
// frontend/src/local-pdf/hooks/useDocs.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listDocs, uploadDoc } from "../api/docs";

export function useDocs(token: string) {
  return useQuery({ queryKey: ["docs"], queryFn: () => listDocs(token), staleTime: 5_000 });
}

export function useUploadDoc(token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadDoc(file, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}
```

```ts
// frontend/src/local-pdf/hooks/useSegments.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createBox, deleteBox, getSegments, mergeBoxes, splitBox, updateBox } from "../api/docs";
import type { BoxKind } from "../types/domain";

export function useSegments(slug: string, token: string) {
  return useQuery({ queryKey: ["segments", slug], queryFn: () => getSegments(slug, token) });
}

export function useUpdateBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boxId, patch }: { boxId: string; patch: { kind?: BoxKind; bbox?: [number, number, number, number] } }) =>
      updateBox(slug, boxId, patch, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useMergeBoxes(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => mergeBoxes(slug, ids, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useSplitBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ boxId, splitY }: { boxId: string; splitY: number }) => splitBox(slug, boxId, splitY, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useCreateBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ page, bbox, kind }: { page: number; bbox: [number, number, number, number]; kind: BoxKind }) =>
      createBox(slug, page, bbox, kind, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}

export function useDeleteBox(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (boxId: string) => deleteBox(slug, boxId, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["segments", slug] }),
  });
}
```

```ts
// frontend/src/local-pdf/hooks/useExtract.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { exportSourceElements, extractRegion, getHtml, putHtml } from "../api/docs";
import { apiBase } from "../api/client";
import { readNdjsonLines } from "../api/ndjson";
import type { ExtractLine, SegmentLine } from "../types/domain";

export function useHtml(slug: string, token: string) {
  return useQuery({ queryKey: ["html", slug], queryFn: () => getHtml(slug, token) });
}

export function usePutHtml(slug: string, token: string) {
  return useMutation({ mutationFn: (html: string) => putHtml(slug, html, token) });
}

export function useExportSourceElements(slug: string, token: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => exportSourceElements(slug, token),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["docs"] }),
  });
}

export function useExtractRegion(slug: string, token: string) {
  return useMutation({ mutationFn: (boxId: string) => extractRegion(slug, boxId, token) });
}

export async function* streamSegment(slug: string, token: string): AsyncGenerator<SegmentLine> {
  const r = await fetch(`${apiBase()}/api/docs/${encodeURIComponent(slug)}/segment`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<SegmentLine>(r.body);
}

export async function* streamExtract(slug: string, token: string): AsyncGenerator<ExtractLine> {
  const r = await fetch(`${apiBase()}/api/docs/${encodeURIComponent(slug)}/extract`, {
    method: "POST",
    headers: { "X-Auth-Token": token },
  });
  if (!r.body) throw new Error("no body");
  yield* readNdjsonLines<ExtractLine>(r.body);
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc -b --noEmit`

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/local-pdf/hooks/useDocs.ts frontend/src/local-pdf/hooks/useSegments.ts frontend/src/local-pdf/hooks/useExtract.ts
git commit -m "feat(frontend/local-pdf): TanStack Query hooks (docs/segments/extract) + NDJSON streamers"
```

---

## Task 24: Inbox route (`/local-pdf/inbox`)

**Files:**
- Create: `frontend/src/local-pdf/routes/inbox.tsx`
- Create: `frontend/tests/local-pdf/routes/inbox.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/local-pdf/routes/inbox.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { InboxRoute } from "../../../src/local-pdf/routes/inbox";

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs", () =>
    HttpResponse.json([
      { slug: "rep", filename: "Rep.pdf", pages: 4, status: "raw", last_touched_utc: "2026-04-30T10:00:00Z", box_count: 0 },
      { slug: "spec", filename: "Spec.pdf", pages: 12, status: "done", last_touched_utc: "2026-04-30T11:00:00Z", box_count: 35 },
    ]),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrapped() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/inbox"]}>
        <Routes>
          <Route path="/local-pdf/inbox" element={<InboxRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("InboxRoute", () => {
  it("lists docs with status badge", async () => {
    render(wrapped());
    await waitFor(() => expect(screen.getByText("Rep.pdf")).toBeInTheDocument());
    expect(screen.getByText("Spec.pdf")).toBeInTheDocument();
    expect(screen.getByText("raw")).toBeInTheDocument();
    expect(screen.getByText("done")).toBeInTheDocument();
  });

  it("filters by search input", async () => {
    render(wrapped());
    await waitFor(() => expect(screen.getByText("Rep.pdf")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "spec" } });
    expect(screen.queryByText("Rep.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("Spec.pdf")).toBeInTheDocument();
  });

  it("renders Add PDF button", async () => {
    render(wrapped());
    expect(screen.getByRole("button", { name: /add pdf/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/routes/inbox.test.tsx`

Expected: import error.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/local-pdf/routes/inbox.tsx
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";

import { useDocs, useUploadDoc } from "../hooks/useDocs";
import { StatusBadge } from "../components/StatusBadge";

interface Props {
  token: string;
}

export function InboxRoute({ token }: Props): JSX.Element {
  const docs = useDocs(token);
  const upload = useUploadDoc(token);
  const fileRef = useRef<HTMLInputElement>(null);
  const [filter, setFilter] = useState("");

  function handlePickFile() {
    fileRef.current?.click();
  }

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    upload.mutate(f, {
      onSuccess: (m) => toast.success(`uploaded ${m.slug}`),
      onError: (err) => toast.error(`upload failed: ${(err as Error).message}`),
    });
    e.target.value = "";
  }

  const rows = (docs.data ?? []).filter((d) => d.filename.toLowerCase().includes(filter.toLowerCase()) || d.slug.includes(filter.toLowerCase()));

  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <h1 className="text-xl font-semibold">Local-PDF Inbox</h1>
        <input
          type="text"
          className="ml-auto border rounded px-2 py-1 text-sm"
          placeholder="search…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <button className="bg-blue-600 text-white px-3 py-1 rounded text-sm" onClick={handlePickFile}>
          + Add PDF
        </button>
        <input ref={fileRef} type="file" accept="application/pdf" hidden onChange={handleFile} />
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b">
            <th className="p-2">filename</th>
            <th className="p-2">pages</th>
            <th className="p-2">status</th>
            <th className="p-2">boxes</th>
            <th className="p-2">last touched</th>
            <th className="p-2">action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.slug} className="border-b">
              <td className="p-2">{d.filename}</td>
              <td className="p-2">{d.pages}</td>
              <td className="p-2">
                <StatusBadge status={d.status} />
              </td>
              <td className="p-2">{d.box_count}</td>
              <td className="p-2 text-xs text-gray-500">{d.last_touched_utc}</td>
              <td className="p-2">
                <Link className="text-blue-600 underline" to={`/local-pdf/doc/${d.slug}/segment`}>
                  {d.status === "raw" ? "start" : d.status === "done" ? "view" : "resume"}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-400 mt-4">Drop PDFs into <code>data/raw-pdfs/</code> or use Add PDF.</p>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/routes/inbox.test.tsx`

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/routes/inbox.tsx frontend/tests/local-pdf/routes/inbox.test.tsx
git commit -m "feat(frontend/local-pdf): /inbox route (table + status badge + search + Add PDF)"
```

---

## Task 25: Segmenter route (`/local-pdf/doc/:slug/segment`)

**Files:**
- Create: `frontend/src/local-pdf/components/PdfPage.tsx`
- Create: `frontend/src/local-pdf/routes/segment.tsx`
- Create: `frontend/tests/local-pdf/routes/segment.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/local-pdf/routes/segment.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { SegmentRoute } from "../../../src/local-pdf/routes/segment";

vi.mock("../../../src/local-pdf/hooks/usePdfPage", () => ({
  usePdfPage: () => ({
    numPages: 2,
    viewport: { width: 600, height: 800 },
    canvasRef: { current: null },
    loading: false,
    error: null,
  }),
}));

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({
      slug: "rep",
      boxes: [
        { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
        { box_id: "p1-b1", page: 1, bbox: [10, 60, 100, 200], kind: "paragraph", confidence: 0.6, reading_order: 1 },
      ],
    }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/segments/p1-b0", () =>
    HttpResponse.json({ box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "list_item", confidence: 0.95, reading_order: 0 }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/doc/rep/segment"]}>
        <Routes>
          <Route path="/local-pdf/doc/:slug/segment" element={<SegmentRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SegmentRoute", () => {
  it("renders the page-1 boxes after segments load", async () => {
    render(wrap());
    await waitFor(() => expect(screen.getByTestId("box-p1-b0")).toBeInTheDocument());
    expect(screen.getByTestId("box-p1-b1")).toBeInTheDocument();
  });

  it("changes selected box kind via hotkey 'l'", async () => {
    render(wrap());
    await waitFor(() => screen.getByTestId("box-p1-b0"));
    fireEvent.click(screen.getByTestId("box-p1-b0"));
    fireEvent.keyDown(window, { key: "l" });
    await waitFor(() => {
      // optimistic: properties sidebar shows updated kind once invalidate refetches
      const select = screen.getByDisplayValue("list_item") as HTMLSelectElement;
      expect(select).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/routes/segment.test.tsx`

Expected: import error.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/local-pdf/components/PdfPage.tsx
import { usePdfPage } from "../hooks/usePdfPage";
import { apiBase } from "../api/client";

interface Props {
  slug: string;
  token: string;
  page: number;
  scale: number;
  children?: React.ReactNode;
}

export function PdfPage({ slug, token, page, scale, children }: Props): JSX.Element {
  const url = `${apiBase()}/api/docs/${encodeURIComponent(slug)}/source.pdf`;
  const { canvasRef, viewport, loading, error } = usePdfPage(url, token, page, scale);
  if (error) return <div className="text-red-600 p-4">PDF error: {error}</div>;
  return (
    <div className="relative" style={{ width: viewport.width, height: viewport.height }}>
      <canvas ref={canvasRef} />
      {loading && <div className="absolute inset-0 bg-white/60 grid place-items-center">loading…</div>}
      {children}
    </div>
  );
}
```

```tsx
// frontend/src/local-pdf/routes/segment.tsx
import { useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import toast from "react-hot-toast";

import { BoxOverlay } from "../components/BoxOverlay";
import { PdfPage } from "../components/PdfPage";
import { PropertiesSidebar } from "../components/PropertiesSidebar";
import { useBoxHotkeys } from "../hooks/useBoxHotkeys";
import {
  useCreateBox,
  useDeleteBox,
  useMergeBoxes,
  useSegments,
  useSplitBox,
  useUpdateBox,
} from "../hooks/useSegments";
import { streamSegment } from "../hooks/useExtract";
import type { BoxKind } from "../types/domain";

interface Props {
  token: string;
}

export function SegmentRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const scale = 1.5;
  const segments = useSegments(slug ?? "", token);
  const update = useUpdateBox(slug ?? "", token);
  const merge = useMergeBoxes(slug ?? "", token);
  const split = useSplitBox(slug ?? "", token);
  const newBox = useCreateBox(slug ?? "", token);
  const del = useDeleteBox(slug ?? "", token);
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);

  const boxesOnPage = useMemo(
    () => (segments.data?.boxes ?? []).filter((b) => b.page === page),
    [segments.data, page],
  );
  const focused = useMemo(
    () => (segments.data?.boxes ?? []).find((b) => b.box_id === selected[0]) ?? null,
    [segments.data, selected],
  );

  function handleSelect(boxId: string, multi: boolean) {
    setSelected((prev) => (multi ? (prev.includes(boxId) ? prev.filter((p) => p !== boxId) : [...prev, boxId]) : [boxId]));
  }

  async function runSegment() {
    setRunning(true);
    try {
      for await (const line of streamSegment(slug!, token)) {
        if (line.type === "complete") toast.success(`segmented ${line.boxes_total} boxes`);
        if (line.type === "error") toast.error(line.reason);
      }
      await segments.refetch();
    } finally {
      setRunning(false);
    }
  }

  useBoxHotkeys({
    enabled: !!focused,
    setKind: (k: BoxKind) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } }),
    merge: () => selected.length >= 2 && merge.mutate(selected),
    split: () => focused && split.mutate({ boxId: focused.box_id, splitY: (focused.bbox[1] + focused.bbox[3]) / 2 }),
    newBox: () => newBox.mutate({ page, bbox: [50, 50, 200, 200], kind: "paragraph" }),
    del: () => focused && del.mutate(focused.box_id),
  });

  if (!segments.data) {
    return (
      <div className="p-6">
        <p>No segmentation yet.</p>
        <button className="mt-4 bg-blue-600 text-white px-3 py-1 rounded" onClick={runSegment} disabled={running}>
          {running ? "Segmenting…" : "Run segmentation"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <main className="flex-1 overflow-auto p-4">
        <div className="flex gap-2 mb-2">
          {Array.from({ length: 10 }, (_, i) => i + 1).map((p) => (
            <button key={p} className={`px-2 py-1 text-xs ${p === page ? "bg-gray-200" : ""}`} onClick={() => setPage(p)}>
              p{p}
            </button>
          ))}
        </div>
        <PdfPage slug={slug!} token={token} page={page} scale={scale}>
          {boxesOnPage.map((b) => (
            <BoxOverlay
              key={b.box_id}
              box={b}
              selected={selected.includes(b.box_id)}
              onSelect={handleSelect}
              onChange={(boxId, bbox) => update.mutate({ boxId, patch: { bbox } })}
              scale={scale}
            />
          ))}
        </PdfPage>
      </main>
      <PropertiesSidebar
        selected={focused}
        pageBoxCount={boxesOnPage.length}
        onChangeKind={(k) => focused && update.mutate({ boxId: focused.box_id, patch: { kind: k } })}
        onMerge={() => selected.length >= 2 && merge.mutate(selected)}
        onDelete={() => focused && del.mutate(focused.box_id)}
        onRunExtract={() => navigate(`/local-pdf/doc/${slug}/extract`)}
        extractEnabled={(segments.data.boxes ?? []).some((b) => b.kind !== "discard")}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/routes/segment.test.tsx`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/components/PdfPage.tsx frontend/src/local-pdf/routes/segment.tsx frontend/tests/local-pdf/routes/segment.test.tsx
git commit -m "feat(frontend/local-pdf): /segment route (PDF + box overlays + sidebar + hotkeys + run-segment streaming)"
```

---

## Task 26: Extraction route (`/local-pdf/doc/:slug/extract`)

**Files:**
- Create: `frontend/src/local-pdf/routes/extract.tsx`
- Create: `frontend/tests/local-pdf/routes/extract.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/tests/local-pdf/routes/extract.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ExtractRoute } from "../../../src/local-pdf/routes/extract";

vi.mock("../../../src/local-pdf/hooks/usePdfPage", () => ({
  usePdfPage: () => ({ numPages: 1, viewport: { width: 600, height: 800 }, canvasRef: { current: null }, loading: false, error: null }),
}));

const server = setupServer(
  http.get("http://127.0.0.1:8001/api/docs/rep/segments", () =>
    HttpResponse.json({
      slug: "rep",
      boxes: [
        { box_id: "p1-b0", page: 1, bbox: [10, 20, 100, 50], kind: "heading", confidence: 0.95, reading_order: 0 },
      ],
    }),
  ),
  http.get("http://127.0.0.1:8001/api/docs/rep/html", () =>
    HttpResponse.json({ html: '<h1 data-source-box="p1-b0">Hi</h1>' }),
  ),
  http.put("http://127.0.0.1:8001/api/docs/rep/html", () => HttpResponse.json({ ok: true })),
  http.post("http://127.0.0.1:8001/api/docs/rep/export", () =>
    HttpResponse.json({ doc_slug: "rep", source_pipeline: "local-pdf", elements: [] }),
  ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/local-pdf/doc/rep/extract"]}>
        <Routes>
          <Route path="/local-pdf/doc/:slug/extract" element={<ExtractRoute token="tok" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ExtractRoute", () => {
  it("loads html and shows it in editor", async () => {
    render(wrap());
    await waitFor(() => expect(screen.getByText("Hi")).toBeInTheDocument());
  });

  it("Export button posts and toasts", async () => {
    render(wrap());
    await waitFor(() => screen.getByText("Hi"));
    fireEvent.click(screen.getByRole("button", { name: /export/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /export/i })).not.toBeDisabled(),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/local-pdf/routes/extract.test.tsx`

Expected: import error.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/local-pdf/routes/extract.tsx
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import toast from "react-hot-toast";

import { BoxOverlay } from "../components/BoxOverlay";
import { HtmlEditor } from "../components/HtmlEditor";
import { PdfPage } from "../components/PdfPage";
import { useSegments } from "../hooks/useSegments";
import { streamExtract, useExportSourceElements, useExtractRegion, useHtml, usePutHtml } from "../hooks/useExtract";

interface Props {
  token: string;
}

export function ExtractRoute({ token }: Props): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const segments = useSegments(slug ?? "", token);
  const html = useHtml(slug ?? "", token);
  const putHtml = usePutHtml(slug ?? "", token);
  const exportSrc = useExportSourceElements(slug ?? "", token);
  const extractRegion = useExtractRegion(slug ?? "", token);
  const [page, setPage] = useState(1);
  const [running, setRunning] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);
  const debounceRef = useRef<number | null>(null);

  function handleHtmlChange(next: string) {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      putHtml.mutate(next);
    }, 300);
  }

  useEffect(() => () => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
  }, []);

  async function runExtract() {
    setRunning(true);
    try {
      for await (const line of streamExtract(slug!, token)) {
        if (line.type === "complete") toast.success(`extracted ${line.boxes_extracted} boxes`);
        if (line.type === "error") toast.error(line.reason);
      }
      await html.refetch();
    } finally {
      setRunning(false);
    }
  }

  function handleExport() {
    exportSrc.mutate(undefined, {
      onSuccess: () => toast.success("Exported sourceelements.json"),
      onError: (err) => toast.error((err as Error).message),
    });
  }

  function handleClickElement(boxId: string) {
    setHighlight(boxId);
    const target = (segments.data?.boxes ?? []).find((b) => b.box_id === boxId);
    if (target) setPage(target.page);
  }

  function handleRegion(boxId: string) {
    extractRegion.mutate(boxId, {
      onSuccess: (r) => toast.success(`re-extracted ${r.box_id}`),
      onError: (err) => toast.error((err as Error).message),
    });
  }

  const boxesOnPage = (segments.data?.boxes ?? []).filter((b) => b.page === page);

  if (!html.data) {
    return (
      <div className="p-6">
        <button className="bg-blue-600 text-white px-3 py-1 rounded" onClick={runExtract} disabled={running}>
          {running ? "Extracting…" : "Run extraction"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      <section className="w-1/2 overflow-auto p-2 border-r">
        <PdfPage slug={slug!} token={token} page={page} scale={1.2}>
          {boxesOnPage.map((b) => (
            <BoxOverlay
              key={b.box_id}
              box={b}
              selected={highlight === b.box_id}
              onSelect={(id) => handleRegion(id)}
              onChange={() => {}}
              scale={1.2}
            />
          ))}
        </PdfPage>
      </section>
      <section className="w-1/2 flex flex-col">
        <div className="flex justify-end p-2 border-b gap-2">
          <button className="text-sm px-3 py-1 bg-blue-600 text-white rounded" disabled={exportSrc.isPending} onClick={handleExport}>
            Export →
          </button>
        </div>
        <HtmlEditor html={html.data} onChange={handleHtmlChange} onClickElement={handleClickElement} />
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx vitest run tests/local-pdf/routes/extract.test.tsx`

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/local-pdf/routes/extract.tsx frontend/tests/local-pdf/routes/extract.test.tsx
git commit -m "feat(frontend/local-pdf): /extract route (PDF + Tiptap + click-to-link + Export + region re-extract)"
```

---

## Task 27: Wire local-pdf routes into App + TopBar

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/TopBar.tsx`

- [ ] **Step 1: Modify `frontend/src/App.tsx`**

Locate the existing `<Routes>...</Routes>` block (added in A-Plus.2) and add three sibling routes under the auth-gated branch:

```tsx
import { ExtractRoute } from "./local-pdf/routes/extract";
import { InboxRoute } from "./local-pdf/routes/inbox";
import { SegmentRoute } from "./local-pdf/routes/segment";

// inside <Routes> (after existing routes):
<Route path="/local-pdf/inbox" element={<InboxRoute token={token} />} />
<Route path="/local-pdf/doc/:slug/segment" element={<SegmentRoute token={token} />} />
<Route path="/local-pdf/doc/:slug/extract" element={<ExtractRoute token={token} />} />
```

(`token` is the same auth context A-Plus.2 already provides.)

- [ ] **Step 2: Modify `frontend/src/components/TopBar.tsx`**

Add a nav item next to the existing "Goldens" link:

```tsx
<Link to="/local-pdf/inbox" className="px-3 py-1 text-sm hover:underline">
  Local PDF
</Link>
```

- [ ] **Step 3: Run the full frontend test suite**

Run: `cd frontend && npx vitest run`

Expected: all green (existing A-Plus.2 tests + new local-pdf tests).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/TopBar.tsx
git commit -m "feat(frontend): wire local-pdf routes into App + TopBar nav link"
```

---

## Task 28: Playwright happy-path E2E

**Files:**
- Create: `frontend/tests/local-pdf/e2e/local-pdf-happy-path.spec.ts`

- [ ] **Step 1: Write the test**

```ts
// frontend/tests/local-pdf/e2e/local-pdf-happy-path.spec.ts
import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const TOKEN = process.env.LOCAL_PDF_TEST_TOKEN ?? "tok-e2e";
const FRONTEND = process.env.LOCAL_PDF_FRONTEND ?? "http://127.0.0.1:5173";

test.describe("local-pdf happy path", () => {
  test("upload → segment → edit → extract → export", async ({ page }) => {
    await page.addInitScript((t) => sessionStorage.setItem("auth-token", t), TOKEN);
    await page.goto(`${FRONTEND}/#/local-pdf/inbox`);

    // Upload a small fixture PDF
    const pdf = resolve("frontend/tests/local-pdf/e2e/fixtures/small.pdf");
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(pdf);
    await expect(page.getByText("uploaded")).toBeVisible({ timeout: 10_000 });

    // Click into the doc
    await page.getByRole("link", { name: /^start$/i }).first().click();
    await expect(page.getByRole("button", { name: /run segmentation/i })).toBeVisible();
    await page.getByRole("button", { name: /run segmentation/i }).click();
    await expect(page.getByText(/segmented/i)).toBeVisible({ timeout: 30_000 });

    // Press 'h' to set selected box to heading
    await page.locator('[data-testid^="box-"]').first().click();
    await page.keyboard.press("h");

    // Run extraction
    await page.getByRole("button", { name: /run extraction/i }).click();
    await expect(page.getByText(/extracted/i)).toBeVisible({ timeout: 60_000 });

    // Export
    await page.getByRole("button", { name: /export/i }).click();
    await expect(page.getByText(/exported sourceelements/i)).toBeVisible({ timeout: 10_000 });
  });
});
```

Place a tiny PDF fixture at `frontend/tests/local-pdf/e2e/fixtures/small.pdf` (any 1-page PDF; can be generated with `printf '%%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF' > fixtures/small.pdf` or copied from an existing test asset).

- [ ] **Step 2: Run E2E (only if backend + frontend are running locally)**

```bash
# in one shell:
source .venv/bin/activate
GOLDENS_API_TOKEN=tok-e2e LOCAL_PDF_DATA_ROOT=/tmp/local-pdf-e2e query-eval segment serve --port 8001
# in another:
cd frontend && npm run dev
# in a third:
cd frontend && LOCAL_PDF_TEST_TOKEN=tok-e2e npx playwright test tests/local-pdf/e2e/local-pdf-happy-path.spec.ts
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/local-pdf/e2e/local-pdf-happy-path.spec.ts frontend/tests/local-pdf/e2e/fixtures/small.pdf
git commit -m "test(local-pdf/e2e): playwright happy-path (upload → segment → extract → export)"
```

---

## Task 29: Update root README + open PR

**Files:**
- Modify: `README.md` (add a section)

- [ ] **Step 1: Append a "Local PDF pipeline (Phase A.0)" section** to root `README.md` documenting:
  - the new `data/raw-pdfs/<slug>/` layout
  - the `query-eval segment serve` command
  - the `/local-pdf/inbox` UI entry point
  - that the output `sourceelements.json` is drop-in for the goldens system

- [ ] **Step 2: Run the full test matrix**

```bash
source .venv/bin/activate && python -m pytest features/pipelines/local-pdf/tests -v
cd frontend && npx vitest run
cd frontend && npx tsc -b --noEmit
```

Expected: all green; no TS errors.

- [ ] **Step 3: Commit + push + open PR**

```bash
git add README.md
git commit -m "docs(local-pdf): document Phase A.0 quickstart in root README"
git push -u origin a-0-local-pdf-pipeline
gh pr create --title "Phase A.0 — Local PDF pipeline (DocLayout-YOLO + MinerU 3 + visual review UI)" --body "$(cat <<'PR_EOF'
## Summary
- Backend: FastAPI service at `features/pipelines/local-pdf/` exposing 14 endpoints (upload/inbox/segment/extract/region/html/export) with NDJSON streaming for the long-running operations and fcntl-locked sidecar JSON in `data/raw-pdfs/<slug>/`.
- Workers: DocLayout-YOLO segmentation + MinerU 3 extraction wrappers with injectable `predict_fn` / `extract_fn` for fast tests.
- Converter: emits canonical `SourceElement` JSON (`source_pipeline: "local-pdf"`) drop-in compatible with the existing goldens system.
- Frontend: 3 new React routes — Inbox table, 2-pane Segmenter (PDF + box overlays + hotkeys h/p/t/f/c/q/l/x + m/n/// + Backspace), 2-pane Extraction view (PDF + Tiptap WYSIWYG with CodeMirror raw-mode toggle + click-to-link + per-region re-extract).
- CLI: new `query-eval segment serve` subcommand.

## Test plan
- [ ] Backend unit tests: `pytest features/pipelines/local-pdf/tests` green
- [ ] Frontend unit tests: `cd frontend && npx vitest run` green
- [ ] TS typecheck: `cd frontend && npx tsc -b --noEmit` clean
- [ ] Playwright happy-path with one small PDF
- [ ] Manual smoke: upload BAM_Tragkorb_2024.pdf, verify boxes, export, diff against existing microsoft pipeline output

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PR_EOF
)"
```

Expected: PR opens with all checks green.

---

## Methodology + Model Allocation

Use **superpowers:subagent-driven-development**. One subagent per task, atomic commit, no shared state. Suggested model per task:

| Task | Model | Rationale |
|------|-------|-----------|
| 1 | Haiku | Mechanical: pyproject + scaffold |
| 2 | Haiku | Schema enums + literal validators |
| 3 | Haiku | Settings class |
| 4 | Haiku | Verbatim copy from A-Plus.1 |
| 5 | Haiku | Pure-string functions |
| 6 | Sonnet | fcntl + atomic-rename semantics worth a careful pass |
| 7 | Haiku | App factory boilerplate |
| 8 | Sonnet | Class-mapping + injectable predict_fn require care |
| 9 | Sonnet | subprocess wiring + iterator semantics |
| 10 | Sonnet | upload, slug collision, FileResponse |
| 11 | Sonnet | NDJSON StreamingResponse + persistence ordering |
| 12 | Sonnet | bbox-union, split arithmetic, multi-route refactor |
| 13 | Sonnet | Streaming + html assembly + status transitions |
| 14 | Sonnet | HTMLParser-based text extractor |
| 15 | Haiku | argparse subparser |
| 16 | Sonnet | TS types + fetch wrapper + msw test plumbing |
| 17 | Haiku | TextDecoder line buffer |
| 18 | Sonnet | PDF.js worker setup + render lifecycle |
| 19 | Haiku | Pure event-listener hook |
| 20 | Sonnet | Drag/resize math + DOM events |
| 21 | Haiku | Two presentational components |
| 22 | Sonnet | Tiptap + CodeMirror integration is fiddly |
| 23 | Haiku | Thin TanStack Query wrappers |
| 24 | Sonnet | Route + table + upload integration |
| 25 | Sonnet | Page state, multi-select, hotkey wiring, streaming run |
| 26 | Sonnet | Two-pane sync, debounced PUT, export, region re-extract |
| 27 | Haiku | Two-line route registration |
| 28 | Sonnet | Playwright across upload/segment/extract/export |
| 29 | Haiku | README + push + gh pr create |

Opus is not required for any task in this plan — every step has a clear, mechanical or moderately-complex specification.

---

## Self-review notes

- All function names referenced across tasks line up: `slugify_filename` / `unique_slug` (Task 5) used in Task 10; `read_segments` / `write_segments` / `write_yolo` (Task 6) used in Tasks 11-14; `_YOLO_PREDICT_FN` / `_MINERU_EXTRACT_FN` test hooks declared in Tasks 11/13 and exercised in Tasks 11/13/25/26; `run_yolo` (Task 8) called from Task 11; `run_mineru` / `run_mineru_region` (Task 9) called from Task 13; `build_source_elements_payload` (Task 14) called from `/export` route also added in Task 14; `BoxKind` / `DocStatus` / `SegmentBox` / `SegmentsFile` / `DocMeta` / `HtmlPayload` (Task 2) used throughout backend; TS `BoxKind` / `SegmentBox` / `DocMeta` / `ExtractLine` / `SegmentLine` (Task 16) used in all frontend tasks; `apiBase()` / `apiFetch()` (Task 16) used by `streamSegment` / `streamExtract` (Task 23) and by `usePdfPage` / `PdfPage` indirectly (Task 18/25); `BoxOverlay` (Task 20) reused in `/segment` (Task 25) and `/extract` (Task 26); `useBoxHotkeys` (Task 19) attached in `/segment` (Task 25); `HtmlEditor` (Task 22) consumed in `/extract` (Task 26).
- No "TBD" / "similar to Task N" / "implement later" markers remain. Each task has full code, full tests with assertions, and a real commit message.
- Status transitions match D7: `raw → segmenting → extracting → done` (no auto-progression). The `/segment` route bumps to `segmenting`; `/extract` bumps to `extracting`; `/export` bumps to `done`.
- D8/D9 satisfied: per-PDF sidecar JSON in `data/raw-pdfs/<slug>/`; auto-save with 300ms debounce on the Tiptap → PUT /html path (Task 26).
- D14/D15 satisfied: 8 hotkeys in `useBoxHotkeys` (Task 19); 7 colors in `box-colors.css` (Task 20) plus a discard gray.
- D16 satisfied: `data-source-box="<box_id>"` round-trips through MinerU output (Task 13 fake_extract emits it; Task 14 converter consumes it; Task 22 HtmlEditor click handler finds it).
- D17 satisfied: `POST /api/docs/{slug}/extract/region` + `useExtractRegion` hook + ExtractRoute right-click handoff.
- D18 satisfied: every sidecar write goes through `_write_locked_text` (LOCK_EX + tmp + atomic rename).

