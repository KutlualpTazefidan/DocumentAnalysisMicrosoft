"""Tests for the dataclasses in query_index.types."""

from __future__ import annotations

import pytest


def test_chunk_holds_id_title_chunk() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="Title", chunk="Some chunk body.")
    assert c.chunk_id == "c1"
    assert c.title == "Title"
    assert c.chunk == "Some chunk body."


def test_chunk_repr_excludes_chunk_field() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="T", chunk="SECRET-CONTENT")
    assert "SECRET-CONTENT" not in repr(c)


def test_chunk_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="T", chunk="x")
    with pytest.raises(FrozenInstanceError):
        c.chunk_id = "c2"  # type: ignore[misc]


def test_searchhit_holds_all_fields() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c1", title="T", chunk="body", score=0.87)
    assert h.chunk_id == "c1"
    assert h.title == "T"
    assert h.chunk == "body"
    assert h.score == pytest.approx(0.87)


def test_searchhit_repr_excludes_chunk_field() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c1", title="T", chunk="LEAKY", score=0.5)
    assert "LEAKY" not in repr(h)


def test_searchhit_str_shows_id_and_score_only() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c42", title="T", chunk="body", score=0.875)
    s = str(h)
    assert "c42" in s
    assert "0.875" in s
    assert "body" not in s


def test_chunk_accepts_optional_section_heading_and_source_file() -> None:
    from query_index.types import Chunk

    c = Chunk(
        chunk_id="c1",
        title="T",
        chunk="body",
        section_heading="3.3 Werkstoffkennwerte",
        source_file="GNB B 147_2001 Rev. 1.pdf",
    )
    assert c.section_heading == "3.3 Werkstoffkennwerte"
    assert c.source_file == "GNB B 147_2001 Rev. 1.pdf"


def test_chunk_section_heading_and_source_file_default_to_none() -> None:
    from query_index.types import Chunk

    c = Chunk(chunk_id="c1", title="T", chunk="body")
    assert c.section_heading is None
    assert c.source_file is None


def test_searchhit_accepts_optional_section_heading_and_source_file() -> None:
    from query_index.types import SearchHit

    h = SearchHit(
        chunk_id="c1",
        title="T",
        chunk="body",
        score=0.9,
        section_heading="3.3 Werkstoffkennwerte",
        source_file="GNB B 147_2001 Rev. 1.pdf",
    )
    assert h.section_heading == "3.3 Werkstoffkennwerte"
    assert h.source_file == "GNB B 147_2001 Rev. 1.pdf"


def test_searchhit_section_heading_and_source_file_default_to_none() -> None:
    from query_index.types import SearchHit

    h = SearchHit(chunk_id="c1", title="T", chunk="body", score=0.9)
    assert h.section_heading is None
    assert h.source_file is None
