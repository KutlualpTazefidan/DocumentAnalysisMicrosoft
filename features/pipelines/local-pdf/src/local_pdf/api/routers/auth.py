"""Auth + feature endpoints.

Public surface:
  * ``POST /api/auth/login``  — username + password + tenant_slug,
                                 sets HttpOnly session cookie.
  * ``POST /api/auth/logout`` — clears cookie + revokes session.
  * ``GET  /api/auth/me``     — returns identity from request.state.
  * ``POST /api/auth/check``  — legacy X-Auth-Token introspect; kept
                                 so older clients (CLI/tests) keep
                                 working until Phase 5 removes them.
  * ``GET  /api/_features``   — public capabilities ping.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from local_pdf.api.auth import SESSION_COOKIE, lookup_token
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.sessions import create_session, revoke_session
from local_pdf.auth.tenants import get_tenant_by_id
from local_pdf.auth.users import (
    InactiveUserError,
    LoginLockedError,
    UnknownUserError,
    WrongPasswordError,
    authenticate,
)

router = APIRouter()
_log = logging.getLogger(__name__)

# Cookie lifetime mirrors the session TTL inside the DB. The browser
# drops the cookie when the server-side row expires, so a stale cookie
# can never be re-used.
_COOKIE_MAX_AGE_SECONDS = 24 * 60 * 60


class LoginRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    tenant_slug: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr


class IdentityResponse(BaseModel):
    """Public projection of ``AuthIdentity`` — what the frontend reads
    after login or on /me. Never leaks the curator-id / user-id keys
    unless the caller would already have them from earlier in the
    session, so we keep the response shape tight."""

    model_config = ConfigDict(frozen=True)
    role: str
    pseudonym: str
    tenant_slug: str | None
    name: str
    # Tenant display name (Anzeigename); None on the legacy token path.
    tenant_name: str | None = None


class CheckTokenRequest(BaseModel):
    token: str


class CheckTokenResponse(BaseModel):
    role: str
    name: str


class FeaturesResponse(BaseModel):
    features: list[str]
    roles: list[str]


@router.post("/api/auth/login", response_model=IdentityResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> IdentityResponse:
    """Verify ``(tenant_slug, username, password)`` and issue a session.

    Failure modes are deliberately collapsed into one 401 from the
    client's perspective so an attacker can't probe which usernames
    exist. The server log keeps the distinction for forensics.
    """
    cfg = request.app.state.config
    plain_password = body.password.get_secret_value()
    try:
        with open_auth_db(cfg.data_root) as conn:
            ensure_schema(conn)
            user = authenticate(
                conn,
                tenant_slug=body.tenant_slug,
                username=body.username,
                password=plain_password,
            )
            session = create_session(conn, user_id=user.user_id)
            tenant_slug = body.tenant_slug
            tenant_obj = get_tenant_by_id(conn, user.tenant_id)
            tenant_name = tenant_obj.name if tenant_obj else None
    except LoginLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "login locked", "locked_until": exc.locked_until},
        ) from exc
    except (UnknownUserError, WrongPasswordError, InactiveUserError) as exc:
        _log.info("login rejected: %s", exc.__class__.__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from exc

    # HttpOnly + SameSite=Lax: covers same-origin via Vite proxy and
    # cookies follow redirects. ``secure`` stays False on plain HTTP
    # localhost; enable in production behind HTTPS via reverse proxy.
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session.session_id,
        max_age=_COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return IdentityResponse(
        role=user.role,
        pseudonym=user.pseudonym,
        tenant_slug=tenant_slug,
        name=user.pseudonym,
        tenant_name=tenant_name,
    )


@router.post("/api/auth/logout")
async def logout(request: Request) -> Response:
    """Revoke the current session row and clear the cookie.

    Idempotent: missing cookie or unknown session still returns 204 so
    a stale-tab logout doesn't bubble up as an error. Returns a
    fresh ``Response`` rather than mutating the injected one so the
    status code persists through FastAPI's response model layer.
    """
    cfg = request.app.state.config
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        try:
            with open_auth_db(cfg.data_root) as conn:
                ensure_schema(conn)
                revoke_session(conn, session_token)
        except Exception as exc:  # pragma: no cover — defensive
            _log.warning("logout revoke failed: %s", exc)
    out = JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
    out.delete_cookie(key=SESSION_COOKIE, path="/")
    return out


@router.get("/api/auth/me", response_model=IdentityResponse)
async def me(request: Request) -> IdentityResponse:
    """Return identity for the current session.

    Middleware has already verified the request; we just project
    ``request.state.identity`` into the public shape."""
    ident = getattr(request.state, "identity", None)
    if ident is None:
        # Shouldn't happen — middleware would have already 401'd.
        raise HTTPException(status_code=401, detail="not authenticated")
    return IdentityResponse(
        role=ident.role,
        pseudonym=ident.pseudonym,
        tenant_slug=ident.tenant_slug,
        name=ident.name,
        tenant_name=ident.tenant_name,
    )


@router.post("/api/auth/check", response_model=CheckTokenResponse)
async def check_token(body: CheckTokenRequest, request: Request) -> CheckTokenResponse:
    """Legacy token-introspect endpoint. Kept for backward compat with
    CLI / test clients; will be removed after Phase 5."""
    cfg = request.app.state.config
    ident = lookup_token(cfg.data_root, body.token, admin_token=cfg.api_token)
    if ident is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return CheckTokenResponse(role=ident.role, name=ident.name)


@router.get("/api/_features", response_model=FeaturesResponse)
async def get_features() -> FeaturesResponse:
    return FeaturesResponse(
        features=["local-pdf", "curate", "synthesise"],
        roles=["admin", "curator"],
    )
