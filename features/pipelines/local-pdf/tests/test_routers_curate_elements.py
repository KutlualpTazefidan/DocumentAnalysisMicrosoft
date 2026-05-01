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
    from local_pdf.storage.sidecar import write_meta, write_source_elements

    raw = "e" * 32
    write_curators(
        tmp_path,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-z",
                    name="Dr Z",
                    token_prefix=raw[-8:],
                    token_sha256=hash_token(raw),
                    assigned_slugs=["specx"],
                    created_at="t",
                    last_seen_at=None,
                    active=True,
                )
            ]
        ),
    )
    (tmp_path / "specx").mkdir()
    write_meta(
        tmp_path,
        "specx",
        DocMeta(
            slug="specx",
            filename="x.pdf",
            pages=1,
            status=DocStatus.open_for_curation,
            last_touched_utc="t",
        ),
    )
    write_source_elements(
        tmp_path,
        "specx",
        {
            "doc_slug": "specx",
            "source_pipeline": "local-pdf",
            "elements": [
                {
                    "box_id": "p1-aa",
                    "page": 1,
                    "kind": "paragraph",
                    "text": "Hello world",
                    "bbox": [0, 0, 10, 10],
                },
                {
                    "box_id": "p1-bb",
                    "page": 1,
                    "kind": "heading",
                    "text": "Title",
                    "bbox": [0, 20, 10, 30],
                },
            ],
        },
    )
    return TestClient(create_app()), raw


def test_list_elements(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs/specx/elements", headers={"X-Auth-Token": raw})
    assert r.status_code == 200
    eids = [e["element_id"] for e in r.json()]
    assert eids == ["p1-aa", "p1-bb"]


def test_get_element(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs/specx/elements/p1-aa", headers={"X-Auth-Token": raw})
    assert r.status_code == 200
    assert r.json()["content"] == "Hello world"


def test_get_unknown_element(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs/specx/elements/nope", headers={"X-Auth-Token": raw})
    assert r.status_code == 404
