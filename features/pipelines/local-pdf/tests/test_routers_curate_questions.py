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

    raw = "f" * 32
    write_curators(
        tmp_path,
        CuratorsFile(
            curators=[
                Curator(
                    id="c-w",
                    name="Dr W",
                    token_prefix=raw[-8:],
                    token_sha256=hash_token(raw),
                    assigned_slugs=["d1"],
                    created_at="t",
                    last_seen_at=None,
                    active=True,
                )
            ]
        ),
    )
    (tmp_path / "d1").mkdir()
    write_meta(
        tmp_path,
        "d1",
        DocMeta(
            slug="d1",
            filename="d1.pdf",
            pages=1,
            status=DocStatus.open_for_curation,
            last_touched_utc="t",
        ),
    )
    write_source_elements(
        tmp_path,
        "d1",
        {
            "doc_slug": "d1",
            "source_pipeline": "local-pdf",
            "elements": [
                {
                    "box_id": "p1-x",
                    "page": 1,
                    "kind": "paragraph",
                    "text": "Foo",
                    "bbox": [0, 0, 1, 1],
                }
            ],
        },
    )
    return TestClient(create_app()), raw


def test_post_question(env) -> None:
    client, raw = env
    r = client.post(
        "/api/curate/docs/d1/questions",
        headers={"X-Auth-Token": raw},
        json={"element_id": "p1-x", "query": "Was bedeutet Foo?"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["element_id"] == "p1-x"
    assert body["curator_id"] == "c-w"
    assert "question_id" in body


def test_post_question_unknown_element(env) -> None:
    client, raw = env
    r = client.post(
        "/api/curate/docs/d1/questions",
        headers={"X-Auth-Token": raw},
        json={"element_id": "nope", "query": "?"},
    )
    assert r.status_code == 404
