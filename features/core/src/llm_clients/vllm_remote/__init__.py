"""vLLM remote backend — thin wrapper around openai_direct.

vLLM exposes an OpenAI-compatible HTTP API at ``/v1/`` so the actual
client work is identical to the OpenAI direct path. This package only
exists so env-var names are self-documenting (``VLLM_BASE_URL``,
``VLLM_MODEL``, ``VLLM_API_KEY``) instead of overloading
``OPENAI_*`` for a non-OpenAI deployment.
"""

from llm_clients.vllm_remote.client import VllmRemoteClient
from llm_clients.vllm_remote.config import VllmRemoteConfig

__all__ = ["VllmRemoteClient", "VllmRemoteConfig"]
