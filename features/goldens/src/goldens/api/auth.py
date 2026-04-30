"""X-Auth-Token middleware. Header-based static-token guard for /api/* paths.

Allowlisted (no token required):
- /api/health  — liveness probe
- /docs        — Swagger UI
- /openapi.json — schema
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request

_ALLOWLIST = ("/api/health", "/docs", "/openapi.json", "/redoc")


def install_auth_middleware(app: FastAPI, *, token: str) -> None:
    """Register an HTTP middleware that requires `X-Auth-Token: <token>` on
    every `/api/*` path EXCEPT the allowlisted ones."""

    @app.middleware("http")
    async def _check_token(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path
        # Allowlisted paths: pass through unconditionally.
        if path in _ALLOWLIST or any(path.startswith(prefix + "/") for prefix in _ALLOWLIST):
            return await call_next(request)
        # Non-/api/ paths: pass through (FastAPI 404s them naturally).
        if not path.startswith("/api/"):
            return await call_next(request)
        sent = request.headers.get("X-Auth-Token")
        if not sent or sent != token:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid X-Auth-Token"},
            )
        return await call_next(request)
