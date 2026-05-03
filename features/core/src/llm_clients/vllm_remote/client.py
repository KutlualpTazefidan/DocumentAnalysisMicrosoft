"""Adapter that forwards LLMClient calls to a vLLM OpenAI-compatible server.

vLLM speaks the OpenAI chat-completions and embeddings protocols at
``{base_url}/chat/completions`` and ``{base_url}/embeddings``. We
delegate to the existing ``OpenAIDirectClient`` (which already wraps
the ``openai`` Python SDK) by translating the vLLM config to an
``OpenAIDirectConfig``. No new transport code, no duplicated retry
logic — the OpenAI client already handles both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llm_clients.openai_direct.client import OpenAIDirectClient
from llm_clients.openai_direct.config import OpenAIDirectConfig

if TYPE_CHECKING:
    from llm_clients.base import Completion, Message, ResponseFormat
    from llm_clients.vllm_remote.config import VllmRemoteConfig


class VllmRemoteClient:
    """LLMClient backed by a remote vLLM server (OpenAI-compatible API).

    Forwards ``complete`` and ``embed`` to a delegated OpenAIDirectClient.
    The config translation is trivial — vLLM exposes the same endpoints
    as OpenAI, just with a self-hosted base URL.
    """

    def __init__(self, config: VllmRemoteConfig):
        self._config = config
        self._inner = OpenAIDirectClient(
            OpenAIDirectConfig(api_key=config.api_key, base_url=config.base_url)
        )

    def complete(
        self,
        messages: list[Message],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: ResponseFormat | None = None,
    ) -> Completion:
        return self._inner.complete(
            messages,
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        result: list[list[float]] = self._inner.embed(texts, model)
        return result
