"""Shared retry decorator for LLM client calls.

Retries up to 3 attempts on `LLMRateLimitError` or `LLMServerError`,
with exponential backoff (1s, 2s, 4s — multiplied by jitter). Does
NOT retry on `LLMConfigError` or any other exception type.

Backends are responsible for translating their provider-specific
HTTP errors into these exceptions BEFORE the retry layer sees them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from llm_clients.base import LLMRateLimitError, LLMServerError

F = TypeVar("F", bound=Callable[..., object])


def with_retry(fn: F) -> F:
    """Wrap a method so that retryable LLM errors trigger up to 3 attempts."""

    decorated = retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=10.0),
        retry=retry_if_exception_type((LLMRateLimitError, LLMServerError)),
        reraise=True,
    )(fn)
    return cast("F", decorated)
