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


def test_lookup_admin_token(tmp_path):
    from local_pdf.api.auth import lookup_token

    ident = lookup_token(tmp_path, "ADMIN-TOK", admin_token="ADMIN-TOK")
    assert ident is not None
    assert ident.role == "admin"
    assert ident.name == "admin"
    assert ident.curator_id is None


def test_lookup_curator_token(tmp_path):
    from local_pdf.api.auth import lookup_token
    from local_pdf.api.schemas import Curator, CuratorsFile
    from local_pdf.storage.curators import hash_token, write_curators

    raw = "deadbeefcafebabe1234567890abcdef"
    write_curators(
        tmp_path,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-zz",
                    name="Dr Curator",
                    token_prefix=raw[-8:],
                    token_sha256=hash_token(raw),
                    assigned_slugs=[],
                    created_at="t",
                    last_seen_at=None,
                    active=True,
                )
            ]
        ),
    )
    ident = lookup_token(tmp_path, raw, admin_token="ADMIN-TOK")
    assert ident is not None
    assert ident.role == "curator"
    assert ident.name == "Dr Curator"
    assert ident.curator_id == "c-zz"


def test_lookup_unknown(tmp_path):
    from local_pdf.api.auth import lookup_token

    assert lookup_token(tmp_path, "nope", admin_token="ADMIN-TOK") is None


def test_curator_blocked_from_admin_route(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import Curator, CuratorsFile
    from local_pdf.storage.curators import hash_token, write_curators

    monkeypatch.setenv("GOLDENS_API_TOKEN", "ADMIN")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path))
    raw = "0" * 32
    write_curators(
        tmp_path,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-q",
                    name="C",
                    token_prefix=raw[-8:],
                    token_sha256=hash_token(raw),
                    assigned_slugs=[],
                    created_at="t",
                    last_seen_at=None,
                    active=True,
                )
            ]
        ),
    )
    client = TestClient(create_app())
    r = client.get("/api/admin/docs", headers={"X-Auth-Token": raw})
    assert r.status_code == 403
    assert r.json()["detail"] == "admin role required"
