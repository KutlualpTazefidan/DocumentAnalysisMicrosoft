from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOLDENS_API_TOKEN", "ADMIN")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def test_features_public(client) -> None:
    r = client.get("/api/_features")
    assert r.status_code == 200
    body = r.json()
    assert "roles" in body
    assert set(body["roles"]) == {"admin", "curator"}
    assert isinstance(body.get("features"), list)


def test_auth_check_admin(client) -> None:
    r = client.post("/api/auth/check", json={"token": "ADMIN"})
    assert r.status_code == 200
    assert r.json() == {"role": "admin", "name": "admin"}


def test_auth_check_curator(client, tmp_path) -> None:
    from local_pdf.api.schemas import Curator, CuratorsFile
    from local_pdf.storage.curators import hash_token, write_curators

    raw = "f" * 32
    write_curators(
        tmp_path,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-1",
                    name="Dr X",
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
    r = client.post("/api/auth/check", json={"token": raw})
    assert r.status_code == 200
    assert r.json() == {"role": "curator", "name": "Dr X"}


def test_auth_check_invalid(client) -> None:
    r = client.post("/api/auth/check", json={"token": "nope"})
    assert r.status_code == 401
