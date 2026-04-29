"""Core schema dataclasses: Event, Review, HumanActor, LLMActor, SourceElement.

All dataclasses are `frozen=True`. `__post_init__` does light
sanity-check validation only — no external resource access. The
`Actor` union (HumanActor | LLMActor) is dispatched via the `kind`
discriminator field at deserialization time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal


def _validate_iso_utc(value: str) -> None:
    """Raise ValueError if value is not a parseable ISO-8601 UTC timestamp."""
    if not value:
        raise ValueError("timestamp_utc must be non-empty")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"timestamp_utc not ISO-8601: {value!r}") from e


ElementType = Literal["paragraph", "heading", "table", "figure", "list_item"]
_ELEMENT_TYPES: tuple[str, ...] = (
    "paragraph",
    "heading",
    "table",
    "figure",
    "list_item",
)


@dataclass(frozen=True)
class SourceElement:
    """A pipeline-independent reference to a structural element in a source document.

    Element-IDs come from a structured-document parser (e.g., Document
    Intelligence) and are stable across pipelines: different pipelines may
    chunk these elements differently into their indexed chunks, but the
    element-ID itself is a property of the source document.

    This is the canonical ground-truth anchor for a goldset entry —
    pipeline-specific chunk-IDs are derived from it on demand for fast
    in-pipeline evaluation; cross-pipeline evaluation works directly on
    SourceElement IDs.
    """

    document_id: str
    page_number: int
    element_id: str
    element_type: ElementType

    def __post_init__(self) -> None:
        if not self.document_id:
            raise ValueError("document_id must be non-empty")
        if not self.element_id:
            raise ValueError("element_id must be non-empty")
        if self.page_number < 1:
            raise ValueError("page_number must be >= 1")
        if self.element_type not in _ELEMENT_TYPES:
            raise ValueError(f"unknown element_type: {self.element_type!r}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SourceElement:
        return cls(
            document_id=d["document_id"],
            page_number=d["page_number"],
            element_id=d["element_id"],
            element_type=d["element_type"],
        )


@dataclass(frozen=True)
class HumanActor:
    pseudonym: str
    level: Literal["expert", "phd", "masters", "bachelors", "other"]
    kind: Literal["human"] = "human"

    def __post_init__(self) -> None:
        if not self.pseudonym:
            raise ValueError("pseudonym must be non-empty")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> HumanActor:
        return cls(
            pseudonym=d["pseudonym"],
            level=d["level"],
            kind=d.get("kind", "human"),
        )


@dataclass(frozen=True)
class LLMActor:
    model: str
    model_version: str
    prompt_template_version: str
    temperature: float
    kind: Literal["llm"] = "llm"

    def __post_init__(self) -> None:
        for f_name in ("model", "model_version", "prompt_template_version"):
            if not getattr(self, f_name):
                raise ValueError(f"{f_name} must be non-empty")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> LLMActor:
        return cls(
            model=d["model"],
            model_version=d["model_version"],
            prompt_template_version=d["prompt_template_version"],
            temperature=d["temperature"],
            kind=d.get("kind", "llm"),
        )


Actor = HumanActor | LLMActor


CreateAction = Literal["created_from_scratch", "synthesised", "imported_from_faq"]
ReviewAction = Literal["accepted_unchanged", "approved", "rejected"]


def actor_from_dict(d: dict) -> Actor:
    """Dispatch on the 'kind' discriminator."""
    kind = d.get("kind")
    if kind == "human":
        return HumanActor.from_dict(d)
    if kind == "llm":
        return LLMActor.from_dict(d)
    raise ValueError(f"unknown actor kind: {kind!r}")


_REVIEW_ACTIONS = (
    "created_from_scratch",
    "synthesised",
    "imported_from_faq",
    "accepted_unchanged",
    "approved",
    "rejected",
    "deprecated",
)


@dataclass(frozen=True)
class Review:
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

    def __post_init__(self) -> None:
        _validate_iso_utc(self.timestamp_utc)
        if self.action not in _REVIEW_ACTIONS:
            raise ValueError(f"unknown review action: {self.action!r}")

    def to_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "action": self.action,
            "actor": self.actor.to_dict(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Review:
        return cls(
            timestamp_utc=d["timestamp_utc"],
            action=d["action"],
            actor=actor_from_dict(d["actor"]),
            notes=d.get("notes"),
        )


_EVENT_TYPES = ("created", "reviewed", "deprecated")


@dataclass(frozen=True)
class Event:
    event_id: str
    timestamp_utc: str
    event_type: Literal["created", "reviewed", "deprecated"]
    entry_id: str
    schema_version: int
    payload: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        if self.event_type not in _EVENT_TYPES:
            raise ValueError(f"unknown event_type: {self.event_type!r}")
        _validate_iso_utc(self.timestamp_utc)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "timestamp_utc": self.timestamp_utc,
            "event_type": self.event_type,
            "entry_id": self.entry_id,
            "schema_version": self.schema_version,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Event:
        return cls(
            event_id=d["event_id"],
            timestamp_utc=d["timestamp_utc"],
            event_type=d["event_type"],
            entry_id=d["entry_id"],
            schema_version=d["schema_version"],
            payload=d.get("payload", {}),
        )
