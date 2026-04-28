"""Tests for the re-exported public API at ingestion.__init__."""

from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import ingestion

    expected = {
        "IngestionConfig",
        "RawChunk",
        "analyze_pdf",
        "chunk",
        "embed_chunks",
        "get_chunker",
        "list_strategies",
        "slug_from_filename",
        "upload_chunks",
    }
    missing = expected - set(dir(ingestion))
    assert not missing, f"Missing public exports: {missing}"
