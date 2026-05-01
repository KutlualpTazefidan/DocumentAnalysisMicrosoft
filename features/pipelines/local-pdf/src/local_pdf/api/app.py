"""FastAPI app factory for local-pdf."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_pdf.api.auth import install_auth_middleware
from local_pdf.api.config import ApiConfig
from local_pdf.api.schemas import HealthResponse


def create_app() -> FastAPI:
    cfg = ApiConfig()
    cfg.data_root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="local-pdf-api",
        version="0.2.0",
        description="Local PDF pipeline API (DocLayout-YOLO + MinerU 3).",
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
    from local_pdf.api.routers.admin.docs import router as admin_docs_router
    from local_pdf.api.routers.admin.extract import router as extract_router
    from local_pdf.api.routers.admin.segments import router as segments_router
    from local_pdf.api.routers.auth import router as auth_router
    from local_pdf.api.routers.curate.docs import router as curate_docs_router
    from local_pdf.api.routers.curate.elements import router as curate_elements_router

    app.include_router(auth_router)
    app.include_router(gone_router)
    app.include_router(admin_docs_router)
    app.include_router(segments_router)
    app.include_router(extract_router)
    app.include_router(curate_docs_router)
    app.include_router(curate_elements_router)

    return app
