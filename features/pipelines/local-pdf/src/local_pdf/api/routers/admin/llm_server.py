"""Routes that control the local vLLM subprocess.

The Synthesise tab in the SPA shows a status pill + Start/Stop button
that hits these endpoints. See ``local_pdf.llm_server.process`` for
the underlying VllmProcess manager.

Endpoints
---------

GET   /api/admin/llm/status   — current state + log tail
POST  /api/admin/llm/start    — spawn vllm-server/start.sh if not running
POST  /api/admin/llm/stop     — SIGTERM, then SIGKILL on timeout
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel

from local_pdf.llm_server.process import get_instance, vllm_serve_available

if TYPE_CHECKING:
    from local_pdf.llm_server import VllmStatus

router = APIRouter()


class LlmStatusResponse(BaseModel):
    state: str
    pid: int | None = None
    model: str | None = None
    base_url: str | None = None
    healthy: bool = False
    error: str | None = None
    log_tail: list[str] = []
    vllm_cli_available: bool = True


def _to_response(s: VllmStatus) -> LlmStatusResponse:
    return LlmStatusResponse(
        state=s.state,
        pid=s.pid,
        model=s.model,
        base_url=s.base_url,
        healthy=s.healthy,
        error=s.error,
        log_tail=s.log_tail,
        vllm_cli_available=vllm_serve_available(),
    )


@router.get("/api/admin/llm/status", response_model=LlmStatusResponse)
async def llm_status() -> LlmStatusResponse:
    return _to_response(get_instance().status())


@router.post("/api/admin/llm/start", response_model=LlmStatusResponse)
async def llm_start() -> LlmStatusResponse:
    # Free MinerU/torch's cached pipeline models before starting vLLM
    # so the new server doesn't fight the backend's already-loaded
    # weights for VRAM. Idempotent — safe to call when nothing is
    # cached. Subsequent extract calls reload on demand.
    try:
        from local_pdf.workers.mineru import free_cached_models

        free_cached_models()
    except Exception:
        # Cleanup is best-effort; never let it block the start path.
        pass
    return _to_response(get_instance().start())


@router.post("/api/admin/llm/stop", response_model=LlmStatusResponse)
async def llm_stop() -> LlmStatusResponse:
    return _to_response(get_instance().stop())
