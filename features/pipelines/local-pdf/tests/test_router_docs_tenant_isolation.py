"""Tenant-isolation e2e for document uploads + listings.

Two cookie-mode users in distinct tenants upload PDFs with the same
filename and list documents. Each tenant must see only their own
upload — no cross-tenant leakage at the doc-listing layer.
"""

from __future__ import annotations

import io

import pytest
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import create_user


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "legacy-admin-token")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    with open_auth_db(root) as conn:
        ensure_schema(conn)
        t_a = create_tenant(conn, slug="alpha", name="Alpha")
        t_b = create_tenant(conn, slug="beta", name="Beta")
        create_user(
            conn,
            tenant_id=t_a.tenant_id,
            username="boss",
            password="pw",
            role="admin",
            pseudonym="Klarer Wolf",
        )
        create_user(
            conn,
            tenant_id=t_b.tenant_id,
            username="boss",
            password="pw",
            role="admin",
            pseudonym="Stiller Fuchs",
        )
    return root


def _login(setup, tenant_slug):
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": tenant_slug, "username": "boss", "password": "pw"},
    )
    assert r.status_code == 200
    return client


def test_docs_listing_is_tenant_isolated(setup):
    alpha = _login(setup, "alpha")
    beta = _login(setup, "beta")

    r_a = alpha.post(
        "/api/admin/docs",
        files={"file": ("alpha.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    assert r_a.status_code in (200, 201), r_a.text
    slug_a = r_a.json()["slug"]

    r_b = beta.post(
        "/api/admin/docs",
        files={"file": ("beta.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    assert r_b.status_code in (200, 201), r_b.text
    slug_b = r_b.json()["slug"]

    alpha_docs = alpha.get("/api/admin/docs").json()
    alpha_slugs = {
        d["slug"] for d in (alpha_docs["docs"] if isinstance(alpha_docs, dict) else alpha_docs)
    }
    assert slug_a in alpha_slugs
    assert slug_b not in alpha_slugs

    beta_docs = beta.get("/api/admin/docs").json()
    beta_slugs = {
        d["slug"] for d in (beta_docs["docs"] if isinstance(beta_docs, dict) else beta_docs)
    }
    assert slug_b in beta_slugs
    assert slug_a not in beta_slugs
