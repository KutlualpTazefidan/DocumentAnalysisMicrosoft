"""Tests for query_index.embeddings.get_embedding()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_get_embedding_calls_openai_with_text_and_deployment_name(
    env_vars: dict[str, str], mock_openai_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.embeddings import get_embedding

    cfg = Config.from_env()
    with patch("query_index.embeddings.get_openai_client", return_value=mock_openai_client):
        result = get_embedding("hello world", cfg)

    assert result == [0.1] * 3072
    mock_openai_client.embeddings.create.assert_called_once_with(
        input=["hello world"], model=cfg.embedding_deployment_name
    )


def test_get_embedding_returns_list_of_floats(
    env_vars: dict[str, str], mock_openai_client: MagicMock
) -> None:
    from query_index.config import Config
    from query_index.embeddings import get_embedding

    mock_openai_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.5, 0.25, 0.125])]
    )
    cfg = Config.from_env()
    with patch("query_index.embeddings.get_openai_client", return_value=mock_openai_client):
        result = get_embedding("hi", cfg)

    assert result == [0.5, 0.25, 0.125]
    assert all(isinstance(x, float) for x in result)


def test_get_embedding_loads_config_from_env_when_cfg_omitted(
    env_vars: dict[str, str], mock_openai_client: MagicMock
) -> None:
    """When called without cfg, the function loads Config.from_env() itself.
    This exercises the hybrid-cfg convention used across the public API."""
    from query_index.embeddings import get_embedding

    with patch("query_index.embeddings.get_openai_client", return_value=mock_openai_client):
        result = get_embedding("hi")  # no cfg passed

    assert result == [0.1] * 3072
    mock_openai_client.embeddings.create.assert_called_once()
