"""Tests for query_index.client lazy-construction helpers."""

from __future__ import annotations

from unittest.mock import patch


def test_get_openai_client_constructs_azureopenai_with_config(
    env_vars: dict[str, str],
) -> None:
    from query_index.client import get_openai_client
    from query_index.config import Config

    cfg = Config.from_env()
    with patch("query_index.client.AzureOpenAI") as mock_cls:
        get_openai_client(cfg)
    mock_cls.assert_called_once_with(
        api_version=cfg.azure_openai_api_version,
        azure_endpoint=cfg.ai_foundry_endpoint,
        api_key=cfg.ai_foundry_key,
    )


def test_get_search_client_constructs_searchclient_with_config(
    env_vars: dict[str, str],
) -> None:
    from query_index.client import get_search_client
    from query_index.config import Config

    cfg = Config.from_env()
    with (
        patch("query_index.client.SearchClient") as mock_cls,
        patch("query_index.client.AzureKeyCredential") as mock_cred,
    ):
        mock_cred.return_value = "credential-instance"
        get_search_client(cfg)
    mock_cred.assert_called_once_with(cfg.ai_search_key)
    mock_cls.assert_called_once_with(
        endpoint=cfg.ai_search_endpoint,
        index_name=cfg.ai_search_index_name,
        credential="credential-instance",
    )


def test_get_search_index_client_constructs_with_config(
    env_vars: dict[str, str],
) -> None:
    from query_index.client import get_search_index_client
    from query_index.config import Config

    cfg = Config.from_env()
    with (
        patch("query_index.client.SearchIndexClient") as mock_cls,
        patch("query_index.client.AzureKeyCredential") as mock_cred,
    ):
        mock_cred.return_value = "credential-instance"
        get_search_index_client(cfg)
    mock_cred.assert_called_once_with(cfg.ai_search_key)
    mock_cls.assert_called_once_with(
        endpoint=cfg.ai_search_endpoint,
        credential="credential-instance",
    )
