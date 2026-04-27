"""Tests for query_index.config.Config.from_env()."""

from __future__ import annotations

import pytest


def test_from_env_loads_all_required_fields(env_vars: dict[str, str]) -> None:
    from query_index.config import Config

    cfg = Config.from_env()
    assert cfg.ai_foundry_key == env_vars["AI_FOUNDRY_KEY"]
    assert cfg.ai_foundry_endpoint == env_vars["AI_FOUNDRY_ENDPOINT"]
    assert cfg.ai_search_key == env_vars["AI_SEARCH_KEY"]
    assert cfg.ai_search_endpoint == env_vars["AI_SEARCH_ENDPOINT"]
    assert cfg.ai_search_index_name == env_vars["AI_SEARCH_INDEX_NAME"]
    assert cfg.embedding_deployment_name == env_vars["EMBEDDING_DEPLOYMENT_NAME"]
    assert cfg.embedding_model_version == env_vars["EMBEDDING_MODEL_VERSION"]
    assert cfg.embedding_dimensions == int(env_vars["EMBEDDING_DIMENSIONS"])
    assert cfg.azure_openai_api_version == env_vars["AZURE_OPENAI_API_VERSION"]


def test_from_env_is_frozen(env_vars: dict[str, str]) -> None:
    from dataclasses import FrozenInstanceError

    from query_index.config import Config

    cfg = Config.from_env()
    with pytest.raises(FrozenInstanceError):
        cfg.ai_foundry_key = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    "missing_var",
    [
        "AI_FOUNDRY_KEY",
        "AI_FOUNDRY_ENDPOINT",
        "AI_SEARCH_KEY",
        "AI_SEARCH_ENDPOINT",
        "AI_SEARCH_INDEX_NAME",
        "EMBEDDING_DEPLOYMENT_NAME",
        "EMBEDDING_MODEL_VERSION",
        "EMBEDDING_DIMENSIONS",
        "AZURE_OPENAI_API_VERSION",
    ],
)
def test_from_env_raises_with_clear_message_when_required_missing(
    env_vars: dict[str, str], monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    from query_index.config import Config

    monkeypatch.delenv(missing_var, raising=False)
    with pytest.raises(KeyError) as excinfo:
        Config.from_env()
    assert missing_var in str(excinfo.value)


def test_embedding_dimensions_must_be_integer(
    env_vars: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from query_index.config import Config

    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "not-a-number")
    with pytest.raises(ValueError):
        Config.from_env()
