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
        "chunk_id": "c42",
        "title": "Section 4.2",
        "chunk": "Tragkorbdurchmesser ...",
    }
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = get_chunk("c42", cfg)

    assert isinstance(result, Chunk)
    assert result.chunk_id == "c42"
    assert result.title == "Section 4.2"
    assert result.chunk == "Tragkorbdurchmesser ..."
    mock_search_client.get_document.assert_called_once_with(key="c42")


def test_sample_chunks_returns_n_chunks(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.chunks import sample_chunks
    from query_index.config import Config
    from query_index.types import Chunk

    mock_search_client.search.return_value = [
        {"chunk_id": f"c{i}", "title": f"T{i}", "chunk": f"body{i}"} for i in range(5)
    ]
    cfg = Config.from_env()
    with patch("query_index.chunks.get_search_client", return_value=mock_search_client):
        result = sample_chunks(n=5, seed=42, cfg=cfg)

    assert len(result) == 5
    assert all(isinstance(c, Chunk) for c in result)


def test_sample_chunks_pulls_a_window_at_least_as_large_as_sample_window(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """sample_chunks pulls a window of at least SAMPLE_WINDOW docs (or n if n
    is larger) before shuffling, so the returned sample is meaningfully random
    rather than just the top-n by relevance."""
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
    """Same seed must produce the same shuffled selection of chunk_ids
    given the same upstream document set."""
    from query_index.chunks import sample_chunks
    from query_index.config import Config

    docs = [{"chunk_id": f"c{i}", "title": f"T{i}", "chunk": f"b{i}"} for i in range(20)]
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
