"""Shared fixtures for query_index tests. All fixtures mock Azure clients."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Populate the environment with valid dummy values for Config.from_env()."""
    values = {
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
def mock_openai_client() -> MagicMock:
    """A MagicMock that mimics openai.AzureOpenAI."""
    client = MagicMock()
    client.embeddings.create.return_value = MagicMock(data=[MagicMock(embedding=[0.1] * 3072)])
    return client


@pytest.fixture
def mock_search_client() -> MagicMock:
    """A MagicMock that mimics azure.search.documents.SearchClient."""
    client = MagicMock()
    client.search.return_value = []
    return client
