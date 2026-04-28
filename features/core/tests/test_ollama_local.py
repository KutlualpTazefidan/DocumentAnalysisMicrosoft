"""Skeleton tests for Ollama local backend."""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from llm_clients.base import Completion, LLMRateLimitError, LLMServerError, Message
from llm_clients.ollama_local import OllamaLocalClient, OllamaLocalConfig


@pytest.fixture
def cfg() -> OllamaLocalConfig:
    return OllamaLocalConfig(base_url="http://localhost:11434")


@pytest.fixture
def client(cfg: OllamaLocalConfig) -> OllamaLocalClient:
    return OllamaLocalClient(cfg)


def test_config_from_env_uses_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    cfg = OllamaLocalConfig.from_env()
    assert cfg.base_url == "http://localhost:11434"


def test_config_from_env_respects_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://my-ollama:9999")
    cfg = OllamaLocalConfig.from_env()
    assert cfg.base_url == "http://my-ollama:9999"


@respx.mock
def test_complete_returns_text_no_usage(client: OllamaLocalClient):
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=Response(
            200, json={"model": "llama3", "message": {"role": "assistant", "content": "hi"}}
        )
    )
    out: Completion = client.complete(messages=[Message(role="user", content="hi")], model="llama3")
    assert out.text == "hi"
    assert out.usage is None


@respx.mock
def test_complete_translates_429(client: OllamaLocalClient):
    respx.post("http://localhost:11434/api/chat").mock(return_value=Response(429, text="busy"))
    with pytest.raises(LLMRateLimitError):
        client.complete(messages=[Message(role="user", content="hi")], model="llama3")


@respx.mock
def test_complete_translates_500(client: OllamaLocalClient):
    respx.post("http://localhost:11434/api/chat").mock(return_value=Response(500, text="boom"))
    with pytest.raises(LLMServerError):
        client.complete(messages=[Message(role="user", content="hi")], model="llama3")


@respx.mock
def test_embed_loops_per_text(client: OllamaLocalClient):
    respx.post("http://localhost:11434/api/embeddings").mock(
        side_effect=[
            Response(200, json={"embedding": [0.1, 0.2]}),
            Response(200, json={"embedding": [0.3, 0.4]}),
        ]
    )
    out = client.embed(texts=["a", "b"], model="nomic-embed-text")
    assert out == [[0.1, 0.2], [0.3, 0.4]]
