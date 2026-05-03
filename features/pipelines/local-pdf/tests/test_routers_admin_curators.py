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


def test_create_curator_returns_full_token_once(client) -> None:
    r = client.post(
        "/api/admin/curators",
        headers={"X-Auth-Token": "ADMIN"},
        json={"name": "Dr X"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Dr X"
    assert len(body["token"]) == 32
    assert body["id"].startswith("c-")
    assert body["token_prefix"] == body["token"][-8:]

    # second list call: token NOT returned
    listr = client.get("/api/admin/curators", headers={"X-Auth-Token": "ADMIN"})
    cur = listr.json()[0]
    assert "token" not in cur
    assert cur["token_prefix"] == body["token_prefix"]


def test_revoke_curator(client) -> None:
    cr = client.post(
        "/api/admin/curators",
        headers={"X-Auth-Token": "ADMIN"},
        json={"name": "Dr Y"},
    )
    cid = cr.json()["id"]
    r = client.delete(f"/api/admin/curators/{cid}", headers={"X-Auth-Token": "ADMIN"})
    assert r.status_code == 204
    listr = client.get("/api/admin/curators", headers={"X-Auth-Token": "ADMIN"})
    assert listr.json() == []


def test_assign_curator_to_doc(client, tmp_path) -> None:
    from local_pdf.api.schemas import DocMeta, DocStatus
    from local_pdf.storage.sidecar import write_meta

    (tmp_path / "doc1").mkdir()
    write_meta(
        tmp_path,
        "doc1",
        DocMeta(
            slug="doc1",
            filename="x.pdf",
            pages=1,
            status=DocStatus.open_for_curation,
            last_touched_utc="t",
        ),
    )
    cr = client.post(
        "/api/admin/curators",
        headers={"X-Auth-Token": "ADMIN"},
        json={"name": "Dr Z"},
    )
    cid = cr.json()["id"]
    r = client.post(
        "/api/admin/docs/doc1/curators",
        headers={"X-Auth-Token": "ADMIN"},
        json={"curator_id": cid},
    )
    assert r.status_code == 200
    g = client.get("/api/admin/docs/doc1/curators", headers={"X-Auth-Token": "ADMIN"})
    assert {c["id"] for c in g.json()} == {cid}


def test_curator_role_blocked_from_admin_curators(client) -> None:
    from local_pdf.api.schemas import Curator, CuratorsFile
    from local_pdf.storage.curators import hash_token, write_curators

    raw = "1" * 32
    write_curators(
        client.app.state.config.data_root,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-1",
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
    r = client.get("/api/admin/curators", headers={"X-Auth-Token": raw})
    assert r.status_code == 403
