"""Tests for the re-exported public API at query_index.__init__."""

from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index

    expected = {
        "Chunk",
        "Config",
        "SearchHit",
        "get_chunk",
        "get_embedding",
        "hybrid_search",
        "sample_chunks",
    }
    missing = expected - set(dir(query_index))
    assert not missing, f"Missing public exports: {missing}"


def test_public_api_does_not_expose_helpers() -> None:
    import query_index

    not_expected = {"get_openai_client", "get_search_client", "get_search_index_client"}
    overexposed = not_expected & set(dir(query_index))
    assert not overexposed, f"Helpers leaked into public API: {overexposed}"
