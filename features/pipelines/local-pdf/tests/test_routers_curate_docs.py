from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOLDENS_API_TOKEN", "ADMIN")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app
    from local_pdf.api.schemas import Curator, CuratorsFile, DocMeta, DocStatus
    from local_pdf.storage.curators import hash_token, write_curators
    from local_pdf.storage.sidecar import write_meta

    raw = "c" * 32
    write_curators(
        tmp_path,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-q",
                    name="Dr Q",
                    token_prefix=raw[-8:],
                    token_sha256=hash_token(raw),
                    assigned_slugs=["spec-a", "spec-b"],
                    created_at="t",
                    last_seen_at=None,
                    active=True,
                )
            ]
        ),
    )
    for slug, status in [
        ("spec-a", DocStatus.open_for_curation),
        ("spec-b", DocStatus.extracted),  # assigned but not yet published
        ("spec-c", DocStatus.open_for_curation),  # published but not assigned
    ]:
        (tmp_path / slug).mkdir()
        write_meta(
            tmp_path,
            slug,
            DocMeta(
                slug=slug,
                filename=f"{slug}.pdf",
                pages=1,
                status=status,
                last_touched_utc="t",
            ),
        )
    return TestClient(create_app()), raw


def test_curator_sees_only_assigned_and_published(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs", headers={"X-Auth-Token": raw})
    assert r.status_code == 200
    slugs = [d["slug"] for d in r.json()]
    assert slugs == ["spec-a"]


def test_admin_blocked_from_curate_route(env) -> None:
    client, _ = env
    r = client.get("/api/curate/docs", headers={"X-Auth-Token": "ADMIN"})
    assert r.status_code == 403


def test_curator_get_assigned_doc(env) -> None:
    from local_pdf.storage.sidecar import write_html

    client, raw = env
    write_html(client.app.state.config.data_root, "spec-a", "<p>body</p>")

    r = client.get("/api/curate/docs/spec-a", headers={"X-Auth-Token": raw})
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "spec-a"
    assert body["html"] == "<p>body</p>"


def test_curator_404_on_unassigned_doc(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs/spec-c", headers={"X-Auth-Token": raw})
    assert r.status_code == 404


def test_curator_404_on_unpublished_assigned_doc(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs/spec-b", headers={"X-Auth-Token": raw})
    assert r.status_code == 404
