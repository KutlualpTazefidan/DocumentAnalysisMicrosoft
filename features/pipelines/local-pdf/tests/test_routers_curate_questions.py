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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _create_question(client, raw: str, query: str = "Was bedeutet Foo?") -> str:
    r = client.post(
        "/api/curate/docs/d1/questions",
        headers={"X-Auth-Token": raw},
        json={"element_id": "p1-x", "query": query},
    )
    assert r.status_code == 201
    return r.json()["question_id"]


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_questions_empty(env) -> None:
    client, raw = env
    r = client.get("/api/curate/docs/d1/questions", headers={"X-Auth-Token": raw})
    assert r.status_code == 200
    assert r.json() == []


def test_list_questions_returns_created(env) -> None:
    client, raw = env
    qid = _create_question(client, raw)
    r = client.get("/api/curate/docs/d1/questions", headers={"X-Auth-Token": raw})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["question_id"] == qid
    assert body[0]["query"] == "Was bedeutet Foo?"


def test_list_questions_filter_element_id(env) -> None:
    client, raw = env
    _create_question(client, raw, "Frage A")
    r = client.get(
        "/api/curate/docs/d1/questions?element_id=p1-x",
        headers={"X-Auth-Token": raw},
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    r2 = client.get(
        "/api/curate/docs/d1/questions?element_id=nope",
        headers={"X-Auth-Token": raw},
    )
    assert r2.status_code == 200
    assert r2.json() == []


# ---------------------------------------------------------------------------
# refine
# ---------------------------------------------------------------------------


def test_refine_question(env) -> None:
    client, raw = env
    qid = _create_question(client, raw)
    r = client.post(
        f"/api/curate/docs/d1/questions/{qid}/refine",
        headers={"X-Auth-Token": raw},
        json={"query": "Verfeinerte Frage?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["question_id"] == qid
    assert body["refined_query"] == "Verfeinerte Frage?"


def test_refine_question_not_found(env) -> None:
    client, raw = env
    r = client.post(
        "/api/curate/docs/d1/questions/q-notexist/refine",
        headers={"X-Auth-Token": raw},
        json={"query": "irgendetwas"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# deprecate
# ---------------------------------------------------------------------------


def test_deprecate_question(env) -> None:
    client, raw = env
    qid = _create_question(client, raw)
    r = client.post(
        f"/api/curate/docs/d1/questions/{qid}/deprecate",
        headers={"X-Auth-Token": raw},
        json={"reason": "Duplikat"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["deprecated"] is True
    assert body["deprecated_reason"] == "Duplikat"


def test_deprecate_question_no_reason(env) -> None:
    client, raw = env
    qid = _create_question(client, raw)
    r = client.post(
        f"/api/curate/docs/d1/questions/{qid}/deprecate",
        headers={"X-Auth-Token": raw},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["deprecated"] is True
    assert body["deprecated_reason"] is None


def test_deprecate_question_not_found(env) -> None:
    client, raw = env
    r = client.post(
        "/api/curate/docs/d1/questions/q-notexist/deprecate",
        headers={"X-Auth-Token": raw},
        json={},
    )
    assert r.status_code == 404
