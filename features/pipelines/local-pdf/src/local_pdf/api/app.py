"""FastAPI app factory for local-pdf."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from local_pdf.api.auth import install_auth_middleware
from local_pdf.api.config import ApiConfig
from local_pdf.api.schemas import HealthResponse


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """App lifespan — release MinerU VLM weights + CUDA memory + SIGTERM
    any managed vLLM subprocess on shutdown.

    Without this, Ctrl-C on the dev server can leave the process hanging
    on PyTorch worker threads / cached predictor singletons. We call
    MinerU's own shutdown helper plus torch.cuda.empty_cache() so
    uvicorn's shutdown signal can finish. We also tell the local vLLM
    process manager to terminate any subprocess it owns — so an admin
    who Ctrl-C's the backend doesn't end up with an orphan vLLM holding
    GPU memory.
    """
    yield
    try:
        from local_pdf.llm_server.process import terminate_on_app_shutdown

        terminate_on_app_shutdown()
    except Exception:
        pass
    try:
        from mineru.backend.vlm.vlm_analyze import shutdown_cached_models

        shutdown_cached_models()
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def create_app() -> FastAPI:
    cfg = ApiConfig()
    cfg.data_root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="local-pdf-api",
        version="0.2.0",
        description="Local PDF pipeline API (DocLayout-YOLO + MinerU VLM).",
        lifespan=_lifespan,
    )
    app.state.config = cfg

    install_auth_middleware(app, token=cfg.api_token)

    @app.exception_handler(FileNotFoundError)
    async def _file_not_found(_req: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_req: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health", response_model=HealthResponse)
    async def _health() -> HealthResponse:
        return HealthResponse(data_root=str(cfg.data_root))

    from local_pdf.api.routers._gone import router as gone_router
    from local_pdf.api.routers.admin.comparison import router as comparison_router
    from local_pdf.api.routers.admin.curators import router as admin_curators_router
    from local_pdf.api.routers.admin.docs import router as admin_docs_router
    from local_pdf.api.routers.admin.extract import router as extract_router
    from local_pdf.api.routers.admin.llm_server import router as llm_server_router
    from local_pdf.api.routers.admin.pipelines import router as pipelines_router
    from local_pdf.api.routers.admin.provenienz import router as provenienz_router
    from local_pdf.api.routers.admin.segments import router as segments_router
    from local_pdf.api.routers.admin.synthesise import router as synthesise_router
    from local_pdf.api.routers.auth import router as auth_router
    from local_pdf.api.routers.curate.docs import router as curate_docs_router
    from local_pdf.api.routers.curate.elements import router as curate_elements_router
    from local_pdf.api.routers.curate.questions import router as curate_questions_router

    app.include_router(auth_router)
    app.include_router(gone_router)
    app.include_router(admin_docs_router)
    app.include_router(segments_router)
    app.include_router(extract_router)
    app.include_router(synthesise_router)
    app.include_router(comparison_router)
    app.include_router(pipelines_router)
    app.include_router(provenienz_router)
    app.include_router(llm_server_router)
    app.include_router(admin_curators_router)
    app.include_router(curate_docs_router)
    app.include_router(curate_elements_router)
    app.include_router(curate_questions_router)

    return app
