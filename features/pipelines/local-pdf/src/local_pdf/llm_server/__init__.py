"""Process management for the standalone vllm-server/ launcher.

The FastAPI backend uses ``VllmProcess`` to start, stop, and monitor a
local vLLM OpenAI-compatible server (defined under repo-root
``vllm-server/``). ``terminate_on_app_shutdown`` is wired into the app
lifespan so we never leak a vLLM worker if the backend crashes or
restarts.
"""

from local_pdf.llm_server.process import VllmProcess, VllmStatus

__all__ = ["VllmProcess", "VllmStatus"]
