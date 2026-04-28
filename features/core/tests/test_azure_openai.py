"""Tests for the Azure OpenAI backend.

HTTP responses are mocked at the httpx transport layer with `respx`.
The openai SDK uses httpx underneath, so respx routes intercept the
real HTTP calls without us mocking the SDK directly.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from llm_clients.azure_openai import AzureOpenAIClient, AzureOpenAIConfig
from llm_clients.base import (
    Completion,
    LLMConfigError,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
)


@pytest.fixture
def cfg() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        endpoint="https://test-foundry.services.ai.azure.com",
        api_key="test-key",
        api_version="2024-02-01",
        chat_deployment_name="gpt-4o",
        embedding_deployment_name="text-embedding-3-large",
    )


@pytest.fixture
def client(cfg: AzureOpenAIConfig) -> AzureOpenAIClient:
    return AzureOpenAIClient(cfg)


def test_config_from_env_raises_when_required_var_missing(monkeypatch):
    for v in (
        "AI_FOUNDRY_KEY",
        "AI_FOUNDRY_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "CHAT_DEPLOYMENT_NAME",
        "EMBEDDING_DEPLOYMENT_NAME",
    ):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(LLMConfigError, match="Missing"):
        AzureOpenAIConfig.from_env()


def test_config_from_env_constructs_when_all_set(monkeypatch):
    monkeypatch.setenv("AI_FOUNDRY_KEY", "k")
    monkeypatch.setenv("AI_FOUNDRY_ENDPOINT", "https://e.example")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    monkeypatch.setenv("CHAT_DEPLOYMENT_NAME", "gpt-4o")
    monkeypatch.setenv("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    cfg = AzureOpenAIConfig.from_env()
    assert cfg.api_key == "k"
    assert cfg.chat_deployment_name == "gpt-4o"


@respx.mock
def test_complete_returns_text_and_usage(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(
        return_value=Response(
            200,
            json={
                "id": "abc",
                "object": "chat.completion",
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            },
        )
    )
    out: Completion = client.complete(
        messages=[Message(role="user", content="hi")],
        model="gpt-4o",
    )
    assert out.text == "hello"
    assert out.model == "gpt-4o-2024-08-06"
    assert out.usage is not None
    assert out.usage.total_tokens == 6


@respx.mock
def test_complete_passes_response_format_when_set(client: AzureOpenAIClient):
    route = respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(
        return_value=Response(
            200,
            json={
                "id": "abc",
                "object": "chat.completion",
                "model": "gpt-4o",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    client.complete(
        messages=[Message(role="user", content="hi")],
        model="gpt-4o",
        response_format=ResponseFormat(type="json_object"),
    )
    payload = route.calls[0].request.read().decode()
    assert "json_object" in payload


@respx.mock
def test_complete_translates_429_to_rate_limit_error(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(return_value=Response(429, json={"error": {"message": "rate"}}))
    with pytest.raises(LLMRateLimitError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_complete_translates_500_to_server_error(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(return_value=Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(LLMServerError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_complete_translates_401_to_config_error(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(return_value=Response(401, json={"error": {"message": "auth"}}))
    with pytest.raises(LLMConfigError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_embed_returns_vectors(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/text-embedding-3-large/embeddings"
    ).mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
                    {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )
    )
    vectors = client.embed(texts=["a", "b"], model="text-embedding-3-large")
    assert len(vectors) == 2
    assert vectors[0] == [0.1, 0.2, 0.3]
