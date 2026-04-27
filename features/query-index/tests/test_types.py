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
