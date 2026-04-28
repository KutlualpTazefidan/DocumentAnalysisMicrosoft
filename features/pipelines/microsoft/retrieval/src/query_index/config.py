"""Environment-driven configuration for query_index.

`Config.from_env()` reads required variables from os.environ. Missing variables
raise KeyError with the variable name in the message. EMBEDDING_DIMENSIONS is
parsed as int; if it is not numeric, ValueError is raised.

Loading dotenv files (`.env`) is the responsibility of the entry point, not this
module — see the spec section on env loading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_REQUIRED_VARS: tuple[str, ...] = (
    "AI_FOUNDRY_KEY",
    "AI_FOUNDRY_ENDPOINT",
    "AI_SEARCH_KEY",
    "AI_SEARCH_ENDPOINT",
    "AI_SEARCH_INDEX_NAME",
    "EMBEDDING_DEPLOYMENT_NAME",
    "EMBEDDING_MODEL_VERSION",
    "EMBEDDING_DIMENSIONS",
    "AZURE_OPENAI_API_VERSION",
)


@dataclass(frozen=True)
class Config:
    ai_foundry_key: str
    ai_foundry_endpoint: str
    ai_search_key: str
    ai_search_endpoint: str
    ai_search_index_name: str
    embedding_deployment_name: str
    embedding_model_version: str
    embedding_dimensions: int
    azure_openai_api_version: str

    @classmethod
    def from_env(cls) -> Config:
        for var in _REQUIRED_VARS:
            if var not in os.environ:
                raise KeyError(f"Required environment variable not set: {var}")

        return cls(
            ai_foundry_key=os.environ["AI_FOUNDRY_KEY"],
            ai_foundry_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
            ai_search_key=os.environ["AI_SEARCH_KEY"],
            ai_search_endpoint=os.environ["AI_SEARCH_ENDPOINT"],
            ai_search_index_name=os.environ["AI_SEARCH_INDEX_NAME"],
            embedding_deployment_name=os.environ["EMBEDDING_DEPLOYMENT_NAME"],
            embedding_model_version=os.environ["EMBEDDING_MODEL_VERSION"],
            embedding_dimensions=int(os.environ["EMBEDDING_DIMENSIONS"]),
            azure_openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        )
