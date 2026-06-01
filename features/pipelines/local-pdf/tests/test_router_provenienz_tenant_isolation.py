"""End-to-end test: provenienz sessions stay isolated per tenant.

Two cookie-mode users in distinct tenants spawn sessions on the same
slug. Each tenant's list_sessions must return only its own session
ids — no cross-tenant leakage.
"""

from __future__ import annotations

import io

import pytest
from local_pdf.auth.db import ensure_schema, open_auth_db
from local_pdf.auth.tenants import create_tenant
from local_pdf.auth.users import create_user
from local_pdf.storage.sidecar import write_mineru


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "legacy-admin-token")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    # Two tenants, one admin user each.
    with open_auth_db(root) as conn:
        ensure_schema(conn)
        t_alpha = create_tenant(conn, slug="alpha", name="Alpha")
        t_beta = create_tenant(conn, slug="beta", name="Beta")
        create_user(
            conn,
            tenant_id=t_alpha.tenant_id,
            username="boss",
            password="pw",
            role="admin",
            pseudonym="Klarer Wolf",
        )
        create_user(
            conn,
            tenant_id=t_beta.tenant_id,
            username="boss",
            password="pw",
            role="admin",
            pseudonym="Stiller Fuchs",
        )
    return root


def _client_login(root, tenant_slug):
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    client = TestClient(create_app())
    r = client.post(
        "/api/auth/login",
        json={"tenant_slug": tenant_slug, "username": "boss", "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return client


def _seed_doc(client, slug: str = "shared-doc") -> str:
    """Upload a stub PDF + write mineru data so the create-session
    handler finds a valid chunk."""
    upload = client.post(
        "/api/admin/docs",
        files={"file": (f"{slug}.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    assert upload.status_code in (200, 201), upload.text
    slug_actual = upload.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug_actual,
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>Hello world.</p>"},
            ],
            "diagnostics": [],
        },
    )
    return slug_actual


def test_two_tenants_do_not_see_each_others_sessions(setup):
    """Each tenant spawns its own session on the shared slug; the
    list endpoint must return only the caller's own sessions."""
    # Tenant alpha: upload + create session.
    alpha = _client_login(setup, "alpha")
    slug = _seed_doc(alpha)
    r_alpha = alpha.post(
        "/api/admin/provenienz/sessions",
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    )
    assert r_alpha.status_code == 201, r_alpha.text
    sid_alpha = r_alpha.json()["session_id"]

    # Tenant beta: own session on the same slug.
    beta = _client_login(setup, "beta")
    r_beta = beta.post(
        "/api/admin/provenienz/sessions",
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    )
    assert r_beta.status_code == 201, r_beta.text
    sid_beta = r_beta.json()["session_id"]

    assert sid_alpha != sid_beta

    # alpha lists -> only alpha's session.
    alpha_list = alpha.get("/api/admin/provenienz/sessions").json()
    alpha_ids = {s["session_id"] for s in alpha_list}
    assert sid_alpha in alpha_ids
    assert sid_beta not in alpha_ids

    # beta lists -> only beta's session.
    beta_list = beta.get("/api/admin/provenienz/sessions").json()
    beta_ids = {s["session_id"] for s in beta_list}
    assert sid_beta in beta_ids
    assert sid_alpha not in beta_ids


def test_tenant_cannot_get_other_tenants_session(setup):
    """Direct GET by session_id must 404 when the caller is in a
    different tenant — no path-traversal escape."""
    alpha = _client_login(setup, "alpha")
    slug = _seed_doc(alpha)
    sid_alpha = alpha.post(
        "/api/admin/provenienz/sessions",
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]

    beta = _client_login(setup, "beta")
    r = beta.get(f"/api/admin/provenienz/sessions/{sid_alpha}")
    assert r.status_code == 404
