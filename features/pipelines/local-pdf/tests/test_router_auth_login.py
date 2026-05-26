"""End-to-end tests for /api/auth/login, /logout, /me.

These tests exercise the full middleware -> route -> SQLite chain
because the value of session-cookie auth is in the composition. Unit
tests on each layer live in test_auth_*.py.
"""

from __future__ import annotations

import pytest
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import create_user


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "legacy-admin-token")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    # Seed: one tenant + one curator + one admin user.
    with open_auth_db(root) as conn:
        ensure_schema(conn)
        tenant = create_tenant(conn, slug="default", name="Default")
        create_user(
            conn,
            tenant_id=tenant.tenant_id,
            username="alice",
            password="secret",
            role="curator",
            pseudonym="Wachsamer Hirsch",
        )
        create_user(
            conn,
            tenant_id=tenant.tenant_id,
            username="boss",
            password="bosspw",
            role="admin",
            pseudonym="Klarer Wolf",
        )

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def test_login_sets_session_cookie(client):
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "alice", "password": "secret"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "curator"
    assert body["pseudonym"] == "Wachsamer Hirsch"
    assert body["tenant_slug"] == "default"
    # Cookie present + HttpOnly.
    cookie_header = r.headers.get("set-cookie", "").lower()
    assert "lpdf_session=" in cookie_header
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header


def test_login_wrong_password_is_401(client):
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "alice", "password": "wrong"},
    )
    assert r.status_code == 401
    # No oracle: same error as wrong username.
    assert r.json()["detail"] == "invalid credentials"


def test_login_unknown_user_is_401_not_404(client):
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "ghost", "password": "x"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"


def test_login_unknown_tenant_is_401(client):
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": "fake", "username": "alice", "password": "secret"},
    )
    assert r.status_code == 401


def test_me_returns_identity_after_login(client):
    client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "alice", "password": "secret"},
    )
    r = client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "curator"
    assert body["pseudonym"] == "Wachsamer Hirsch"
    assert body["tenant_slug"] == "default"


def test_me_without_session_is_401(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_revokes_session(client):
    client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "alice", "password": "secret"},
    )
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    # Cookie was cleared; subsequent /me is 401.
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 401


def test_admin_route_blocks_curator(client):
    """A curator session can call /api/auth/me but not /api/admin/*."""
    client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "alice", "password": "secret"},
    )
    r = client.get("/api/admin/llm/status")
    assert r.status_code == 403


def test_admin_route_allows_admin(client):
    client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "boss", "password": "bosspw"},
    )
    r = client.get("/api/admin/llm/status")
    # The route may return 200 or whatever vLLM status reports, but
    # auth must NOT be the blocker.
    assert r.status_code != 401
    assert r.status_code != 403


def test_legacy_token_still_works(client):
    """X-Auth-Token fallback path: admin env-var token still authenticates."""
    r = client.get("/api/admin/llm/status", headers={"X-Auth-Token": "legacy-admin-token"})
    assert r.status_code != 401
    assert r.status_code != 403


def test_login_then_admin_route_with_cookie(client):
    """The session cookie alone (no X-Auth-Token header) authorises an
    admin route when the logged-in user has role=admin."""
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "boss", "password": "bosspw"},
    )
    assert r.status_code == 200
    # Cookie auto-attached by TestClient.
    r2 = client.get("/api/admin/llm/status")
    assert r2.status_code != 401
    assert r2.status_code != 403
