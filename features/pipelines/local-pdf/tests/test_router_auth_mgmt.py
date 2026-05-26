"""End-to-end tests for the admin tenant/user-management routes."""

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

    # Seed one tenant + one admin user so the admin routes can be
    # exercised through a normal login session.
    with open_auth_db(root) as conn:
        ensure_schema(conn)
        tenant = create_tenant(conn, slug="default", name="Default")
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

    c = TestClient(create_app())
    # Authenticate as admin — cookie attaches automatically.
    r = c.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "boss", "password": "bosspw"},
    )
    assert r.status_code == 200, r.text
    return c


def test_list_tenants(client):
    r = client.get("/api/admin/tenants")
    assert r.status_code == 200, r.text
    slugs = [t["slug"] for t in r.json()["tenants"]]
    assert "default" in slugs


def test_create_tenant(client):
    r = client.post("/api/admin/tenants", json={"slug": "gns-2026", "name": "GNS"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "gns-2026"
    assert body["name"] == "GNS"


def test_create_tenant_duplicate_slug_409(client):
    r = client.post("/api/admin/tenants", json={"slug": "default", "name": "Other"})
    assert r.status_code == 409


def test_create_tenant_invalid_slug_409(client):
    r = client.post("/api/admin/tenants", json={"slug": "UPPER", "name": "x"})
    assert r.status_code == 409


def test_create_user_in_tenant(client):
    r = client.post(
        "/api/admin/tenants/default/users",
        json={"username": "newbie", "password": "pw", "role": "curator"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "newbie"
    assert body["pseudonym"]  # auto-generated
    assert body["role"] == "curator"
    assert body["active"] is True


def test_create_user_with_custom_pseudonym(client):
    r = client.post(
        "/api/admin/tenants/default/users",
        json={
            "username": "newbie",
            "password": "pw",
            "pseudonym": "Listiger Fuchs",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["pseudonym"] == "Listiger Fuchs"


def test_create_user_rejects_email_pseudonym_409(client):
    r = client.post(
        "/api/admin/tenants/default/users",
        json={
            "username": "newbie",
            "password": "pw",
            "pseudonym": "hans@example.com",
        },
    )
    assert r.status_code == 409
    assert "E-Mail" in r.json()["detail"]


def test_create_user_duplicate_username_409(client):
    client.post(
        "/api/admin/tenants/default/users",
        json={"username": "dup", "password": "pw"},
    )
    r = client.post(
        "/api/admin/tenants/default/users",
        json={"username": "dup", "password": "pw"},
    )
    assert r.status_code == 409


def test_list_users_for_tenant(client):
    client.post(
        "/api/admin/tenants/default/users",
        json={"username": "a", "password": "pw"},
    )
    client.post(
        "/api/admin/tenants/default/users",
        json={"username": "b", "password": "pw"},
    )
    r = client.get("/api/admin/tenants/default/users")
    assert r.status_code == 200, r.text
    usernames = {u["username"] for u in r.json()["users"]}
    assert {"boss", "a", "b"}.issubset(usernames)


def test_list_users_unknown_tenant_404(client):
    r = client.get("/api/admin/tenants/missing/users")
    assert r.status_code == 404


def test_pseudonym_suggest(client):
    r = client.get("/api/admin/tenants/default/pseudonym-suggest")
    assert r.status_code == 200, r.text
    assert " " in r.json()["pseudonym"]  # Adjective + Animal


def test_deactivate_user(client):
    create_r = client.post(
        "/api/admin/tenants/default/users",
        json={"username": "to-remove", "password": "pw"},
    )
    user_id = create_r.json()["user_id"]
    r = client.delete(f"/api/admin/users/{user_id}")
    assert r.status_code == 204
    # Now listed as inactive (still present for audit).
    list_r = client.get("/api/admin/tenants/default/users")
    deactivated = next(u for u in list_r.json()["users"] if u["user_id"] == user_id)
    assert deactivated["active"] is False


def test_deactivate_unknown_user_404(client):
    r = client.delete("/api/admin/users/u-doesnt-exist")
    assert r.status_code == 404


def test_admin_routes_require_admin_role(tmp_path, monkeypatch):
    """Logging in as a curator must NOT grant admin-route access."""
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "legacy")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    with open_auth_db(root) as conn:
        ensure_schema(conn)
        tenant = create_tenant(conn, slug="default", name="Default")
        create_user(
            conn,
            tenant_id=tenant.tenant_id,
            username="curator",
            password="pw",
            role="curator",
        )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    c = TestClient(create_app())
    c.post(
        "/api/auth/login",
        json={"tenant_slug": "default", "username": "curator", "password": "pw"},
    )
    r = c.get("/api/admin/tenants")
    assert r.status_code == 403
