"""Pydantic schemas for the local-pdf HTTP API."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Re-export the worker event surface — the NDJSON streaming endpoints emit
# these directly. See `local_pdf.workers.base` for the source-of-truth.
from local_pdf.workers.base import (
    ModelLoadedEvent,
    ModelLoadingEvent,
    ModelUnloadedEvent,
    ModelUnloadingEvent,
    WorkCompleteEvent,
    WorkerEventUnion,
    WorkFailedEvent,
    WorkProgressEvent,
)

__all__ = [
    "BoxKind",
    "CreateBoxRequest",
    "Curator",
    "CuratorsFile",
    "DocMeta",
    "DocStatus",
    "ExtractRegionRequest",
    "HealthResponse",
    "HtmlPayload",
    "MergeBoxesRequest",
    "ModelLoadedEvent",
    "ModelLoadingEvent",
    "ModelUnloadedEvent",
    "ModelUnloadingEvent",
    "SegmentBox",
    "SegmentsFile",
    "SplitBoxRequest",
    "UpdateBoxRequest",
    "WorkCompleteEvent",
    "WorkFailedEvent",
    "WorkProgressEvent",
    "WorkerEventUnion",
]


class BoxKind(StrEnum):
    heading = "heading"
    paragraph = "paragraph"
    table = "table"
    figure = "figure"
    caption = "caption"
    formula = "formula"
    list_item = "list_item"
    discard = "discard"


class DocStatus(StrEnum):
    raw = "raw"
    segmenting = "segmenting"
    extracting = "extracting"
    extracted = "extracted"
    synthesising = "synthesising"
    synthesised = "synthesised"
    open_for_curation = "open-for-curation"
    archived = "archived"
    done = "done"  # legacy from A.0; keep for back-compat
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


class Curator(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    token_prefix: str
    token_sha256: str
    assigned_slugs: list[str] = Field(default_factory=list)
    created_at: str
    last_seen_at: str | None = None
    active: bool = True


class CuratorsFile(BaseModel):
    model_config = ConfigDict(frozen=True)
    curators: list[Curator] = Field(default_factory=list)
