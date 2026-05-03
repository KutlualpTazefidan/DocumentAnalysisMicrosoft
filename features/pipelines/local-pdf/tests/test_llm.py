"""Tests for local_pdf.llm — client factory + model selection."""

from __future__ import annotations

import pytest


def test_get_llm_client_returns_ollama_by_default(monkeypatch) -> None:
    from llm_clients.ollama_local import OllamaLocalClient

    monkeypatch.delenv("LLM_BACKEND", raising=False)
    from local_pdf.llm import get_llm_client

    client = get_llm_client()
    assert isinstance(client, OllamaLocalClient)


def test_get_llm_client_returns_azure_when_env_set(monkeypatch) -> None:
    from llm_clients.azure_openai import AzureOpenAIClient

    monkeypatch.setenv("LLM_BACKEND", "azure_openai")
    monkeypatch.setenv("AI_FOUNDRY_KEY", "key")
    monkeypatch.setenv("AI_FOUNDRY_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-15-preview")
    monkeypatch.setenv("CHAT_DEPLOYMENT_NAME", "gpt-4o")
    monkeypatch.setenv("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-ada-002")
    from local_pdf.llm import get_llm_client

    client = get_llm_client()
    assert isinstance(client, AzureOpenAIClient)


def test_get_llm_client_raises_on_unknown_backend(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BACKEND", "unknown_vendor")
    from local_pdf.llm import get_llm_client

    with pytest.raises(ValueError, match="unsupported backend"):
        get_llm_client()


def test_get_default_model_returns_qwen_default(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    from local_pdf.llm import get_default_model

    assert get_default_model() == "qwen2.5:7b-instruct"


def test_get_default_model_respects_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "llama3:8b")
    from local_pdf.llm import get_default_model

    assert get_default_model() == "llama3:8b"
