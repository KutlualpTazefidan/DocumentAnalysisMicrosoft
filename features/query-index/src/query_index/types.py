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
