"""RawChunk dataclass and Chunker Protocol.

The Chunker Protocol is the plugin point for chunking strategies. Each
strategy implementation declares a `name` (used in CLI --strategy and in
output filenames) and provides a `chunk()` method that yields RawChunks
from a Document Intelligence analyze result dict.

V1 ships only the section chunker (in `section.py`); future strategies
(fixed-size, llm-based) plug in at the same interface without changing
the CLI or downstream stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RawChunk:
    """One chunk produced by a chunker.

    Serialised to a JSONL line in the chunk-stage output. The `vector` field
    is added later by the embed stage, but is NOT part of RawChunk.
    """

    chunk_id: str
    title: str
    section_heading: str
    chunk: str
    source_file: str


@runtime_checkable
class Chunker(Protocol):
    """Protocol for chunking strategies."""

    name: str

    def chunk(
        self,
        analyze_result: dict,
        slug: str,
        source_file: str,
    ) -> list[RawChunk]: ...
