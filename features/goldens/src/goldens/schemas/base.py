"""Core schema models: Event, Review, HumanActor, LLMActor, SourceElement.

All models are `frozen=True` (Pydantic v2 ConfigDict). Validation lives
in `@field_validator` (replaces dataclass `__post_init__`). The Actor
union is `Annotated[HumanActor | LLMActor, Field(discriminator="kind")]`.

For backwards compatibility with callers that historically used the
dataclass `to_dict` / `from_dict` API, we keep `actor_from_dict` as a
helper that wraps `TypeAdapter[Actor].validate_python`. New code should
use `model_dump(mode="json")` / `model_validate` directly on the model
classes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator


def _validate_iso_utc(value: str) -> str:
    """Raise ValueError if value is not a parseable ISO-8601 UTC timestamp.

    Mirrors the dataclass `_validate_iso_utc` from the pre-Pydantic
    implementation so the validation surface is identical.
    """
    if not value:
        raise ValueError("timestamp_utc must be non-empty")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"timestamp_utc not ISO-8601: {value!r}") from e
    return value


ElementType = Literal["paragraph", "heading", "table", "figure", "list_item"]


class SourceElement(BaseModel):
    """A pipeline-independent reference to a structural element in a source document."""

    model_config = ConfigDict(frozen=True)

    document_id: str
    page_number: int
    element_id: str
    element_type: ElementType

    @field_validator("document_id", "element_id", mode="after")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @field_validator("page_number", mode="after")
    @classmethod
    def _page_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("page_number must be >= 1")
        return v


class HumanActor(BaseModel):
    model_config = ConfigDict(frozen=True)

    pseudonym: str
    level: Literal["expert", "phd", "masters", "bachelors", "other"]
    kind: Literal["human"] = "human"

    @field_validator("pseudonym", mode="after")
    @classmethod
    def _pseudonym_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("pseudonym must be non-empty")
        return v


class LLMActor(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str
    model_version: str
    prompt_template_version: str
    temperature: float
    kind: Literal["llm"] = "llm"

    @field_validator("model", "model_version", "prompt_template_version", mode="after")
    @classmethod
    def _str_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v


# Discriminated union — Pydantic v2 dispatches on `kind` automatically.
Actor = Annotated[HumanActor | LLMActor, Field(discriminator="kind")]

# Module-level adapter for the union (TypeAdapter cannot be used inside
# a model; it's a free-standing utility for the projection layer).
_actor_adapter: TypeAdapter[HumanActor | LLMActor] = TypeAdapter(Actor)


def actor_from_dict(d: dict) -> HumanActor | LLMActor:
    """Dispatch on the 'kind' discriminator (backwards-compat helper)."""
    kind = d.get("kind")
    if kind not in ("human", "llm"):
        raise ValueError(f"unknown actor kind: {kind!r}")
    return _actor_adapter.validate_python(d)  # type: ignore[no-any-return]  # TypeAdapter[HumanActor | LLMActor].validate_python inferred as Any by mypy; runtime type is correct


CreateAction = Literal["created_from_scratch", "synthesised", "imported_from_faq"]
ReviewAction = Literal["accepted_unchanged", "approved", "rejected"]


_REVIEW_ACTIONS = (
    "created_from_scratch",
    "synthesised",
    "imported_from_faq",
    "accepted_unchanged",
    "approved",
    "rejected",
    "deprecated",
)


class Review(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp_utc: str
    action: Literal[
        "created_from_scratch",
        "synthesised",
        "imported_from_faq",
        "accepted_unchanged",
        "approved",
        "rejected",
        "deprecated",
    ]
    actor: Actor
    notes: str | None = None

    @field_validator("timestamp_utc", mode="after")
    @classmethod
    def _ts_iso(cls, v: str) -> str:
        return _validate_iso_utc(v)


_EVENT_TYPES = ("created", "reviewed", "deprecated")


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    timestamp_utc: str
    event_type: Literal["created", "reviewed", "deprecated"]
    entry_id: str
    schema_version: int
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "entry_id", mode="after")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @field_validator("schema_version", mode="after")
    @classmethod
    def _schema_version_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("schema_version must be >= 1")
        return v

    @field_validator("timestamp_utc", mode="after")
    @classmethod
    def _ts_iso(cls, v: str) -> str:
        return _validate_iso_utc(v)
