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
