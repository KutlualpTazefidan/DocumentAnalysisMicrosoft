"""Admin endpoints for tenant + user management.

All routes here require ``role=admin`` (enforced by middleware via the
``/api/admin/`` path prefix). A user is always created inside the
caller's own tenant — cross-tenant admin actions need a separate
super-admin path that doesn't exist yet (and probably shouldn't, for
this single-machine setup).

The pseudonym story:
  * ``POST /tenants/{slug}/users`` with ``pseudonym = None`` auto-
    generates a fresh "Adjective Animal" pair, avoiding collisions
    with existing pseudonyms in the same tenant.
  * Passing a non-null ``pseudonym`` runs the field through
    :func:`validate_user_pseudonym` so an admin can't accidentally
    bake an email or known first name into the audit identity.

The endpoints return ``UserOut`` projections rather than the internal
:class:`User` dataclass so we keep flexibility to add internal fields
(e.g., notes) without affecting the API contract.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.pseudonyms import generate_pseudonym
from local_pdf.auth.sessions import revoke_all_sessions_for_user
from local_pdf.auth.tenants import (
    create_tenant,
    delete_tenant,
    get_tenant_by_slug,
    list_tenants,
    update_tenant_name,
)
from local_pdf.auth.users import (
    create_user,
    deactivate_user,
    get_user_by_id,
    list_users_for_tenant,
)

router = APIRouter()


# ── Pydantic projections ────────────────────────────────────────────────


class TenantOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    tenant_id: str
    slug: str
    name: str
    created_at: str


class TenantsResponse(BaseModel):
    tenants: list[TenantOut]


class CreateTenantRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)


class UpdateTenantRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: str
    tenant_id: str
    username: str
    pseudonym: str
    role: str
    active: bool
    created_at: str
    last_login_at: str | None


class UsersResponse(BaseModel):
    users: list[UserOut]


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr
    role: Literal["admin", "reviewer", "curator"] = "curator"
    pseudonym: str | None = Field(
        default=None,
        description=(
            "Optional override. Empty / null = auto-generate. Use the "
            "Pseudonym suggestion endpoint to preview before submit."
        ),
    )


class PseudonymSuggestResponse(BaseModel):
    pseudonym: str


# ── Tenants ─────────────────────────────────────────────────────────────


@router.get("/api/admin/tenants", response_model=TenantsResponse)
async def admin_list_tenants(request: Request) -> TenantsResponse:
    cfg = request.app.state.config
    with open_auth_db(cfg.data_root) as conn:
        ensure_schema(conn)
        rows = list_tenants(conn)
    return TenantsResponse(
        tenants=[
            TenantOut(tenant_id=t.tenant_id, slug=t.slug, name=t.name, created_at=t.created_at)
            for t in rows
        ]
    )


@router.post(
    "/api/admin/tenants",
    response_model=TenantOut,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_tenant(body: CreateTenantRequest, request: Request) -> TenantOut:
    cfg = request.app.state.config
    try:
        with open_auth_db(cfg.data_root) as conn:
            ensure_schema(conn)
            t = create_tenant(conn, slug=body.slug, name=body.name)
    except ValueError as exc:
        # Slug clash or invalid input — surface as 409.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TenantOut(tenant_id=t.tenant_id, slug=t.slug, name=t.name, created_at=t.created_at)


@router.patch("/api/admin/tenants/{tenant_slug}", response_model=TenantOut)
async def admin_update_tenant(
    tenant_slug: str, body: UpdateTenantRequest, request: Request
) -> TenantOut:
    """Rename a tenant. Only ``name`` is mutable — the slug is the
    partition key for ``data_root/tenants/{slug}/`` and is immutable."""
    cfg = request.app.state.config
    try:
        with open_auth_db(cfg.data_root) as conn:
            ensure_schema(conn)
            t = update_tenant_name(conn, slug=tenant_slug, name=body.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TenantOut(tenant_id=t.tenant_id, slug=t.slug, name=t.name, created_at=t.created_at)


@router.delete(
    "/api/admin/tenants/{tenant_slug}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def admin_delete_tenant(tenant_slug: str, request: Request) -> None:
    """Hard-delete a tenant. Users + sessions cascade via FK; data
    under ``data_root/tenants/{slug}/`` stays on disk for manual
    cleanup. Refuses to delete the caller's own tenant — would
    lock the admin out of the system on the next request."""
    ident = getattr(request.state, "identity", None)
    if ident is not None and getattr(ident, "tenant_slug", None) == tenant_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Eigenen Fachbereich kannst du nicht löschen.",
        )
    cfg = request.app.state.config
    try:
        with open_auth_db(cfg.data_root) as conn:
            ensure_schema(conn)
            delete_tenant(conn, slug=tenant_slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ── Users (scoped to tenant slug) ───────────────────────────────────────


@router.get("/api/admin/tenants/{tenant_slug}/users", response_model=UsersResponse)
async def admin_list_users(tenant_slug: str, request: Request) -> UsersResponse:
    cfg = request.app.state.config
    with open_auth_db(cfg.data_root) as conn:
        ensure_schema(conn)
        tenant = get_tenant_by_slug(conn, tenant_slug)
        if tenant is None:
            raise HTTPException(status_code=404, detail=f"tenant not found: {tenant_slug}")
        rows = list_users_for_tenant(conn, tenant.tenant_id)
    return UsersResponse(
        users=[
            UserOut(
                user_id=u.user_id,
                tenant_id=u.tenant_id,
                username=u.username,
                pseudonym=u.pseudonym,
                role=u.role,
                active=u.active,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
            )
            for u in rows
        ]
    )


@router.post(
    "/api/admin/tenants/{tenant_slug}/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_user(tenant_slug: str, body: CreateUserRequest, request: Request) -> UserOut:
    cfg = request.app.state.config
    try:
        with open_auth_db(cfg.data_root) as conn:
            ensure_schema(conn)
            tenant = get_tenant_by_slug(conn, tenant_slug)
            if tenant is None:
                raise HTTPException(status_code=404, detail=f"tenant not found: {tenant_slug}")
            user = create_user(
                conn,
                tenant_id=tenant.tenant_id,
                username=body.username,
                password=body.password.get_secret_value(),
                role=body.role,
                pseudonym=body.pseudonym,
            )
    except ValueError as exc:
        # 409 covers username clash, pseudonym clash, validator
        # rejections (email pattern, real-name first token).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserOut(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        username=user.username,
        pseudonym=user.pseudonym,
        role=user.role,
        active=user.active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.delete("/api/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_deactivate_user(user_id: str, request: Request) -> None:
    """Soft-delete: flip ``active = 0`` AND revoke any open sessions.

    We do NOT hard-delete the row so audit logs that reference the
    ``user_id`` (or its pseudonym) remain attributable.
    """
    cfg = request.app.state.config
    with open_auth_db(cfg.data_root) as conn:
        ensure_schema(conn)
        existing = get_user_by_id(conn, user_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"user not found: {user_id}")
        deactivate_user(conn, user_id)
        revoke_all_sessions_for_user(conn, user_id)
    return None


# ── Pseudonym preview (UX helper for the create-user form) ──────────────


@router.get(
    "/api/admin/tenants/{tenant_slug}/pseudonym-suggest",
    response_model=PseudonymSuggestResponse,
)
async def admin_suggest_pseudonym(tenant_slug: str, request: Request) -> PseudonymSuggestResponse:
    cfg = request.app.state.config
    with open_auth_db(cfg.data_root) as conn:
        ensure_schema(conn)
        tenant = get_tenant_by_slug(conn, tenant_slug)
        if tenant is None:
            raise HTTPException(status_code=404, detail=f"tenant not found: {tenant_slug}")
        rows = list_users_for_tenant(conn, tenant.tenant_id)
    existing = {u.pseudonym for u in rows}
    return PseudonymSuggestResponse(pseudonym=generate_pseudonym(exclude=existing))
