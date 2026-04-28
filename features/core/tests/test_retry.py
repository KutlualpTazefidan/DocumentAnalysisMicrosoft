"""Tests for the with_retry decorator: retry on 429/5xx, no retry on
other errors, propagation after exhaustion."""

from __future__ import annotations

import pytest
from llm_clients.base import (
    LLMConfigError,
    LLMRateLimitError,
    LLMServerError,
)
from llm_clients.retry import with_retry


def _make_flaky(failure_exc: Exception, fail_count: int):
    """Return a function that fails `fail_count` times with
    `failure_exc`, then succeeds with 'ok'."""

    state = {"calls": 0}

    @with_retry
    def fn():
        state["calls"] += 1
        if state["calls"] <= fail_count:
            raise failure_exc
        return "ok"

    return fn, state


def test_succeeds_immediately_when_no_failure():
    fn, state = _make_flaky(LLMRateLimitError("rate"), fail_count=0)
    assert fn() == "ok"
    assert state["calls"] == 1


def test_retries_on_rate_limit_and_succeeds_within_budget():
    fn, state = _make_flaky(LLMRateLimitError("rate"), fail_count=2)
    assert fn() == "ok"
    assert state["calls"] == 3  # 2 failures + 1 success


def test_retries_on_server_error_and_succeeds_within_budget():
    fn, state = _make_flaky(LLMServerError("5xx"), fail_count=2)
    assert fn() == "ok"
    assert state["calls"] == 3


def test_does_not_retry_on_config_error():
    fn, state = _make_flaky(LLMConfigError("missing env"), fail_count=2)
    with pytest.raises(LLMConfigError):
        fn()
    assert state["calls"] == 1


def test_does_not_retry_on_value_error():
    """Non-LLM exceptions propagate immediately without retry."""

    state = {"calls": 0}

    @with_retry
    def fn():
        state["calls"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        fn()
    assert state["calls"] == 1


def test_propagates_last_error_after_three_attempts():
    fn, state = _make_flaky(LLMRateLimitError("rate"), fail_count=10)
    with pytest.raises(LLMRateLimitError):
        fn()
    assert state["calls"] == 3  # exactly 3 attempts, then re-raise
