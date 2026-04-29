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
