"""Chunker name → class mapping.

To add a new strategy:
  1. Implement a class conforming to the Chunker Protocol in a new module
     under `chunkers/`.
  2. Import it here and add to _REGISTRY.
  3. Add tests for it under `tests/unit/test_chunkers_<name>.py`.

V1 ships only the section chunker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ingestion.chunkers.section import SectionChunker

if TYPE_CHECKING:
    from ingestion.chunkers.base import Chunker

_REGISTRY: dict[str, type[Chunker]] = {
    "section": SectionChunker,
}


def get_chunker(name: str) -> Chunker:
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown chunker strategy: {name!r}. Available: {available}")
    return _REGISTRY[name]()


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)
