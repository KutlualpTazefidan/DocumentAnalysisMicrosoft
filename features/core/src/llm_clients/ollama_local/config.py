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
