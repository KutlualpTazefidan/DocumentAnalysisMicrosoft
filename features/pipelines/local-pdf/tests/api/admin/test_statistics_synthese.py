"""Tests for /api/admin/statistics/synthese/{slug}.

Live-scan C1 endpoint — walks the per-doc ``golden_events_v1.jsonl`` to
compute curator-survival and vote-distribution. Vote-counting logic ships
now but is only exercised once vote events land (Task 13).
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


def _seed_synthese_doc(
    data_root: Path,
    slug: str,
    n_created: int = 5,
    n_deprecated: int = 1,
) -> None:
    (data_root / slug).mkdir(parents=True, exist_ok=True)
    (data_root / slug / "datasets").mkdir(parents=True, exist_ok=True)
    (data_root / slug / "mineru-out.json").write_text(
        json.dumps({"elements": [], "diagnostics": []})
    )
    events_path = data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    actor = HumanActor(pseudonym="reviewer-x", level="other")
    entry_ids: list[str] = []
    for _ in range(n_created):
        eid = new_entry_id()
        entry_ids.append(eid)
        append_event(
            events_path,
            Event(
                event_id=new_event_id(),
                timestamp_utc=now_utc_iso(),
                event_type="created",
                entry_id=eid,
                schema_version=1,
                payload={
                    "action": "synthesised",
                    "actor": actor.model_dump(mode="json"),
                    "entry_data": {
                        "task_type": "retrieval",
                        "query": "q?",
                        "expected_chunk_ids": [],
                        "chunk_hashes": {},
                    },
                },
            ),
        )
    for i in range(n_deprecated):
        append_event(
            events_path,
            Event(
                event_id=new_event_id(),
                timestamp_utc=now_utc_iso(),
                event_type="deprecated",
                entry_id=entry_ids[i],
                schema_version=1,
                payload={"actor": actor.model_dump(mode="json"), "reason": "test"},
            ),
        )


def test_synthese_stats_survival_rate(client, tmp_path):
    cfg = client.app.state.config
    _seed_synthese_doc(cfg.data_root, "doc-a")
    r = client.get("/api/admin/statistics/synthese/doc-a", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "doc-a"
    assert body["questions_created"] == 5
    assert body["questions_deprecated"] == 1
    assert body["survival_rate"] == pytest.approx(4 / 5)
    # No votes yet → zero counts, null rate, empty distribution.
    assert body["vote_approved"] == 0
    assert body["vote_rejected"] == 0
    assert body["vote_approval_rate"] is None
    assert body["vote_distribution"] == []


def test_synthese_stats_zero_created_returns_null_survival(client):
    cfg = client.app.state.config
    slug = "empty"
    (cfg.data_root / slug).mkdir(parents=True, exist_ok=True)
    (cfg.data_root / slug / "datasets").mkdir(parents=True, exist_ok=True)
    (cfg.data_root / slug / "mineru-out.json").write_text(
        json.dumps({"elements": [], "diagnostics": []})
    )
    r = client.get(f"/api/admin/statistics/synthese/{slug}", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["survival_rate"] is None
    assert body["vote_approval_rate"] is None


def test_synthese_stats_404_when_doc_missing(client):
    r = client.get("/api/admin/statistics/synthese/nonexistent", headers=AUTH)
    assert r.status_code == 404
