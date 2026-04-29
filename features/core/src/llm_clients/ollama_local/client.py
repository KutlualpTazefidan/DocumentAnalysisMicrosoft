"""Ollama local implementation of LLMClient (skeleton).

Uses Ollama's native HTTP API. Token usage is NOT reported by
Ollama in the responses we use, so `Completion.usage` is always None.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import httpx

from llm_clients.base import (
    Completion,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
)
from llm_clients.retry import with_retry

if TYPE_CHECKING:
    from llm_clients.ollama_local.config import OllamaLocalConfig


def _translate_status(response: httpx.Response) -> Exception | None:
    if response.status_code == 429:
        return cast("Exception", LLMRateLimitError(response.text))
    if response.status_code >= 500:
        return cast("Exception", LLMServerError(response.text))
    return None


class OllamaLocalClient:
    def __init__(self, config: OllamaLocalConfig):
        self._config = config
        self._http = httpx.Client(base_url=config.base_url, timeout=60.0)

    @with_retry
    def complete(
        self,
        messages: list[Message],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: ResponseFormat | None = None,
    ) -> Completion:
        payload: dict = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens
        if response_format is not None and response_format.type == "json_object":
            payload["format"] = "json"
        response = self._http.post("/api/chat", json=payload)
        translated = _translate_status(response)
        if translated is not None:
            raise translated
        response.raise_for_status()
        body = response.json()
        return Completion(
            text=body["message"]["content"],
            model=body.get("model", model),
            usage=None,
        )

    @with_retry
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            response = self._http.post("/api/embeddings", json={"model": model, "prompt": t})
            translated = _translate_status(response)
            if translated is not None:
                raise translated
            response.raise_for_status()
            out.append(list(response.json()["embedding"]))
        return out
