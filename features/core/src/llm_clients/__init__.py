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
