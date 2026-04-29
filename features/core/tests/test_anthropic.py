"""Skeleton tests for the Anthropic backend."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from llm_clients.anthropic import AnthropicClient, AnthropicConfig
from llm_clients.base import (
    Completion,
    LLMConfigError,
    LLMRateLimitError,
    LLMServerError,
    Message,
)


@pytest.fixture
def cfg() -> AnthropicConfig:
    return AnthropicConfig(api_key="sk-ant-test")


@pytest.fixture
def client(cfg: AnthropicConfig) -> AnthropicClient:
    return AnthropicClient(cfg)


def test_config_from_env_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicConfig.from_env()


def test_config_from_env_constructs(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    assert AnthropicConfig.from_env().api_key == "sk-ant-x"


@respx.mock
def test_complete_returns_text_and_usage(client: AnthropicClient):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "hello"}],
                "model": "claude-opus-4-7",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        )
    )
    out: Completion = client.complete(
        messages=[Message(role="user", content="hi")], model="claude-opus-4-7"
    )
    assert out.text == "hello"
    assert out.usage is not None
    assert out.usage.total_tokens == 6


@respx.mock
def test_complete_extracts_system_message(client: AnthropicClient):
    """Anthropic API wants `system` as a top-level argument."""

    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "ok"}],
                "model": "claude-opus-4-7",
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )
    client.complete(
        messages=[
            Message(role="system", content="be brief"),
            Message(role="user", content="hi"),
        ],
        model="claude-opus-4-7",
    )
    payload = route.calls[0].request.read().decode()
    assert "be brief" in payload
    assert '"system":"be brief"' in payload or '"system": "be brief"' in payload


@respx.mock
def test_complete_translates_429(client: AnthropicClient):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(429, json={"error": {"message": "rate"}})
    )
    with pytest.raises(LLMRateLimitError):
        client.complete(messages=[Message(role="user", content="hi")], model="claude-opus-4-7")


@respx.mock
def test_complete_translates_500(client: AnthropicClient):
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(500, json={"error": {"message": "boom"}})
    )
    with pytest.raises(LLMServerError):
        client.complete(messages=[Message(role="user", content="hi")], model="claude-opus-4-7")


def test_embed_raises_not_implemented(client: AnthropicClient):
    with pytest.raises(NotImplementedError):
        client.embed(texts=["x"], model="any")
