"""LLM client factory for local-pdf.

Selects a backend based on the LLM_BACKEND environment variable.

Supported backends:
  - ``ollama_local``  (default; matches the existing dev setup)
  - ``azure_openai``
  - ``vllm_remote``   (new — OpenAI-compatible vLLM server over HTTP;
                       enable for A.5 synthetic question generation by
                       setting ``LLM_BACKEND=vllm_remote`` plus
                       ``VLLM_BASE_URL`` and ``VLLM_MODEL``)
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from llm_clients.azure_openai import AzureOpenAIClient, AzureOpenAIConfig
from llm_clients.ollama_local import OllamaLocalClient, OllamaLocalConfig
from llm_clients.vllm_remote import VllmRemoteClient, VllmRemoteConfig

if TYPE_CHECKING:
    from llm_clients.base import LLMClient


def get_llm_client() -> LLMClient:
    backend = os.environ.get("LLM_BACKEND", "ollama_local")
    if backend == "vllm_remote":
        return VllmRemoteClient(VllmRemoteConfig.from_env())
    if backend == "ollama_local":
        return OllamaLocalClient(OllamaLocalConfig.from_env())
    if backend == "azure_openai":
        return AzureOpenAIClient(AzureOpenAIConfig.from_env())
    raise ValueError(f"unsupported backend: {backend}")


def get_default_model() -> str:
    """Return the model id for the configured backend.

    ``vllm_remote`` reads vllm-server/config.toml so the model name
    follows whatever the picker last selected. Falls back to the
    ``VLLM_MODEL`` env var if config.toml is missing (early-boot
    or non-vllm-server deployments). Other backends read
    ``LLM_MODEL`` with the historic ollama qwen2.5 default.
    """
    if os.environ.get("LLM_BACKEND") == "vllm_remote":
        # Late import to avoid a hard dep on llm_server when this
        # backend isn't selected.
        from local_pdf.llm_server.process import configured_model_name

        configured = configured_model_name()
        if configured:
            return configured
        return os.environ.get("VLLM_MODEL", "")
    return os.environ.get("LLM_MODEL", "qwen2.5:7b-instruct")
