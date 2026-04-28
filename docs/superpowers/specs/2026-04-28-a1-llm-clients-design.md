# Phase A.1 — `core/llm_clients/` Design Spec

**Status:** Draft for review
**Date:** 2026-04-28
**Parent spec:** `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§3 layer `core/`, §7 Phase A.1)

---

## 1. Scope

Build the `core/llm_clients/` package — the multi-vendor LLM abstraction
that downstream layers (`goldens/creation/synthetic.py`,
`evaluators/llm_judge/`, future Phase A.5 HTTP API) will depend on.

This spec captures the eight design decisions agreed during the A.1
brainstorming session on 2026-04-28. The parent spec (§3) defines
`core/` as the fourth architectural layer; this fragment fills in the
package's internal shape.

## 2. Goals & Non-Goals

### Goals

- A single `LLMClient` `Protocol` exposing `complete` and `embed`.
- Four backend skeletons: Azure OpenAI, OpenAI direct, Ollama local,
  Anthropic. **Only Azure OpenAI is fully functional in A.1**; the
  other three implement the protocol but their integration smokes are
  deferred until first real use.
- Per-backend `Config` dataclasses loaded from env via `from_env()`,
  matching the pattern already in `query_index/config.py`.
- Three shared exception types in the base module:
  `LLMRateLimitError`, `LLMServerError`, `LLMConfigError`.
- Retry with exponential backoff on `429` / `5xx` via `tenacity` —
  3 attempts.
- Token-usage logging where the backend reports it (Azure/OpenAI/
  Anthropic); silent on Ollama.
- Coverage threshold per `docs/evaluation/coverage-thresholds.md`:
  85 %+ (HTTP transport mocked; one manual integration smoke per
  fully-implemented backend).

### Non-Goals

- **Async API.** v1 is sync only. Async will be added when Phase A.5
  HTTP API benefits from it.
- **Streaming responses.** Complete-response retrieval is sufficient
  for synthetic generation and judge calls.
- **Image / audio / fine-tuning operations.** YAGNI; not needed by
  any current consumer.
- **Pre-call token estimation.** `tiktoken` already exists in
  `pipelines/microsoft/ingestion/` for embedding-budget checks; we do
  not duplicate it here. We log post-call usage from the response.
- **Custom circuit-breaker / advanced rate-limit handling.** Tenacity's
  exponential-backoff retry is the contract.
- **Full-fidelity Ollama / OpenAI-direct / Anthropic backends.** Their
  protocol implementations exist as skeletons (correctly typed,
  HTTP-mocked tests), but integration with real endpoints is left for
  the first consumer that needs them.

## 3. Package Layout

```
features/core/
├── pyproject.toml
├── README.md
├── src/
│   └── llm_clients/
│       ├── __init__.py            ← public API: LLMClient, exceptions, factory
│       ├── base.py                ← Protocol, exceptions, shared types
│       ├── retry.py               ← tenacity wrapper used by all backends
│       ├── azure_openai/
│       │   ├── __init__.py
│       │   ├── config.py          ← AzureOpenAIConfig.from_env()
│       │   └── client.py          ← AzureOpenAIClient(LLMClient)
│       ├── openai_direct/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── client.py          ← skeleton: protocol-conformant, HTTP-mocked
│       ├── ollama_local/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── client.py          ← skeleton
│       └── anthropic/
│           ├── __init__.py
│           ├── config.py
│           └── client.py          ← skeleton
└── tests/
    ├── conftest.py
    ├── test_base.py               ← protocol + exceptions
    ├── test_retry.py              ← tenacity wrapper behaviour
    ├── test_azure_openai.py       ← full coverage with mocked HTTP
    ├── test_openai_direct.py      ← skeleton tests
    ├── test_ollama_local.py       ← skeleton tests
    └── test_anthropic.py          ← skeleton tests
```

`features/core/` is one Python package (`llm_clients`). Sub-packages
per backend keep their config/client co-located.

## 4. Protocol & Types

```python
# llm_clients/base.py

from typing import Protocol, Literal


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ResponseFormat:
    """Hint to the backend about response shape. v1 supports only JSON-mode."""
    type: Literal["text", "json_object"]


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class Completion:
    text: str
    model: str               # provider-reported model id (echoed back)
    usage: TokenUsage | None # None if backend doesn't report usage (Ollama)


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
```

## 5. Exceptions

```python
# llm_clients/base.py

class LLMError(Exception):
    """Base for all llm_clients errors."""


class LLMRateLimitError(LLMError):
    """Provider returned 429. Retry-after honoured by the retry layer."""


class LLMServerError(LLMError):
    """Provider returned 5xx. Retry-after exponential."""


class LLMConfigError(LLMError):
    """Auth, missing env var, or other setup-time failure."""
```

Backend-specific errors that don't map to these three propagate as
their original library type — we don't wrap them.

## 6. Retry policy

`llm_clients/retry.py` exports a single decorator:

```python
def with_retry(fn):
    """Retry on LLMRateLimitError and LLMServerError. 3 attempts.
    Exponential backoff: 1s, 2s, 4s (with jitter)."""
