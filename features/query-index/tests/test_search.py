"""Tests for query_index.search.hybrid_search()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_hybrid_search_returns_list_of_searchhits(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search
    from query_index.types import SearchHit

    mock_search_client.search.return_value = [
        {
            "id": "c1",
            "title": "Title 1",
            "chunk": "Body 1",
            "section_heading": "Section A",
            "source_file": "doc1.pdf",
            "@search.score": 0.91,
        },
        {
            "id": "c2",
            "title": "Title 2",
            "chunk": "Body 2",
            "section_heading": "Section B",
            "source_file": "doc1.pdf",
            "@search.score": 0.55,
        },
    ]
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.1] * 3072),
    ):
        results = hybrid_search("query text", top=2, cfg=cfg)

    assert len(results) == 2
    assert all(isinstance(r, SearchHit) for r in results)
    assert results[0].chunk_id == "c1"
    assert results[0].section_heading == "Section A"
    assert results[0].source_file == "doc1.pdf"
    assert results[0].score == 0.91


def test_hybrid_search_handles_missing_optional_fields(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    """Backwards-compat: indexes without section_heading/source_file still work."""
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = [
        {
            "id": "c1",
            "title": "Title 1",
            "chunk": "Body 1",
            "@search.score": 0.91,
        },
    ]
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.1] * 3072),
    ):
        results = hybrid_search("q", top=1, cfg=cfg)

    assert results[0].section_heading is None
    assert results[0].source_file is None


def test_hybrid_search_passes_text_and_vector_to_searchclient(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.7] * 3072),
    ):
        hybrid_search("the query", top=5, cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["search_text"] == "the query"
    assert kwargs["top"] == 5
    vector_queries = kwargs["vector_queries"]
    assert len(vector_queries) == 1
    assert vector_queries[0].vector == [0.7] * 3072
    assert vector_queries[0].k_nearest_neighbors == 5
    assert vector_queries[0].fields == "chunkVector"


def test_hybrid_search_passes_filter_when_provided(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.0] * 3072),
    ):
        hybrid_search("q", top=3, filter="source_file eq 'doc1.pdf'", cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs["filter"] == "source_file eq 'doc1.pdf'"


def test_hybrid_search_omits_filter_when_none(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.0] * 3072),
    ):
        hybrid_search("q", top=3, cfg=cfg)

    _, kwargs = mock_search_client.search.call_args
    assert kwargs.get("filter") is None


def test_hybrid_search_returns_empty_list_when_no_results(
    env_vars: dict[str, str], mock_search_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.search import hybrid_search

    mock_search_client.search.return_value = []
    cfg = Config.from_env()
    with (
        patch("query_index.search.get_search_client", return_value=mock_search_client),
        patch("query_index.search.get_embedding", return_value=[0.0] * 3072),
    ):
        results = hybrid_search("q", top=3, cfg=cfg)

    assert results == []
