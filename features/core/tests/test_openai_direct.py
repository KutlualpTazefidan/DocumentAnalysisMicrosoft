"""Skeleton tests for the OpenAI direct backend.

Covers config + happy-path complete + happy-path embed. Error
translation is identical to AzureOpenAIClient and is exercised
there; we don't duplicate the full error matrix here.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from llm_clients.base import (
    Completion,
    LLMConfigError,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
)
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig


@pytest.fixture
def cfg() -> OpenAIDirectConfig:
    return OpenAIDirectConfig(api_key="sk-test", base_url="https://api.openai.com/v1")


@pytest.fixture
def client(cfg: OpenAIDirectConfig) -> OpenAIDirectClient:
    return OpenAIDirectClient(cfg)


def test_config_from_env_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        OpenAIDirectConfig.from_env()


def test_config_from_env_uses_default_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    cfg = OpenAIDirectConfig.from_env()
    assert cfg.base_url == "https://api.openai.com/v1"


@respx.mock
def test_complete_happy_path(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "id": "abc",
                "object": "chat.completion",
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    out: Completion = client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")
    assert out.text == "hi"


@respx.mock
def test_embed_happy_path(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )
    )
    out = client.embed(texts=["x"], model="text-embedding-3-large")
    assert out == [[0.1, 0.2]]


@respx.mock
def test_complete_passes_max_tokens_and_response_format(client: OpenAIDirectClient):
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
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
        max_tokens=64,
        response_format=ResponseFormat(type="json_object"),
    )
    payload = route.calls[0].request.read().decode()
    assert "max_tokens" in payload
    assert "json_object" in payload


@respx.mock
def test_complete_translates_429_to_rate_limit_error(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(429, json={"error": {"message": "rate"}})
    )
    with pytest.raises(LLMRateLimitError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_complete_translates_500_to_server_error(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(500, json={"error": {"message": "boom"}})
    )
    with pytest.raises(LLMServerError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_embed_translates_429_to_rate_limit_error(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(429, json={"error": {"message": "rate"}})
    )
    with pytest.raises(LLMRateLimitError):
        client.embed(texts=["x"], model="text-embedding-3-large")
