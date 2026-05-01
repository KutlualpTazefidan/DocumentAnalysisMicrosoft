"""Pydantic schemas for the local-pdf HTTP API."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
