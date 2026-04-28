"""Tests for ingestion.chunkers.base — RawChunk dataclass and Chunker Protocol."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest


def test_raw_chunk_holds_all_fields() -> None:
    from ingestion.chunkers.base import RawChunk

    rc = RawChunk(
        chunk_id="foo-001",
        title="Test Document",
        section_heading="1. Introduction",
        chunk="Body text.",
        source_file="foo.pdf",
    )
    assert rc.chunk_id == "foo-001"
    assert rc.title == "Test Document"
    assert rc.section_heading == "1. Introduction"
    assert rc.chunk == "Body text."
    assert rc.source_file == "foo.pdf"


def test_raw_chunk_round_trip_via_asdict() -> None:
    from ingestion.chunkers.base import RawChunk

    rc = RawChunk("foo-001", "T", "S", "body", "foo.pdf")
    out = asdict(rc)
    assert out == {
        "chunk_id": "foo-001",
        "title": "T",
        "section_heading": "S",
        "chunk": "body",
        "source_file": "foo.pdf",
    }
    rc2 = RawChunk(**out)
    assert rc2 == rc


def test_raw_chunk_is_frozen() -> None:
    from ingestion.chunkers.base import RawChunk

    rc = RawChunk("a", "b", "c", "d", "e")
    with pytest.raises(FrozenInstanceError):
        rc.chunk_id = "x"  # type: ignore[misc]


def test_chunker_protocol_is_runtime_checkable() -> None:
    """A class with the right shape passes isinstance() against Chunker."""
    from ingestion.chunkers.base import Chunker, RawChunk

    class FakeChunker:
        name = "fake"

        def chunk(
            self,
            analyze_result: dict,
            slug: str,
            source_file: str,
        ) -> list[RawChunk]:
            return []

    assert isinstance(FakeChunker(), Chunker)
