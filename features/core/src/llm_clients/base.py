"""Protocol, dataclasses, and exception hierarchy for LLM clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ResponseFormat:
    """Hint to the backend about response shape. v1 supports only
    plain text and JSON-mode."""

    type: Literal["text", "json_object"]


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: TokenUsage | None


class LLMClient(Protocol):
    def complete(
        self,
        messages: list[Message],
        model: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: ResponseFormat | None = None,
    ) -> Completion: ...

    def embed(
        self,
        texts: list[str],
        model: str,
    ) -> list[list[float]]: ...


class LLMError(Exception):
    """Base for all llm_clients errors."""


class LLMRateLimitError(LLMError):
    """Provider returned 429."""


class LLMServerError(LLMError):
    """Provider returned 5xx."""


class LLMConfigError(LLMError):
    """Auth, missing env var, or other setup-time failure."""
