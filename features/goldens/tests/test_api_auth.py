from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def test_auth_middleware_allows_correct_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok-good")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _protected() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-good"})
    assert resp.status_code == 200


def test_auth_middleware_rejects_missing_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _protected() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/protected")
    assert resp.status_code == 401
    assert "missing or invalid" in resp.json()["detail"].lower()


def test_auth_middleware_rejects_wrong_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _protected() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-bad"})
    assert resp.status_code == 401


def test_auth_middleware_lets_health_through() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from goldens.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/health")
    def _health() -> dict:
        return {"status": "ok"}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    resp = client.get("/api/health")  # no X-Auth-Token header
    assert resp.status_code == 200


def test_auth_middleware_lets_docs_through() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from goldens.api.auth import install_auth_middleware

    app = FastAPI()
    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)

    # /docs is built into FastAPI; the Swagger UI HTML must load without auth.
    resp = client.get("/docs")
    assert resp.status_code == 200
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
