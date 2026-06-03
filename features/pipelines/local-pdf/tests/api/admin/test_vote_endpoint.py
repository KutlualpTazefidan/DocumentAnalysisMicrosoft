"""Tests for the vote POST endpoint and vote_summary on GET /questions.

Task 13: ``/api/admin/docs/{slug}/questions/{question_id}/vote`` appends a
``reviewed`` event with ``payload.action in {approved, rejected, revoked}``
and the existing ``GET /questions`` enriches each question with a
``vote_summary`` containing per-entry counts plus the requesting user's
current ``my_vote``. ``revoked`` toggles a previous vote off without
contributing to either count.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from goldens.operations._time import now_utc_iso
from goldens.schemas.base import Event, HumanActor
from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
from goldens.storage.ids import new_entry_id, new_event_id
from goldens.storage.log import append_event

if TYPE_CHECKING:
    from pathlib import Path


AUTH = {"X-Auth-Token": "tok"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    root = tmp_path / "raw-pdfs"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _seed_synthese_question(data_root: Path, slug: str) -> str:
    """Seed a doc with one synthesised question and return its entry_id."""
    doc_dir = data_root / slug
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "datasets").mkdir(parents=True, exist_ok=True)
    (doc_dir / "mineru-out.json").write_text(json.dumps({"elements": [], "diagnostics": []}))
    (doc_dir / "segments.json").write_text(json.dumps({"slug": slug, "boxes": []}))
    events_path = doc_dir / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    actor = HumanActor(pseudonym="curator-x", level="other")
    entry_id = new_entry_id()
    append_event(
        events_path,
        Event(
            event_id=new_event_id(),
            timestamp_utc=now_utc_iso(),
            event_type="created",
            entry_id=entry_id,
            schema_version=1,
            payload={
                "task_type": "retrieval",
                "action": "synthesised",
                "actor": actor.model_dump(mode="json"),
                "entry_data": {
                    "query": "Was ist X?",
                    "expected_chunk_ids": [],
                    "chunk_hashes": {},
                    "source_element": {
                        "document_id": slug,
                        "page_number": 1,
                        "element_id": "elem-1",
                        "element_type": "paragraph",
                    },
                },
            },
        ),
    )
    return entry_id


def test_vote_endpoint_appends_event(client, tmp_path):
    cfg = client.app.state.config
    entry_id = _seed_synthese_question(cfg.data_root, "doc-a")
    r = client.post(
        f"/api/admin/docs/doc-a/questions/{entry_id}/vote",
        json={"action": "approved"},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["event_type"] == "reviewed"
    assert body["payload"]["action"] == "approved"


def test_questions_get_includes_vote_summary(client, tmp_path):
    cfg = client.app.state.config
    entry_id = _seed_synthese_question(cfg.data_root, "doc-a")
    client.post(
        f"/api/admin/docs/doc-a/questions/{entry_id}/vote",
        json={"action": "approved"},
        headers=AUTH,
    )
    r = client.get("/api/admin/docs/doc-a/questions", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    q = next(iter(body.values()))[0]
    assert q["vote_summary"]["approved_count"] == 1
    assert q["vote_summary"]["rejected_count"] == 0
    # The X-Auth-Token admin path resolves identity.pseudonym = "admin",
    # so the POST writes actor.pseudonym = "admin" and the subsequent
    # GET (same identity) sees its own vote in ``my_vote``.
    assert q["vote_summary"]["my_vote"] == "approved"


def test_toggle_off_via_revoked(client, tmp_path):
    cfg = client.app.state.config
    entry_id = _seed_synthese_question(cfg.data_root, "doc-a")
    client.post(
        f"/api/admin/docs/doc-a/questions/{entry_id}/vote",
        json={"action": "approved"},
        headers=AUTH,
    )
    client.post(
        f"/api/admin/docs/doc-a/questions/{entry_id}/vote",
        json={"action": "revoked"},
        headers=AUTH,
    )
    r = client.get("/api/admin/docs/doc-a/questions", headers=AUTH)
    q = next(iter(r.json().values()))[0]
    assert q["vote_summary"]["approved_count"] == 0
    assert q["vote_summary"]["my_vote"] is None
