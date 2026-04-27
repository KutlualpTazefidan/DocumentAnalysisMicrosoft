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
