"""Factory functions for the Azure SDK clients used by query_index.

Construction is lazy and parameterised on a Config — callers pass the config
they have, no module-level singletons. Tests patch the SDK classes here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from openai import AzureOpenAI

if TYPE_CHECKING:
    from query_index.config import Config


def get_openai_client(cfg: Config) -> AzureOpenAI:
    return AzureOpenAI(
        api_version=cfg.azure_openai_api_version,
        azure_endpoint=cfg.ai_foundry_endpoint,
        api_key=cfg.ai_foundry_key,
    )


def get_search_client(cfg: Config) -> SearchClient:
    return SearchClient(
        endpoint=cfg.ai_search_endpoint,
        index_name=cfg.ai_search_index_name,
        credential=AzureKeyCredential(cfg.ai_search_key),
    )


def get_search_index_client(cfg: Config) -> SearchIndexClient:
    return SearchIndexClient(
        endpoint=cfg.ai_search_endpoint,
        credential=AzureKeyCredential(cfg.ai_search_key),
    )
