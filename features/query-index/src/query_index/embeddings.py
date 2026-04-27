"""Embedding helper.

`get_embedding` calls Azure OpenAI's embeddings API with the deployment name
configured in the environment and returns the embedding vector as a list of
floats. Uses the hybrid-cfg convention: pass cfg explicitly for testability,
or omit to have Config.from_env() loaded automatically.
"""

from __future__ import annotations

from query_index.client import get_openai_client
from query_index.config import Config


def get_embedding(text: str, cfg: Config | None = None) -> list[float]:
    if cfg is None:
        cfg = Config.from_env()
    client = get_openai_client(cfg)
    response = client.embeddings.create(input=[text], model=cfg.embedding_deployment_name)
    return list(response.data[0].embedding)
