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
