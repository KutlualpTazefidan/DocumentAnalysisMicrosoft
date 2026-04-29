"""Azure OpenAI implementation of LLMClient.

Wraps the official `openai.AzureOpenAI` client. Translates HTTP
errors into the `LLMRateLimitError` / `LLMServerError` /
`LLMConfigError` hierarchy before the retry layer sees them.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING

from openai import (
    APIError,
    APIStatusError,
    AuthenticationError,
    AzureOpenAI,
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
    from llm_clients.azure_openai.config import AzureOpenAIConfig


def _translate(exc: APIError) -> LLMConfigError | LLMRateLimitError | LLMServerError | APIError:
    """Map openai SDK errors to our exception hierarchy."""

    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, AuthenticationError):
        return LLMConfigError(str(exc))
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return LLMServerError(str(exc))
    return exc


class AzureOpenAIClient:
    def __init__(self, config: AzureOpenAIConfig):
        self._config = config
        self._client = AzureOpenAI(
            api_key=config.api_key,
            api_version=config.api_version,
            azure_endpoint=config.endpoint,
            max_retries=0,
        )

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
        kwargs: dict = {
            "model": model,
            "messages": [asdict(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = asdict(response_format)
        try:
            response = self._client.chat.completions.create(**kwargs)
        except APIError as e:
            raise _translate(e) from e
        choice = response.choices[0]
        usage = response.usage
        return Completion(
            text=choice.message.content or "",
            model=response.model,
            usage=(
                TokenUsage(
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                )
                if usage is not None
                else None
            ),
        )

    @with_retry
    def embed(self, texts: list[str], model: str) -> list[list[float]]:
        try:
            response = self._client.embeddings.create(input=texts, model=model)
        except APIError as e:
            raise _translate(e) from e
        return [list(d.embedding) for d in response.data]
