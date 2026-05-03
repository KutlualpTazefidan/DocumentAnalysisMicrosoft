"""Environment-driven config for the vLLM remote backend.

vLLM (https://github.com/vllm-project/vllm) ships with an OpenAI-compatible
HTTP server. We connect to it the same way we'd connect to OpenAI, but
with a self-hosted base URL and (typically) no real authentication.

Required env vars
-----------------
``VLLM_BASE_URL``  — e.g. ``http://vllm-host:8000/v1``
``VLLM_MODEL``     — the model identifier vLLM serves, e.g.
                     ``mistralai/Mistral-7B-Instruct-v0.3``

Optional
--------
``VLLM_API_KEY``   — defaults to ``"vllm"`` since the OpenAI SDK requires
                     a non-empty key string but vLLM's default deployment
                     accepts any value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from llm_clients.base import LLMConfigError


@dataclass(frozen=True)
class VllmRemoteConfig:
    base_url: str
    model: str
    api_key: str

    @classmethod
    def from_env(cls) -> VllmRemoteConfig:
        if "VLLM_BASE_URL" not in os.environ:
            raise LLMConfigError("Missing required env var: VLLM_BASE_URL")
        if "VLLM_MODEL" not in os.environ:
            raise LLMConfigError("Missing required env var: VLLM_MODEL")
        return cls(
            base_url=os.environ["VLLM_BASE_URL"],
            model=os.environ["VLLM_MODEL"],
            api_key=os.getenv("VLLM_API_KEY", "vllm"),
        )
