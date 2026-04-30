from __future__ import annotations


def test_auth_allows_correct_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _p() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-good"})
    assert resp.status_code == 200


def test_auth_rejects_missing_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _p() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/protected")
    assert resp.status_code == 401
    assert "missing or invalid" in resp.json()["detail"].lower()


def test_auth_rejects_wrong_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/protected")
    def _p() -> dict:
        return {"ok": True}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/protected", headers={"X-Auth-Token": "tok-bad"})
    assert resp.status_code == 401


def test_auth_lets_health_through() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/health")
    def _h() -> dict:
        return {"status": "ok"}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_auth_lets_source_pdf_through_with_token() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from local_pdf.api.auth import install_auth_middleware

    app = FastAPI()

    @app.get("/api/docs/{slug}/source.pdf")
    def _s(slug: str) -> dict:
        return {"slug": slug}

    install_auth_middleware(app, token="tok-good")
    client = TestClient(app)
    resp = client.get("/api/docs/bam/source.pdf", headers={"X-Auth-Token": "tok-good"})
    assert resp.status_code == 200
