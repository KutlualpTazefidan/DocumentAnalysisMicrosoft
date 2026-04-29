# Phase A.1 — `core/llm_clients/` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `features/core/llm_clients/` — the multi-vendor LLM
abstraction with one fully-implemented backend (Azure OpenAI) and
three skeleton backends (OpenAI direct, Ollama local, Anthropic).

**Architecture:** A `LLMClient` `Protocol` exposing `complete` and
`embed`, four backend sub-packages each with their own `Config` and
`Client`, a shared `retry.py` with tenacity, and a base module with
exceptions and dataclasses. Sync only, no streaming, JSON-mode
optional. Coverage: 85 %+ across the package, with backend-specific
tiers per `docs/evaluation/coverage-thresholds.md`.

**Tech Stack:** Python 3.11+, `openai` SDK (already a dep of
retrieval), `anthropic` SDK (new), `httpx` (transitive via openai),
`tenacity` (new), pytest + responses or httpx-mock for HTTP mocking.

**Spec:** `docs/superpowers/specs/2026-04-28-a1-llm-clients-design.md`

---

## File Structure (after this plan)

```
features/core/
├── pyproject.toml
├── README.md
├── .env.example
├── src/
│   └── llm_clients/
│       ├── __init__.py
│       ├── base.py
│       ├── retry.py
│       ├── azure_openai/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── client.py
│       ├── openai_direct/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── client.py
│       ├── ollama_local/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── client.py
│       └── anthropic/
│           ├── __init__.py
│           ├── config.py
│           └── client.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_base.py
    ├── test_retry.py
    ├── test_azure_openai.py
    ├── test_openai_direct.py
    ├── test_ollama_local.py
    └── test_anthropic.py
```

Repo-level changes:

- `bootstrap.sh` — add `pip install -e features/core`
- `scripts/check_import_boundary.sh` — extend search/openai allowlist
  to include `core/llm_clients/`; add new check for `anthropic.*`
- `.env.example` files in retrieval / chunk_match / ingestion get a
  new `CHAT_DEPLOYMENT_NAME=` line for the chat deployment

---

## Task 0: Pre-flight Baseline

**Files:** None.

- [ ] **Step 1: Confirm clean tree on main**

```bash
git status
git rev-parse --abbrev-ref HEAD
```

Expected: `On branch main`, working tree clean (or only `test.ipynb`
untracked).

- [ ] **Step 2: Create the work branch**

```bash
git checkout -b feat/a1-llm-clients
```

- [ ] **Step 3: Capture baseline test/lint state**

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
.venv/bin/ruff check features/ scripts/
.venv/bin/mypy features/
```

Expected (post-Phase 0): `190 passed`, `All checks passed!`,
`Success: no issues found in 29 source files`. Record the numbers —
they are the bar for the final verification.

---

## Task 1: Package skeleton + `base.py`

**Files:**
- Create: `features/core/pyproject.toml`
- Create: `features/core/README.md`
- Create: `features/core/.env.example`
- Create: `features/core/src/llm_clients/__init__.py` (placeholder)
- Create: `features/core/src/llm_clients/base.py`
- Create: `features/core/tests/__init__.py`
- Create: `features/core/tests/conftest.py`
- Create: `features/core/tests/test_base.py`

The `__init__.py` re-exports come in Task 8; in this task it just
imports nothing (so the package loads cleanly).

- [ ] **Step 1: Create the package directory skeleton**

```bash
mkdir -p features/core/src/llm_clients/azure_openai
mkdir -p features/core/src/llm_clients/openai_direct
mkdir -p features/core/src/llm_clients/ollama_local
mkdir -p features/core/src/llm_clients/anthropic
mkdir -p features/core/tests
```

- [ ] **Step 2: Write `features/core/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "core-llm-clients"
version = "0.1.0"
description = "Multi-vendor LLM client abstraction shared across pipelines and evaluators."
requires-python = ">=3.11"
dependencies = [
    "openai>=1.40.0",
    "anthropic>=0.39.0",
    "tenacity>=9.0.0",
    "httpx>=0.28.0",
]

