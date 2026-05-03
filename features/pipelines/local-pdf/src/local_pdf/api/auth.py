"""Role-aware X-Auth-Token middleware.

Token resolution order:
  1. Hash matches an active curator in `<data_root>/curators.json` → role=curator
  2. Token equals env-var GOLDENS_API_TOKEN exactly                → role=admin
  3. Otherwise → 401

Path-based role enforcement:
  - /api/admin/* requires role=admin (else 403)
  - /api/curate/* requires role=curator (else 403)
  - /api/auth/*, /api/_features, /api/health → public/authed via token only

Public bypass (no token check at all):
  - /api/admin/docs/{slug}/mineru-images/{file} — served to <img> tags
    inside iframe srcdoc, which can't carry custom headers. Single-user
    MVP bound to 127.0.0.1 so the slug is a sufficient access guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi.responses import JSONResponse

from local_pdf.storage.curators import find_by_token_hash, hash_token

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request

_ALLOWLIST = ("/api/health", "/docs", "/openapi.json", "/redoc", "/api/_features")
_AUTH_PUBLIC = ("/api/auth/check",)  # validates own header, no middleware enforcement

# Iframe srcdoc <img> tags can't send X-Auth-Token. Bypass middleware for
# the mineru-images GET route only (read-only, scoped to a known slug).
_IMAGE_PATH_RE = re.compile(r"^/api/admin/docs/[^/]+/mineru-images/[^/]+$")


@dataclass(frozen=True)
class AuthIdentity:
    role: Literal["admin", "curator"]
    name: str
    curator_id: str | None


def lookup_token(data_root: Path, token: str, *, admin_token: str) -> AuthIdentity | None:
    if not token:
        return None
    cur = find_by_token_hash(data_root, hash_token(token))
    if cur is not None:
        return AuthIdentity(role="curator", name=cur.name, curator_id=cur.id)
    if token == admin_token:
        return AuthIdentity(role="admin", name="admin", curator_id=None)
    return None


def install_auth_middleware(app: FastAPI, *, token: str) -> None:
    @app.middleware("http")
    async def _check_token(
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        path = request.url.path
        if path in _ALLOWLIST or any(path.startswith(p + "/") for p in _ALLOWLIST):
            return await call_next(request)
        if path in _AUTH_PUBLIC:
            return await call_next(request)
        if request.method == "GET" and _IMAGE_PATH_RE.match(path):
            return await call_next(request)
        if not path.startswith("/api/"):
            return await call_next(request)

        sent = request.headers.get("X-Auth-Token") or ""
        cfg = getattr(request.app.state, "config", None)
        data_root = cfg.data_root if cfg is not None else Path("/tmp/no-curators")
        ident = lookup_token(data_root, sent, admin_token=token)
        if ident is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid X-Auth-Token"},
            )

        if path.startswith("/api/admin/") and ident.role != "admin":
            return JSONResponse(status_code=403, content={"detail": "admin role required"})
        if path.startswith("/api/curate/") and ident.role != "curator":
            return JSONResponse(status_code=403, content={"detail": "curator role required"})

        request.state.identity = ident
        return await call_next(request)
