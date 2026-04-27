"""Shared fixtures for ingestion tests. All Azure clients mocked."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from pathlib import Path  # noqa: F401


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Populate the environment with valid dummy values for both Configs."""
    values = {
        # Document Intelligence
        "DOC_INTEL_ENDPOINT": "https://test-doc-intel.example.com/",
        "DOC_INTEL_KEY": "test-doc-intel-key",
        # query-index pass-through
        "AI_FOUNDRY_KEY": "test-foundry-key",
        "AI_FOUNDRY_ENDPOINT": "https://test-foundry.example.com",
        "AI_SEARCH_KEY": "test-search-key",
        "AI_SEARCH_ENDPOINT": "https://test-search.example.com",
        "AI_SEARCH_INDEX_NAME": "test-index",
        "EMBEDDING_DEPLOYMENT_NAME": "test-embedding-deployment",
        "EMBEDDING_MODEL_VERSION": "1",
        "EMBEDDING_DIMENSIONS": "3072",
        "AZURE_OPENAI_API_VERSION": "2024-02-01",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


@pytest.fixture
def mock_doc_intel_client() -> MagicMock:
    """A MagicMock that mimics azure.ai.documentintelligence.DocumentIntelligenceClient."""
    return MagicMock()


@pytest.fixture
def mock_search_client() -> MagicMock:
    """A MagicMock that mimics azure.search.documents.SearchClient."""
    client = MagicMock()
    client.search.return_value = []
    return client


@pytest.fixture
def mock_search_index_client() -> MagicMock:
    """A MagicMock that mimics azure.search.documents.indexes.SearchIndexClient."""
    return MagicMock()


@pytest.fixture
def sample_analyze_result() -> dict:
    """A minimal Document Intelligence layout response with title, headings, body, and pageFooter.

    Used by chunker tests to verify the section chunker behaviour without
    needing to mock the full Document Intelligence response shape.
    """
    return {
        "_ingestion_metadata": {
            "source_file": "GNB B 147_2001 Rev. 1.pdf",
            "slug": "gnb-b-147-2001-rev-1",
            "timestamp_utc": "20260427T143000",
        },
        "analyzeResult": {
            "apiVersion": "2024-11-30",
            "modelId": "prebuilt-layout",
            "paragraphs": [
                {"content": "Test Document Title", "role": "title"},
                {"content": "Page header", "role": "pageHeader"},
                {"content": "1. Introduction", "role": "sectionHeading"},
                {"content": "Intro body paragraph 1.", "role": None},
                {"content": "Intro body paragraph 2.", "role": None},
                {"content": "Page 2 / 5", "role": "pageFooter"},
                {"content": "2. Methods", "role": "sectionHeading"},
                {"content": "Methods body paragraph.", "role": None},
                {"content": "Footnote text", "role": "footnote"},
            ],
        },
    }
