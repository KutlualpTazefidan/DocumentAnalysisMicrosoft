from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def _make():
        root = tmp_path / "raw-pdfs"
        root.mkdir()
        monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-test")
        monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
        from local_pdf.api.app import create_app

        return create_app(), root

    return _make


def test_health_no_auth_required(make_app) -> None:
    from fastapi.testclient import TestClient

    app, root = make_app()
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data_root"] == str(root)


def test_unknown_route_returns_404(make_app) -> None:
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/nope", headers={"X-Auth-Token": "tok-test"})
    assert resp.status_code == 404


def test_protected_routes_require_token(make_app) -> None:
    from fastapi.testclient import TestClient

    app, _ = make_app()
    client = TestClient(app)
    resp = client.get("/api/docs")
    assert resp.status_code == 401


def test_app_includes_admin_routes_only() -> None:
    import os

    os.environ["GOLDENS_API_TOKEN"] = "tok"
    from local_pdf.api.app import create_app

    app = create_app()
    paths = {r.path for r in app.routes}
    # admin routes present
    assert "/api/admin/docs" in paths
    assert "/api/admin/docs/{slug}" in paths
    assert "/api/admin/docs/{slug}/segments" in paths
    assert "/api/admin/docs/{slug}/extract" in paths
    # legacy routes are gone-shimmed (still in routes dict via wildcard)
    # but the bare /api/docs handler is the gone shim, not the docs handler
    legacy = [r for r in app.routes if getattr(r, "path", "") == "/api/docs"]
    assert len(legacy) >= 1
