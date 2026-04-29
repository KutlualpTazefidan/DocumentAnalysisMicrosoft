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