```

Every backend's `complete` and `embed` methods are decorated with
`@with_retry`. The decorator translates the underlying provider's
HTTP error to `LLMRateLimitError` / `LLMServerError` before letting
tenacity decide whether to retry.

After 3 failed attempts, the last exception propagates to the caller
unchanged (no wrapping).

## 7. Configuration

Each backend has a `Config` dataclass with a `from_env()` classmethod
that reads typed env vars. Pattern:

```python
# llm_clients/azure_openai/config.py
@dataclass(frozen=True)
class AzureOpenAIConfig:
    endpoint: str
    api_key: str
    api_version: str
    chat_deployment_name: str
    embedding_deployment_name: str

    @classmethod
    def from_env(cls) -> "AzureOpenAIConfig":
        return cls(
            endpoint=_required_env("AI_FOUNDRY_ENDPOINT"),
            api_key=_required_env("AI_FOUNDRY_KEY"),
            api_version=_required_env("AZURE_OPENAI_API_VERSION"),
            chat_deployment_name=_required_env("CHAT_DEPLOYMENT_NAME"),
            embedding_deployment_name=_required_env("EMBEDDING_DEPLOYMENT_NAME"),
        )
```

Env vars match the convention already used by
`pipelines/microsoft/retrieval/`: `AI_FOUNDRY_KEY`,
`AI_FOUNDRY_ENDPOINT`, `AZURE_OPENAI_API_VERSION`,
`EMBEDDING_DEPLOYMENT_NAME` (existing). One new variable —
`CHAT_DEPLOYMENT_NAME` — is added for the chat-completion deployment.
This single-source-of-truth arrangement is intentional: both packages
connect to the same Azure account.

Missing required env vars raise `LLMConfigError` at `from_env()` time.

The other three backends define their own `Config` shape but follow
the same `from_env()` contract.

## 8. Public API (`llm_clients/__init__.py`)

```python
from llm_clients.base import (
    LLMClient,
    Message,
    Completion,
    TokenUsage,
    ResponseFormat,
    LLMError,
    LLMRateLimitError,
    LLMServerError,
    LLMConfigError,
)
from llm_clients.azure_openai import AzureOpenAIClient, AzureOpenAIConfig
from llm_clients.openai_direct import OpenAIDirectClient, OpenAIDirectConfig
from llm_clients.ollama_local import OllamaLocalClient, OllamaLocalConfig
from llm_clients.anthropic import AnthropicClient, AnthropicConfig

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

## 9. Testing strategy

| Test file | Contents | Coverage target |
|-----------|----------|------|
| `test_base.py` | dataclass round-trips, exception hierarchy | 100 % |
| `test_retry.py` | retry-on-429, retry-on-5xx, no-retry-on-400, backoff timing | 95 %+ |
| `test_azure_openai.py` | full HTTP-mocked coverage of `complete` + `embed` | 90 %+ |
| `test_openai_direct.py` | skeleton: protocol conformance + happy-path mocked | 70 %+ |
| `test_ollama_local.py` | same | 70 %+ |
| `test_anthropic.py` | same | 70 %+ |

**Integration smokes** (not part of `pytest features/`): one manual
script per fully-implemented backend, run on demand with real env
credentials. In A.1 only Azure OpenAI gets a smoke. Path:
`features/core/tests/integration/smoke_azure_openai.py`. Runs only
when invoked directly.

## 10. Boundary check additions

`scripts/check_import_boundary.sh` is currently silent on
`core/`-layer imports. After A.1 we add:

- `openai.*` imports allowed in `features/core/llm_clients/` AND
  `features/pipelines/microsoft/retrieval/` (existing). Update line 28's
  exclusion to be `^features/(core/llm_clients|pipelines/microsoft/retrieval)/`.
- `azure.search.*`, `azure.identity.*` remain restricted to
  `pipelines/microsoft/retrieval/`.
- A new check 3: `anthropic.*` imports only inside
  `features/core/llm_clients/`.

## 11. Open Questions

1. **Anthropic SDK choice.** Use the official `anthropic` SDK (sync
  client `Anthropic()`)? Yes — same pattern as the other backends.
  Confirmed implicitly by "tenacity-based retry"; no alternative
  proposed.
2. **Ollama protocol.** Native Ollama HTTP API
  (`POST /api/chat`) vs OpenAI-compatible endpoint (`/v1/chat/completions`).
  Default to the native API in A.1 since Ollama's primary surface is
  native; users can configure an OpenAI-compatible endpoint via
  `OpenAIDirectConfig` pointing at `http://localhost:11434/v1`.

## 12. Out of Scope

- Tool/function-calling — different across providers; we add it when
  a consumer needs it.
- Caching of completions — premature; eval runs are deterministic at
  `temperature=0`, so simple eq-checks on `(prompt, model)` are enough
  for now.
- Cost tracking dashboards — usage is logged but not aggregated.
