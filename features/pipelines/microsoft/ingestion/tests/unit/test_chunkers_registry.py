"""Tests for ingestion.chunkers.registry."""

from __future__ import annotations

import pytest


def test_get_chunker_returns_section_chunker() -> None:
    from ingestion.chunkers.registry import get_chunker
    from ingestion.chunkers.section import SectionChunker

    chunker = get_chunker("section")
    assert isinstance(chunker, SectionChunker)
    assert chunker.name == "section"


def test_get_chunker_raises_on_unknown_name() -> None:
    from ingestion.chunkers.registry import get_chunker

    with pytest.raises(ValueError, match="Unknown chunker strategy"):
        get_chunker("does-not-exist")


def test_get_chunker_error_lists_available_strategies() -> None:
    from ingestion.chunkers.registry import get_chunker

    with pytest.raises(ValueError) as excinfo:
        get_chunker("does-not-exist")
    assert "section" in str(excinfo.value)


def test_list_strategies_returns_sorted_names() -> None:
    from ingestion.chunkers.registry import list_strategies

    out = list_strategies()
    assert "section" in out
    assert out == sorted(out)
