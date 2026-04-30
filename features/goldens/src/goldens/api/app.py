"""FastAPI app factory.

`create_app()` is the single entry point. It loads `ApiConfig` from env,
loads the boot-time Identity, registers exception handlers for goldens
domain errors, mounts the auth middleware, and includes the docs/entries
routers.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from goldens.api.auth import install_auth_middleware
from goldens.api.config import ApiConfig
from goldens.api.identity import load_or_fail
from goldens.api.schemas import HealthResponse
from goldens.creation.curate import SlugResolutionError, StartResolutionError
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError


def create_app() -> FastAPI:
    cfg = ApiConfig()
    identity = load_or_fail()  # raises IdentityNotConfiguredError if absent

    app = FastAPI(
        title="goldens-api",
        version="0.1.0",
        description="HTTP wrapper around goldens curate / refine / deprecate / synthesise.",
    )

    # Stash config + identity on app.state so routers can fetch them via Request.
    app.state.config = cfg
    app.state.identity = identity

    install_auth_middleware(app, token=cfg.api_token)

    # ─── Exception handlers (domain → HTTP) ──────────────────────────────

    @app.exception_handler(EntryNotFoundError)
    async def _entry_not_found(_request: Request, exc: EntryNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SlugResolutionError)
    async def _slug_unknown(_request: Request, exc: SlugResolutionError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(StartResolutionError)
    async def _start_unknown(_request: Request, exc: StartResolutionError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(EntryDeprecatedError)
    async def _entry_deprecated(_request: Request, exc: EntryDeprecatedError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def _file_not_found(_request: Request, exc: FileNotFoundError) -> JSONResponse:
        # AnalyzeJsonLoader raises FileNotFoundError when slug or analyze/ is missing.
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # ─── Routes ──────────────────────────────────────────────────────────

    @app.get("/api/health", response_model=HealthResponse)
    async def _health() -> HealthResponse:
        return HealthResponse(goldens_root=str(cfg.data_root))

    # Routers (Tasks 8+) attach via app.include_router(...) below.
    from goldens.api.routers.docs import router as docs_router
    from goldens.api.routers.entries import router as entries_router

    app.include_router(docs_router)
    app.include_router(entries_router)

    # ─── Static SPA mount ────────────────────────────────────────────────
    # Mount frontend/dist/ at "/" when present. In dev mode (no `npm run
    # build` yet), the directory won't exist and we skip — only the API
    # routes plus /docs (Swagger) remain reachable.
    _dist = Path(__file__).resolve().parents[5] / "frontend" / "dist"
    if _dist.is_dir():
        app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")

    return app
