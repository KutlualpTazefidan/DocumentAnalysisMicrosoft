"""Auth middleware: session-cookie first, X-Auth-Token fallback.

Resolution order (first match wins):
  1. ``Cookie: lpdf_session=...``        — SQLite-backed local auth
                                            (multi-tenant, see local_pdf.auth)
  2. ``X-Auth-Token`` request header     — legacy curator-token model;
                                            still supported so CLI / tests
                                            don't have to be refactored at
                                            the same time. Deprecated, will
                                            be removed after Phase 5 of the
                                            multi-tenant migration.

Path-based role enforcement (after identity resolution):
  - /api/admin/*  requires role=admin     (else 403)
  - /api/curate/* requires role=curator   (else 403; admin not accepted —
                                            keeps tenant-curator activity
                                            distinct from admin tooling)
  - /api/auth/login, /api/auth/check, /api/_features, /api/health → public

Public bypass (no auth at all):
  - /api/admin/docs/{slug}/mineru-images/{file} — iframe srcdoc <img>
    cannot send headers; the slug is the access guard.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from fastapi.responses import JSONResponse

from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.sessions import lookup_session
from local_pdf.auth.tenants import get_tenant_by_id
from local_pdf.auth.users import get_user_by_id
from local_pdf.storage.curators import find_by_token_hash, hash_token

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import FastAPI, Request

_log = logging.getLogger(__name__)

_ALLOWLIST = ("/api/health", "/docs", "/openapi.json", "/redoc", "/api/_features")
# Routes that handle their own auth (or have none). The login route
# obviously can't require an existing session; /auth/check is the legacy
# token-introspect path.
_AUTH_PUBLIC = ("/api/auth/check", "/api/auth/login")
_IMAGE_PATH_RE = re.compile(r"^/api/admin/docs/[^/]+/mineru-images/[^/]+$")

SESSION_COOKIE = "lpdf_session"


@dataclass(frozen=True)
class AuthIdentity:
    """Identity attached to ``request.state.identity`` after auth.

    ``pseudonym`` is the user-facing audit identity (lands in JSONL).
    ``name`` is kept as an alias for backward compat with code that reads
    ``identity.name`` (legacy curator path stores the real name there;
    the new session path mirrors ``pseudonym`` into it).

    ``tenant_slug`` / ``user_id`` are populated only on the session path;
    the legacy X-Auth-Token path leaves them ``None`` so existing callers
    keep working.
    """

    role: Literal["admin", "curator", "reviewer"]
    name: str
    pseudonym: str
    curator_id: str | None
    user_id: str | None
    tenant_slug: str | None
    # Tenant display name (Anzeigename); session path only, default None on
    # the legacy token path. Lets the frontend show it without an extra
    # admin-only tenants fetch (curators can't reach that endpoint).
    tenant_name: str | None = None


def lookup_token(data_root: Path, token: str, *, admin_token: str) -> AuthIdentity | None:
    """Legacy X-Auth-Token lookup. Curators-JSON or env-var admin token.

    Returns ``None`` on miss; callers map that to 401.
    """
    if not token:
        return None
    cur = find_by_token_hash(data_root, hash_token(token))
    if cur is not None:
        return AuthIdentity(
            role="curator",
            name=cur.name,
            pseudonym=cur.name,  # pre-multi-tenant: no real pseudonym
            curator_id=cur.id,
            user_id=None,
            tenant_slug=None,
        )
    if token == admin_token:
        return AuthIdentity(
            role="admin",
            name="admin",
            pseudonym="admin",
            curator_id=None,
            user_id=None,
            tenant_slug=None,
        )
    return None


def lookup_session_cookie(data_root: Path, session_token: str) -> AuthIdentity | None:
    """Session-cookie path: SQLite lookup, returns identity or ``None``.

    Validates that the session row exists, is not revoked, has not
    expired, and that the linked user is still active. Tenant slug is
    re-resolved on every request so renaming a tenant doesn't leave
    stale identities cached in cookies.
    """
    if not session_token:
        return None
    try:
        with open_auth_db(data_root) as conn:
            ensure_schema(conn)
            session = lookup_session(conn, session_token)
            if session is None:
                return None
            user = get_user_by_id(conn, session.user_id)
            if user is None or not user.active:
                return None
            tenant = get_tenant_by_id(conn, user.tenant_id)
            if tenant is None:
                return None
            return AuthIdentity(
                role=user.role,
                name=user.pseudonym,
                pseudonym=user.pseudonym,
                curator_id=None,
                user_id=user.user_id,
                tenant_slug=tenant.slug,
                tenant_name=tenant.name,
            )
    except Exception as exc:  # pragma: no cover — defensive only
        _log.warning("session lookup failed: %s", exc)
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

        cfg = getattr(request.app.state, "config", None)
        data_root = cfg.data_root if cfg is not None else Path("/tmp/no-curators")

        # Cookie first — preferred for browser sessions.
        ident: AuthIdentity | None = None
        cookie_token = request.cookies.get(SESSION_COOKIE) or ""
        if cookie_token:
            ident = lookup_session_cookie(data_root, cookie_token)

        # Fall back to legacy header. Logged at debug level so the
        # eventual removal-window can be timed by counting fallbacks.
        if ident is None:
            header_token = request.headers.get("X-Auth-Token") or ""
            if header_token:
                ident = lookup_token(data_root, header_token, admin_token=token)
                if ident is not None:
                    _log.debug("auth: X-Auth-Token fallback (deprecated)")

        if ident is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "missing or invalid credentials"},
            )

        if path.startswith("/api/admin/") and ident.role != "admin":
            return JSONResponse(status_code=403, content={"detail": "admin role required"})
        if path.startswith("/api/curate/") and ident.role != "curator":
            return JSONResponse(status_code=403, content={"detail": "curator role required"})

        request.state.identity = ident
        return await call_next(request)
