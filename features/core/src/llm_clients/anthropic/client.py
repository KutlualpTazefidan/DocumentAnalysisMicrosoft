"""Anthropic implementation of LLMClient (skeleton).

`embed()` raises NotImplementedError — Anthropic does not provide
embeddings via this SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from anthropic import (
    Anthropic,
    APIError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from llm_clients.base import (
    Completion,
    LLMConfigError,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
    TokenUsage,
)
from llm_clients.retry import with_retry

if TYPE_CHECKING:
    from llm_clients.anthropic.config import AnthropicConfig


def _translate(exc: APIError) -> Exception:
    if isinstance(exc, RateLimitError):
        return cast("Exception", LLMRateLimitError(str(exc)))
    if isinstance(exc, AuthenticationError):
        return cast("Exception", LLMConfigError(str(exc)))
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return cast("Exception", LLMServerError(str(exc)))
    return cast("Exception", exc)


def _split_system(messages: list[Message]) -> tuple[str | None, list[dict]]:
    """Anthropic's API takes the system prompt as a top-level argument,
    not as a message. Pull any system messages out and concatenate them."""

    system_parts = [m.content for m in messages if m.role == "system"]
    rest = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return ("\n".join(system_parts) if system_parts else None), rest


class AnthropicClient:
    def __init__(self, config: AnthropicConfig):
        self._config = config
        self._client = Anthropic(api_key=config.api_key, max_retries=0)

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
        system, rest = _split_system(messages)
        kwargs: dict = {
            "model": model,
            "messages": rest,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,  # Anthropic requires max_tokens
        }
        if system is not None:
            kwargs["system"] = system
        # response_format is silently ignored — Anthropic uses tool_choice
        # for structured output, deferred to first consumer that needs it.
        try:
            response = self._client.messages.create(**kwargs)
        except APIError as e:
            raise _translate(e) from e
        text = "".join(b.text for b in response.content if b.type == "text")
        return Completion(
            text=text,
            model=response.model,
            usage=TokenUsage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
        )

    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        raise NotImplementedError("Anthropic does not provide an embeddings API in this SDK.")