[project.optional-dependencies]
test = ["pytest", "pytest-cov", "respx>=0.21.0"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=src/llm_clients --cov-fail-under=85 --cov-branch --cov-report=term-missing"
```

The `respx` library mocks `httpx` at the transport layer — what the
`openai` and `anthropic` SDKs use under the hood. This lets us write
HTTP-mocked tests without touching a real network.

- [ ] **Step 3: Write `features/core/README.md`**

```markdown
# core-llm-clients

Multi-vendor LLM client abstraction. Provides a single `LLMClient`
protocol with four backend implementations: Azure OpenAI, OpenAI
direct, Ollama local, Anthropic.

In Phase A.1 only the Azure OpenAI backend is fully implemented. The
other three are protocol-conformant skeletons; they are exercised by
HTTP-mocked tests but have no integration smoke until a real consumer
needs them.

See spec: `../../docs/superpowers/specs/2026-04-28-a1-llm-clients-design.md`.
```

- [ ] **Step 4: Write `features/core/.env.example`**

```text
# Azure AI Foundry (chat completions + embeddings)
# Same vars used by features/pipelines/microsoft/retrieval/.env.example
AI_FOUNDRY_KEY=
AI_FOUNDRY_ENDPOINT=https://your-foundry.services.ai.azure.com
AZURE_OPENAI_API_VERSION=2024-02-01

# Chat-completion deployment (NEW for core/llm_clients/)
CHAT_DEPLOYMENT_NAME=gpt-4o

# Embedding deployment (already used elsewhere)
EMBEDDING_DEPLOYMENT_NAME=text-embedding-3-large

# OpenAI direct (skeleton — only used if you opt in)
OPENAI_API_KEY=

# Ollama local (skeleton)
OLLAMA_BASE_URL=http://localhost:11434

# Anthropic (skeleton)
ANTHROPIC_API_KEY=
```

- [ ] **Step 5: Write `features/core/src/llm_clients/__init__.py`** as a placeholder

```python
"""Multi-vendor LLM client abstraction. Public re-exports added in
later tasks."""
```

- [ ] **Step 6: Write `features/core/src/llm_clients/base.py`**

```python
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
```

- [ ] **Step 7: Write `features/core/tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 8: Write `features/core/tests/conftest.py`** (empty for now; HTTP mocks come in later tasks)

```python
"""Shared fixtures for llm_clients tests."""
```

- [ ] **Step 9: Write `features/core/tests/test_base.py`** (TDD: write first, then verify)

```python
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
        def complete(self, messages, model, *, temperature=0.0, max_tokens=None, response_format=None):
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
```

- [ ] **Step 10: Install the package and run tests**

```bash
.venv/bin/pip install -e features/core
.venv/bin/pytest features/core/tests -q
```

Expected: 9 tests pass, coverage on `base.py` ≥ 95 % (the protocol's
`...` body shouldn't reduce it materially because Protocol bodies are
abstract).

If coverage trips because `Protocol`'s `...` lines count as
unreachable, adjust `pyproject.toml`'s `[tool.coverage.report]` to
add `class .*\\(Protocol\\):` to `exclude_lines`.

- [ ] **Step 11: Commit**

```bash
git add features/core
git commit -m "feat(core): add llm_clients package skeleton with base types and exceptions"
```

---

## Task 2: `retry.py` — tenacity wrapper

**Files:**
- Create: `features/core/src/llm_clients/retry.py`
- Create: `features/core/tests/test_retry.py`

- [ ] **Step 1: Write `features/core/src/llm_clients/retry.py`**

```python
"""Shared retry decorator for LLM client calls.

Retries up to 3 attempts on `LLMRateLimitError` or `LLMServerError`,
with exponential backoff (1s, 2s, 4s — multiplied by jitter). Does
NOT retry on `LLMConfigError` or any other exception type.

Backends are responsible for translating their provider-specific
HTTP errors into these exceptions BEFORE the retry layer sees them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

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
    return decorated  # type: ignore[return-value]
```

- [ ] **Step 2: Write `features/core/tests/test_retry.py`**

```python
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
```

- [ ] **Step 3: Run the tests**

```bash
.venv/bin/pytest features/core/tests/test_retry.py -q
```

Expected: 6 tests pass.

- [ ] **Step 4: Run the full core suite to verify no regression**

```bash
.venv/bin/pytest features/core/tests -q
```

Expected: 9 (base) + 6 (retry) = 15 tests, all pass; coverage
threshold met.

- [ ] **Step 5: Commit**

```bash
git add features/core/src/llm_clients/retry.py features/core/tests/test_retry.py
git commit -m "feat(core): add tenacity-based retry wrapper for LLM client calls"
```

---

## Task 3: Azure OpenAI backend (full implementation)

**Files:**
- Create: `features/core/src/llm_clients/azure_openai/__init__.py`
- Create: `features/core/src/llm_clients/azure_openai/config.py`
- Create: `features/core/src/llm_clients/azure_openai/client.py`
- Create: `features/core/tests/test_azure_openai.py`

The Azure OpenAI client is the canonical reference implementation.
The other three backends in Tasks 4-6 mirror its shape.

- [ ] **Step 1: Write `features/core/src/llm_clients/azure_openai/config.py`**

```python
"""Environment-driven config for the Azure OpenAI backend."""

from __future__ import annotations

import os
from dataclasses import dataclass

from llm_clients.base import LLMConfigError

_REQUIRED: tuple[str, ...] = (
    "AI_FOUNDRY_KEY",
    "AI_FOUNDRY_ENDPOINT",
    "AZURE_OPENAI_API_VERSION",
    "CHAT_DEPLOYMENT_NAME",
    "EMBEDDING_DEPLOYMENT_NAME",
)


@dataclass(frozen=True)
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    api_version: str
    chat_deployment_name: str
    embedding_deployment_name: str

    @classmethod
    def from_env(cls) -> AzureOpenAIConfig:
        missing = [v for v in _REQUIRED if v not in os.environ]
        if missing:
            raise LLMConfigError(
                f"Missing required env vars for AzureOpenAIConfig: {', '.join(missing)}"
            )
        return cls(
            endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
            api_key=os.environ["AI_FOUNDRY_KEY"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            chat_deployment_name=os.environ["CHAT_DEPLOYMENT_NAME"],
            embedding_deployment_name=os.environ["EMBEDDING_DEPLOYMENT_NAME"],
        )
```

- [ ] **Step 2: Write `features/core/src/llm_clients/azure_openai/client.py`**

```python
"""Azure OpenAI implementation of LLMClient.

Wraps the official `openai.AzureOpenAI` client. Translates HTTP
errors into the `LLMRateLimitError` / `LLMServerError` /
`LLMConfigError` hierarchy before the retry layer sees them.
"""

from __future__ import annotations

from dataclasses import asdict

from openai import (
    APIError,
    APIStatusError,
    AuthenticationError,
    AzureOpenAI,
    RateLimitError,
)

from llm_clients.azure_openai.config import AzureOpenAIConfig
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


def _translate(exc: APIError) -> Exception:
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
```

- [ ] **Step 3: Write `features/core/src/llm_clients/azure_openai/__init__.py`**

```python
from llm_clients.azure_openai.client import AzureOpenAIClient
from llm_clients.azure_openai.config import AzureOpenAIConfig

__all__ = ["AzureOpenAIClient", "AzureOpenAIConfig"]
```

- [ ] **Step 4: Write `features/core/tests/test_azure_openai.py`**

```python
"""Tests for the Azure OpenAI backend.

HTTP responses are mocked at the httpx transport layer with `respx`.
The openai SDK uses httpx underneath, so respx routes intercept the
real HTTP calls without us mocking the SDK directly.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from llm_clients.azure_openai import AzureOpenAIClient, AzureOpenAIConfig
from llm_clients.base import (
    Completion,
    LLMConfigError,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
)


@pytest.fixture
def cfg() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        endpoint="https://test-foundry.services.ai.azure.com",
        api_key="test-key",
        api_version="2024-02-01",
        chat_deployment_name="gpt-4o",
        embedding_deployment_name="text-embedding-3-large",
    )


@pytest.fixture
def client(cfg: AzureOpenAIConfig) -> AzureOpenAIClient:
    return AzureOpenAIClient(cfg)


def test_config_from_env_raises_when_required_var_missing(monkeypatch):
    for v in (
        "AI_FOUNDRY_KEY",
        "AI_FOUNDRY_ENDPOINT",
        "AZURE_OPENAI_API_VERSION",
        "CHAT_DEPLOYMENT_NAME",
        "EMBEDDING_DEPLOYMENT_NAME",
    ):
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(LLMConfigError, match="Missing"):
        AzureOpenAIConfig.from_env()


def test_config_from_env_constructs_when_all_set(monkeypatch):
    monkeypatch.setenv("AI_FOUNDRY_KEY", "k")
    monkeypatch.setenv("AI_FOUNDRY_ENDPOINT", "https://e.example")
    monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    monkeypatch.setenv("CHAT_DEPLOYMENT_NAME", "gpt-4o")
    monkeypatch.setenv("EMBEDDING_DEPLOYMENT_NAME", "text-embedding-3-large")
    cfg = AzureOpenAIConfig.from_env()
    assert cfg.api_key == "k"
    assert cfg.chat_deployment_name == "gpt-4o"


@respx.mock
def test_complete_returns_text_and_usage(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(
        return_value=Response(
            200,
            json={
                "id": "abc",
                "object": "chat.completion",
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            },
        )
    )
    out: Completion = client.complete(
        messages=[Message(role="user", content="hi")],
        model="gpt-4o",
    )
    assert out.text == "hello"
    assert out.model == "gpt-4o-2024-08-06"
    assert out.usage is not None
    assert out.usage.total_tokens == 6


@respx.mock
def test_complete_passes_response_format_when_set(client: AzureOpenAIClient):
    route = respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(
        return_value=Response(
            200,
            json={
                "id": "abc",
                "object": "chat.completion",
                "model": "gpt-4o",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    client.complete(
        messages=[Message(role="user", content="hi")],
        model="gpt-4o",
        response_format=ResponseFormat(type="json_object"),
    )
    payload = route.calls[0].request.read().decode()
    assert "json_object" in payload


@respx.mock
def test_complete_translates_429_to_rate_limit_error(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(return_value=Response(429, json={"error": {"message": "rate"}}))
    with pytest.raises(LLMRateLimitError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_complete_translates_500_to_server_error(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(return_value=Response(500, json={"error": {"message": "boom"}}))
    with pytest.raises(LLMServerError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_complete_translates_401_to_config_error(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"
    ).mock(return_value=Response(401, json={"error": {"message": "auth"}}))
    with pytest.raises(LLMConfigError):
        client.complete(messages=[Message(role="user", content="hi")], model="gpt-4o")


@respx.mock
def test_embed_returns_vectors(client: AzureOpenAIClient):
    respx.post(
        "https://test-foundry.services.ai.azure.com/openai/deployments/text-embedding-3-large/embeddings"
    ).mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"object": "embedding", "index": 0, "embedding": [0.1, 0.2, 0.3]},
                    {"object": "embedding", "index": 1, "embedding": [0.4, 0.5, 0.6]},
                ],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )
    )
    vectors = client.embed(texts=["a", "b"], model="text-embedding-3-large")
    assert len(vectors) == 2
    assert vectors[0] == [0.1, 0.2, 0.3]
```

- [ ] **Step 5: Run the tests**

```bash
.venv/bin/pytest features/core/tests/test_azure_openai.py -q
```

Expected: 8 tests pass; backend coverage ≥ 90 %.

If `respx` is not yet installed, install it explicitly:

```bash
.venv/bin/pip install "respx>=0.21.0"
```

(It is also listed in `pyproject.toml`'s test extras and would come
in via `pip install -e features/core[test]`.)

- [ ] **Step 6: Commit**

```bash
git add features/core/src/llm_clients/azure_openai features/core/tests/test_azure_openai.py
git commit -m "feat(core): add AzureOpenAIClient with full chat-completion and embedding support"
```

---

## Task 4: OpenAI direct backend (skeleton)

**Files:**
- Create: `features/core/src/llm_clients/openai_direct/__init__.py`
- Create: `features/core/src/llm_clients/openai_direct/config.py`
- Create: `features/core/src/llm_clients/openai_direct/client.py`
- Create: `features/core/tests/test_openai_direct.py`

This is a skeleton: the protocol is implemented, the HTTP path is
correct, and there are mocked tests proving the happy path. There is
no integration smoke against the real `api.openai.com` because no
consumer needs it yet.

- [ ] **Step 1: Write `config.py`**

```python
"""Environment-driven config for the OpenAI direct backend (skeleton)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from llm_clients.base import LLMConfigError


@dataclass(frozen=True)
class OpenAIDirectConfig:
    api_key: str
    base_url: str

    @classmethod
    def from_env(cls) -> OpenAIDirectConfig:
        if "OPENAI_API_KEY" not in os.environ:
            raise LLMConfigError("Missing required env var: OPENAI_API_KEY")
        return cls(
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
```

- [ ] **Step 2: Write `client.py`**

```python
"""OpenAI direct implementation of LLMClient (skeleton).

Same shape as `AzureOpenAIClient` — but uses the public OpenAI
endpoint, no `api_version`, no deployment name.
"""

from __future__ import annotations

from dataclasses import asdict

from openai import (
    APIError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
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
from llm_clients.openai_direct.config import OpenAIDirectConfig
from llm_clients.retry import with_retry


def _translate(exc: APIError) -> Exception:
    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, AuthenticationError):
        return LLMConfigError(str(exc))
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return LLMServerError(str(exc))
    return exc


class OpenAIDirectClient:
    def __init__(self, config: OpenAIDirectConfig):
        self._config = config
        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)

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
```

- [ ] **Step 3: Write `__init__.py`**

```python
from llm_clients.openai_direct.client import OpenAIDirectClient
from llm_clients.openai_direct.config import OpenAIDirectConfig

__all__ = ["OpenAIDirectClient", "OpenAIDirectConfig"]
```

- [ ] **Step 4: Write `tests/test_openai_direct.py`**

```python
"""Skeleton tests for the OpenAI direct backend.

Covers config + happy-path complete + happy-path embed. Error
translation is identical to AzureOpenAIClient and is exercised
there; we don't duplicate the full error matrix here.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from llm_clients.base import Completion, LLMConfigError, Message
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig


@pytest.fixture
def cfg() -> OpenAIDirectConfig:
    return OpenAIDirectConfig(api_key="sk-test", base_url="https://api.openai.com/v1")


@pytest.fixture
def client(cfg: OpenAIDirectConfig) -> OpenAIDirectClient:
    return OpenAIDirectClient(cfg)


def test_config_from_env_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        OpenAIDirectConfig.from_env()


def test_config_from_env_uses_default_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    cfg = OpenAIDirectConfig.from_env()
    assert cfg.base_url == "https://api.openai.com/v1"


@respx.mock
def test_complete_happy_path(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "id": "abc",
                "object": "chat.completion",
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )
    out: Completion = client.complete(
        messages=[Message(role="user", content="hi")], model="gpt-4o"
    )
    assert out.text == "hi"


@respx.mock
def test_embed_happy_path(client: OpenAIDirectClient):
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "object": "list",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                "model": "text-embedding-3-large",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )
    )
    out = client.embed(texts=["x"], model="text-embedding-3-large")
    assert out == [[0.1, 0.2]]
```

- [ ] **Step 5: Run, then commit**

```bash
.venv/bin/pytest features/core/tests/test_openai_direct.py -q
git add features/core/src/llm_clients/openai_direct features/core/tests/test_openai_direct.py
git commit -m "feat(core): add OpenAIDirectClient skeleton (protocol-conformant, mocked tests)"
```

Expected: 4 tests pass.

---

## Task 5: Ollama local backend (skeleton)

**Files:**
- Create: `features/core/src/llm_clients/ollama_local/__init__.py`
- Create: `features/core/src/llm_clients/ollama_local/config.py`
- Create: `features/core/src/llm_clients/ollama_local/client.py`
- Create: `features/core/tests/test_ollama_local.py`

Uses Ollama's native HTTP API (`/api/chat`, `/api/embeddings`).
Users wanting OpenAI-compatible behaviour can use
`OpenAIDirectClient` pointed at `http://localhost:11434/v1` instead.

- [ ] **Step 1: Write `config.py`**

```python
"""Environment-driven config for Ollama local backend (skeleton)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaLocalConfig:
    base_url: str

    @classmethod
    def from_env(cls) -> OllamaLocalConfig:
        return cls(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
```

(No required env vars — Ollama default is the localhost URL. No
auth needed for local Ollama.)

- [ ] **Step 2: Write `client.py`**

```python
"""Ollama local implementation of LLMClient (skeleton).

Uses Ollama's native HTTP API. Token usage is NOT reported by
Ollama in the responses we use, so `Completion.usage` is always None.
"""

from __future__ import annotations

import httpx

from llm_clients.base import (
    Completion,
    LLMRateLimitError,
    LLMServerError,
    Message,
    ResponseFormat,
)
from llm_clients.ollama_local.config import OllamaLocalConfig
from llm_clients.retry import with_retry


def _translate_status(response: httpx.Response) -> Exception | None:
    if response.status_code == 429:
        return LLMRateLimitError(response.text)
    if response.status_code >= 500:
        return LLMServerError(response.text)
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
            response = self._http.post(
                "/api/embeddings", json={"model": model, "prompt": t}
            )
            translated = _translate_status(response)
            if translated is not None:
                raise translated
            response.raise_for_status()
            out.append(list(response.json()["embedding"]))
        return out
```

(Ollama's `/api/embeddings` is one-text-per-call; we loop. This is
fine for the skeleton; if a consumer needs batching we can revisit.)

- [ ] **Step 3: Write `__init__.py`**

```python
from llm_clients.ollama_local.client import OllamaLocalClient
from llm_clients.ollama_local.config import OllamaLocalConfig

__all__ = ["OllamaLocalClient", "OllamaLocalConfig"]
```

- [ ] **Step 4: Write `tests/test_ollama_local.py`**

```python
"""Skeleton tests for Ollama local backend."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from llm_clients.base import Completion, LLMRateLimitError, Message
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


@respx.mock
def test_complete_returns_text_no_usage(client: OllamaLocalClient):
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=Response(200, json={"model": "llama3", "message": {"role": "assistant", "content": "hi"}})
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
def test_embed_loops_per_text(client: OllamaLocalClient):
    respx.post("http://localhost:11434/api/embeddings").mock(
        side_effect=[
            Response(200, json={"embedding": [0.1, 0.2]}),
            Response(200, json={"embedding": [0.3, 0.4]}),
        ]
    )
    out = client.embed(texts=["a", "b"], model="nomic-embed-text")
    assert out == [[0.1, 0.2], [0.3, 0.4]]
```

- [ ] **Step 5: Run, then commit**

```bash
.venv/bin/pytest features/core/tests/test_ollama_local.py -q
git add features/core/src/llm_clients/ollama_local features/core/tests/test_ollama_local.py
git commit -m "feat(core): add OllamaLocalClient skeleton (native API, no usage reporting)"
```

Expected: 4 tests pass.

---

## Task 6: Anthropic backend (skeleton)

**Files:**
- Create: `features/core/src/llm_clients/anthropic/__init__.py`
- Create: `features/core/src/llm_clients/anthropic/config.py`
- Create: `features/core/src/llm_clients/anthropic/client.py`
- Create: `features/core/tests/test_anthropic.py`

Uses the official `anthropic` SDK. Anthropic does NOT provide
embeddings via this SDK — `embed()` raises `NotImplementedError` to
make the limitation explicit at runtime. (Consumers can still satisfy
the protocol because raising is part of the protocol's contract for
unsupported operations; we document this in the docstring.)

- [ ] **Step 1: Write `config.py`**

```python
"""Environment-driven config for the Anthropic backend (skeleton)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from llm_clients.base import LLMConfigError


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str

    @classmethod
    def from_env(cls) -> AnthropicConfig:
        if "ANTHROPIC_API_KEY" not in os.environ:
            raise LLMConfigError("Missing required env var: ANTHROPIC_API_KEY")
        return cls(api_key=os.environ["ANTHROPIC_API_KEY"])
```

- [ ] **Step 2: Write `client.py`**

```python
"""Anthropic implementation of LLMClient (skeleton).

`embed()` raises NotImplementedError — Anthropic does not provide
embeddings via this SDK.
"""

from __future__ import annotations

from anthropic import (
    Anthropic,
    APIError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from llm_clients.anthropic.config import AnthropicConfig
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


def _translate(exc: APIError) -> Exception:
    if isinstance(exc, RateLimitError):
        return LLMRateLimitError(str(exc))
    if isinstance(exc, AuthenticationError):
        return LLMConfigError(str(exc))
    if isinstance(exc, APIStatusError) and exc.status_code >= 500:
        return LLMServerError(str(exc))
    return exc


def _split_system(messages: list[Message]) -> tuple[str | None, list[dict]]:
    """Anthropic's API takes the system prompt as a top-level argument,
    not as a message. Pull any system messages out and concatenate them."""

    system_parts = [m.content for m in messages if m.role == "system"]
    rest = [
        {"role": m.role, "content": m.content} for m in messages if m.role != "system"
    ]
    return ("\n".join(system_parts) if system_parts else None), rest


class AnthropicClient:
    def __init__(self, config: AnthropicConfig):
        self._config = config
        self._client = Anthropic(api_key=config.api_key)

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
        raise NotImplementedError(
            "Anthropic does not provide an embeddings API in this SDK."
        )
```

- [ ] **Step 3: Write `__init__.py`**

```python
from llm_clients.anthropic.client import AnthropicClient
from llm_clients.anthropic.config import AnthropicConfig

__all__ = ["AnthropicClient", "AnthropicConfig"]
```

- [ ] **Step 4: Write `tests/test_anthropic.py`**

```python
"""Skeleton tests for the Anthropic backend."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from llm_clients.anthropic import AnthropicClient, AnthropicConfig
from llm_clients.base import Completion, LLMConfigError, Message


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
    # The system content should appear in the system field, not in messages.
    assert '"system":"be brief"' in payload or '"system": "be brief"' in payload


def test_embed_raises_not_implemented(client: AnthropicClient):
    with pytest.raises(NotImplementedError):
        client.embed(texts=["x"], model="any")
```

- [ ] **Step 5: Run, then commit**

```bash
.venv/bin/pytest features/core/tests/test_anthropic.py -q
git add features/core/src/llm_clients/anthropic features/core/tests/test_anthropic.py
git commit -m "feat(core): add AnthropicClient skeleton (chat only, no embeddings)"
```

Expected: 4 tests pass.

---

## Task 7: Wire it all up — public API, boundary check, bootstrap, Makefile

**Files:**
- Modify: `features/core/src/llm_clients/__init__.py`
- Modify: `bootstrap.sh`
- Modify: `scripts/check_import_boundary.sh`
- Modify: `.pre-commit-config.yaml` (the hook's display name)
- Modify: `features/pipelines/microsoft/retrieval/.env.example` (add CHAT_DEPLOYMENT_NAME)
- Modify: `features/pipelines/microsoft/ingestion/.env.example` (add CHAT_DEPLOYMENT_NAME)
- Modify: `features/evaluators/chunk_match/.env.example` (add CHAT_DEPLOYMENT_NAME)

- [ ] **Step 1: Replace `features/core/src/llm_clients/__init__.py`**

```python
"""Multi-vendor LLM client abstraction.

See `docs/superpowers/specs/2026-04-28-a1-llm-clients-design.md`.
"""

from llm_clients.anthropic import AnthropicClient, AnthropicConfig
from llm_clients.azure_openai import AzureOpenAIClient, AzureOpenAIConfig
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
from llm_clients.ollama_local import OllamaLocalClient, OllamaLocalConfig
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig

__all__ = [
    "AnthropicClient",
    "AnthropicConfig",
    "AzureOpenAIClient",
    "AzureOpenAIConfig",
    "Completion",
    "LLMClient",
    "LLMConfigError",
    "LLMError",
    "LLMRateLimitError",
    "LLMServerError",
    "Message",
    "OllamaLocalClient",
    "OllamaLocalConfig",
    "OpenAIDirectClient",
    "OpenAIDirectConfig",
    "ResponseFormat",
    "TokenUsage",
]
```

- [ ] **Step 2: Update `bootstrap.sh`** — add `core` install BEFORE the others (others may depend on it later)

Add these lines after `pip install -r requirements-dev.txt` (around
line 13), before the existing `if [ -f features/pipelines/...` block:

```bash
if [ -f features/core/pyproject.toml ]; then
    pip install -e features/core
fi
```

- [ ] **Step 3: Update `scripts/check_import_boundary.sh`**

Change line 28 from:

```bash
    | grep -v '^features/pipelines/microsoft/retrieval/' \
```

to:

```bash
    | grep -v -E '^features/(pipelines/microsoft/retrieval|core/llm_clients)/' \
```

Update the corresponding header comment block (lines 2–7) to mention
the new path. Also update the error message at line ~32 accordingly.

Add a new check 3 at the bottom of the file (just before
`exit 0`):

```bash
# --- Check 3: anthropic imports — only core/llm_clients ---
violations_anthropic="$(grep -rEn '[[:space:]]*(import|from)[[:space:]]+anthropic([.[:space:]]|$)' \
    --include='*.py' \
    features/ \
    | grep -v '^features/core/llm_clients/' \
    || true)"

if [ -n "$violations_anthropic" ]; then
    echo "BOUNDARY VIOLATION: anthropic.* imports are only allowed inside features/core/llm_clients/"
    echo "$violations_anthropic"
    exit 1
fi
```

- [ ] **Step 4: Update `.pre-commit-config.yaml`** — refresh the hook display name

Replace:

```yaml
        name: Restrict azure/openai imports to features/pipelines/microsoft/{retrieval,ingestion}
```

with:

```yaml
        name: Restrict azure/openai/anthropic imports per per-package boundary
```

- [ ] **Step 5: Update each `.env.example`** in retrieval / ingestion / chunk_match

Add this line at the bottom of each:

```text
CHAT_DEPLOYMENT_NAME=gpt-4o
```

- [ ] **Step 6: Reinstall everything cleanly**

```bash
.venv/bin/pip uninstall -y core-llm-clients query-index ingestion query-index-eval || true
bash bootstrap.sh
```

Expected: bootstrap completes, all four packages install
successfully (`core-llm-clients`, `query-index`, `query-index-eval`,
`ingestion`).

- [ ] **Step 7: Run boundary check**

```bash
.venv/bin/pre-commit run --all-files
```

Expected: all hooks pass.

- [ ] **Step 8: Run full suite**

```bash
.venv/bin/pytest features/ -q
```

Expected: 190 (Phase 0 baseline) + 33 (this plan: 9 base + 6 retry + 8 azure_openai + 4 openai_direct + 4 ollama_local + 4 anthropic) = 223 tests pass. The exact number may vary slightly with parametrisation but should be ~223.

- [ ] **Step 9: Commit**

```bash
git add features/core/src/llm_clients/__init__.py \
        bootstrap.sh scripts/check_import_boundary.sh .pre-commit-config.yaml \
        features/pipelines/microsoft/retrieval/.env.example \
        features/pipelines/microsoft/ingestion/.env.example \
        features/evaluators/chunk_match/.env.example
git commit -m "feat(core): expose llm_clients public API; wire bootstrap, boundary, env templates"
```

---

## Task 8: Final Verification

- [ ] **Step 1: Full suite green**

```bash
.venv/bin/pytest features/ -q 2>&1 | tail -3
```

Expected: pass count ~223 (190 baseline + ~33 new). No failures, no
errors.

- [ ] **Step 2: Lint clean**

```bash
.venv/bin/ruff check features/ scripts/
.venv/bin/mypy features/
```

Expected: both clean.

- [ ] **Step 3: Pre-commit on all files**

```bash
.venv/bin/pre-commit run --all-files
```

Expected: all four hooks pass.

- [ ] **Step 4: Coverage report for the new package**

```bash
.venv/bin/pytest features/core/tests --cov-report=term
```

Expected coverage:
- `base.py` ≥ 95 %
- `retry.py` ≥ 95 %
- `azure_openai/*` ≥ 90 %
- `openai_direct/*`, `ollama_local/*`, `anthropic/*` ≥ 70 % each
- Package total ≥ 85 % (per `pyproject.toml`'s `--cov-fail-under=85`)

If any is below threshold, fix the gap (typically by adding a small
test) before proceeding.

- [ ] **Step 5: Review the commit history**

```bash
git log --oneline main..HEAD
```

Expected: 8 commits, in order:

1. `feat(core): add llm_clients package skeleton with base types and exceptions`
2. `feat(core): add tenacity-based retry wrapper for LLM client calls`
3. `feat(core): add AzureOpenAIClient with full chat-completion and embedding support`
4. `feat(core): add OpenAIDirectClient skeleton (protocol-conformant, mocked tests)`
5. `feat(core): add OllamaLocalClient skeleton (native API, no usage reporting)`
6. `feat(core): add AnthropicClient skeleton (chat only, no embeddings)`
7. `feat(core): expose llm_clients public API; wire bootstrap, boundary, env templates`

(Note: 7, not 8 — the final-verification task does not commit.)

- [ ] **Step 6: Push and open PR (only after explicit user approval)**

```bash
git push -u origin feat/a1-llm-clients
gh pr create --title "Phase A.1: core/llm_clients/ — multi-vendor LLM abstraction" \
  --body "$(cat <<'EOF'
## Summary

Phase A.1 of the goldens restructure: build the `core/llm_clients/`
package per
`docs/superpowers/specs/2026-04-28-a1-llm-clients-design.md`.

- `LLMClient` protocol with `complete` and `embed`
- Four backends: Azure OpenAI (full), OpenAI direct, Ollama local,
  Anthropic (skeletons)
- Tenacity-based retry with 3 attempts, exponential backoff
- Three shared exceptions: `LLMRateLimitError`, `LLMServerError`,
  `LLMConfigError`
- Sync only, no streaming, JSON-mode optional, post-call usage
  logging where the backend reports it

## Test plan

- [x] `pytest features/` — ~223 tests pass (190 baseline + ~33 new)
- [x] Coverage ≥ 85 % on new package; per-module thresholds met
- [x] `ruff check`, `mypy` — clean
- [x] `pre-commit run --all-files` — all four hooks pass (incl. new
      Anthropic boundary check)
- [x] `bash bootstrap.sh` installs all four packages cleanly

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**Pause here for user instruction before pushing or creating the PR.**

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| §3 Package layout | Tasks 1, 4, 5, 6 (sub-package creation) |
| §4 Protocol & types | Task 1 (base.py) |
| §5 Exceptions | Task 1 (base.py) + Task 7 (re-export) |
| §6 Retry policy | Task 2 (retry.py) |
| §7 Configuration | Tasks 3, 4, 5, 6 (per-backend Config) |
| §8 Public API | Task 7 (Step 1) |
| §9 Testing strategy | Tests across Tasks 1–6 + Task 8 verification |
| §10 Boundary check additions | Task 7 (Step 3) |

**Placeholder scan:** No `TBD`/`TODO`. Each step has full code or
exact commands. The PR creation is gated on explicit user approval.

**Type-consistency check:** `LLMClient`, `Message`, `Completion`,
`TokenUsage`, `ResponseFormat`, exceptions — all defined in Task 1
and reused unchanged across Tasks 2–7. Backend-specific
`*Client` / `*Config` pairs are introduced in their respective tasks
and re-exported in Task 7.

**Scope check:** Self-contained — produces a working
`core/llm_clients/` package. Phase A.2 (`goldens/schemas/`) is the
next plan.
