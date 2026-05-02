"""LLM client factory for local-pdf.

Selects a backend based on the LLM_BACKEND environment variable.
Defaults to ollama_local with qwen2.5:7b-instruct.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from llm_clients.azure_openai import AzureOpenAIClient, AzureOpenAIConfig
from llm_clients.ollama_local import OllamaLocalClient, OllamaLocalConfig

if TYPE_CHECKING:
    from llm_clients.base import LLMClient


def get_llm_client() -> LLMClient:
    backend = os.environ.get("LLM_BACKEND", "ollama_local")
    if backend == "ollama_local":
        return OllamaLocalClient(OllamaLocalConfig.from_env())
    if backend == "azure_openai":
        return AzureOpenAIClient(AzureOpenAIConfig.from_env())
    raise ValueError(f"unsupported backend: {backend}")


def get_default_model() -> str:
    return os.environ.get("LLM_MODEL", "qwen2.5:7b-instruct")
