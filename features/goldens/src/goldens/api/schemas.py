"""API-only Pydantic models. Domain models live in goldens.schemas (Pydantic
since PR #22) and are exposed by the routers directly via response_model=."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# DocumentElement and its ElementType field need runtime resolvability so
# Pydantic can build ElementWithCounts (see model_rebuild at module bottom).
from goldens.creation.elements.adapter import DocumentElement  # noqa: TC001
from goldens.schemas import ElementType  # noqa: F401

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

ElementWithCounts.model_rebuild()
