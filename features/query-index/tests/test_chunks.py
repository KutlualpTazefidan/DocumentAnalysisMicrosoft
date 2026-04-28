"""Tests for query_index.chunks (get_chunk, sample_chunks)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_get_chunk_returns_chunk_for_known_id(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import get_chunk
    from query_index.config import Config
    from query_index.types import Chunk

    mock_search_client.get_document.return_value = {
        "id": "c42",
        "title": "Section 4.2",
        "chunk": "Tragkorbdurchmesser ...",
        "section_heading": "4.2 Konstruktion",
        "source_file": "doc1.pdf",
    }
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = get_chunk("c42", cfg)

    assert isinstance(result, Chunk)
    assert result.chunk_id == "c42"
    assert result.title == "Section 4.2"
    assert result.chunk == "Tragkorbdurchmesser ..."
    assert result.section_heading == "4.2 Konstruktion"
    assert result.source_file == "doc1.pdf"
    mock_search_client.get_document.assert_called_once_with(key="c42")


def test_get_chunk_handles_missing_optional_fields(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """Backwards-compat for indexes without section_heading/source_file."""
    from query_index.chunks import get_chunk
    from query_index.config import Config

    mock_search_client.get_document.return_value = {
        "id": "c42",
        "title": "T",
        "chunk": "body",
    }
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = get_chunk("c42", cfg)

    assert result.section_heading is None
    assert result.source_file is None


def test_sample_chunks_returns_n_chunks(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config
    from query_index.types import Chunk

    mock_search_client.search.return_value = [
        {"id": f"c{i}", "title": f"T{i}", "chunk": f"body{i}"} for i in range(5)
    ]
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = sample_chunks(n=5, seed=42, cfg=cfg)

    assert len(result) == 5
    assert all(isinstance(c, Chunk) for c in result)


def test_sample_chunks_pulls_a_window_at_least_as_large_as_sample_window(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import SAMPLE_WINDOW, sample_chunks
    from query_index.config import Config

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        sample_chunks(n=3, seed=1, cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["top"] == max(3, SAMPLE_WINDOW)


def test_sample_chunks_deterministic_for_same_seed(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config

    docs = [{"id": f"c{i}", "title": f"T{i}", "chunk": f"b{i}"} for i in range(20)]
    mock_search_client.search.return_value = docs
    cfg = Config.from_env()

    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        run1 = sample_chunks(n=5, seed=12345, cfg=cfg)
    mock_search_client.search.return_value = docs
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        run2 = sample_chunks(n=5, seed=12345, cfg=cfg)

    assert [c.chunk_id for c in run1] == [c.chunk_id for c in run2]


def test_sample_chunks_raises_when_n_zero_or_negative(env_vars: dict[str, str]) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config

    cfg = Config.from_env()
    with pytest.raises(ValueError):
        sample_chunks(n=0, seed=1, cfg=cfg)
    with pytest.raises(ValueError):
        sample_chunks(n=-1, seed=1, cfg=cfg)
