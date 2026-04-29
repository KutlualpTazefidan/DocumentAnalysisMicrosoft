"""Tests for llm_clients.base — dataclasses, Protocol, exception hierarchy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from llm_clients.base import (
    Completion,
    LLMClient,
    LLMConfigError,
    LLMError,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
    TokenUsage,
)


def test_message_holds_role_and_content():
    m = Message(role="user", content="hi")
    assert m.role == "user"
    assert m.content == "hi"


def test_message_is_frozen():
    m = Message(role="user", content="hi")
    with pytest.raises(FrozenInstanceError):
        m.content = "changed"  # type: ignore[misc]


def test_response_format_accepts_text_and_json_object():
    assert ResponseFormat(type="text").type == "text"
    assert ResponseFormat(type="json_object").type == "json_object"


def test_token_usage_holds_three_int_fields():
    u = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    assert u.total_tokens == 15


def test_completion_can_have_no_usage():
    c = Completion(text="ok", model="gpt-4o", usage=None)
    assert c.usage is None


def test_completion_with_usage():
    c = Completion(
        text="ok",
        model="gpt-4o",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    assert c.usage is not None
    assert c.usage.total_tokens == 2


def test_llm_client_is_a_protocol():
    """A class that defines complete + embed with matching signatures
    is structurally a LLMClient."""

    class Dummy:
        def complete(
            self, messages, model, *, temperature=0.0, max_tokens=None, response_format=None
        ):
            return Completion(text="", model=model, usage=None)

        def embed(self, texts, model):
            return [[0.0] for _ in texts]

    d: LLMClient = Dummy()  # type-checker enforced
    assert d.complete(messages=[], model="m").text == ""
    assert d.embed(texts=["x"], model="m") == [[0.0]]


def test_exception_hierarchy():
    assert issubclass(LLMRateLimitError, LLMError)
    assert issubclass(LLMServerError, LLMError)
    assert issubclass(LLMConfigError, LLMError)
    assert issubclass(LLMError, Exception)
