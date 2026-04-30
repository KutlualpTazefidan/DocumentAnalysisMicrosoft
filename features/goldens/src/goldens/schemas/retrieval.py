"""RetrievalEntry — the first concrete entry type in the goldens
event-sourced model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from goldens.schemas.base import HumanActor, Review, SourceElement

_HUMAN_LEVEL_ORDER: tuple[str, ...] = (
    "expert",
    "phd",
    "masters",
    "bachelors",
    "other",
)


def _highest_level(
    review_chain: tuple[Review, ...],
) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
    """Return the highest-ranked human level from the review chain;
    'synthetic' if no human has ever touched the entry."""
    human_levels = {r.actor.level for r in review_chain if isinstance(r.actor, HumanActor)}
    if not human_levels:
        return "synthetic"
    for tier in _HUMAN_LEVEL_ORDER:
        if tier in human_levels:
            return tier  # type: ignore[return-value]
    # Unreachable: HumanActor.level is constrained to the same Literal.
    raise ValueError(f"no recognised level in {human_levels}")  # pragma: no cover


class RetrievalEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: str
    query: str
    expected_chunk_ids: tuple[str, ...]
    chunk_hashes: dict[str, str]
    review_chain: tuple[Review, ...]
    deprecated: bool
    refines: str | None = None
    task_type: Literal["retrieval"] = "retrieval"
    # Pipeline-independent ground truth: the source-document element from which
    # this entry's question was curated (Document Intelligence ID, stable across
    # pipelines). Optional for backward-compatibility with pre-A.3.1 entries.
    source_element: SourceElement | None = None

    @field_validator("entry_id", "query", mode="after")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("must be non-empty")
        return v

    @property
    def level(
        self,
    ) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
        """Highest reviewer level in the chain. NOT serialized — derived state."""
        return _highest_level(self.review_chain)
