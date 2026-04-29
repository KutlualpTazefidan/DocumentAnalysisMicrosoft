"""RetrievalEntry — the first concrete entry type in the goldens
event-sourced model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from goldens.schemas.base import HumanActor, Review

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


@dataclass(frozen=True)
class RetrievalEntry:
    entry_id: str
    query: str
    expected_chunk_ids: tuple[str, ...]
    chunk_hashes: dict[str, str]
    review_chain: tuple[Review, ...]
    deprecated: bool
    refines: str | None = None
    task_type: Literal["retrieval"] = "retrieval"

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not self.query:
            raise ValueError("query must be non-empty")

    @property
    def level(
        self,
    ) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
        return _highest_level(self.review_chain)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "query": self.query,
            "expected_chunk_ids": list(self.expected_chunk_ids),
            "chunk_hashes": dict(self.chunk_hashes),
            "review_chain": [r.to_dict() for r in self.review_chain],
            "deprecated": self.deprecated,
            "refines": self.refines,
            "task_type": self.task_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RetrievalEntry:
        return cls(
            entry_id=d["entry_id"],
            query=d["query"],
            expected_chunk_ids=tuple(d["expected_chunk_ids"]),
            chunk_hashes=dict(d["chunk_hashes"]),
            review_chain=tuple(Review.from_dict(r) for r in d["review_chain"]),
            deprecated=d["deprecated"],
            refines=d.get("refines"),
            task_type=d.get("task_type", "retrieval"),
        )
