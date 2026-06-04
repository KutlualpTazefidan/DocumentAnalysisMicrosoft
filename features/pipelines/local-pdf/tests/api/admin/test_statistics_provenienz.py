from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from local_pdf.provenienz.storage import Node, append_node

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


def _seed_session(data_root: Path, slug: str, session_id: str, nodes: list[Node]) -> None:
    doc_dir = data_root / slug
    doc_dir.mkdir(parents=True, exist_ok=True)
    sd = doc_dir / "provenienz" / session_id
    sd.mkdir(parents=True, exist_ok=True)
    for n in nodes:
        append_node(sd, n)


def test_provenienz_stats_counts_overrides(client):
    cfg = client.app.state.config
    _seed_session(
        cfg.data_root,
        "doc-a",
        "s1",
        [
            Node(node_id="n1", session_id="s1", kind="plan_proposal", payload={}, actor="agent"),
            Node(node_id="n2", session_id="s1", kind="plan_proposal", payload={}, actor="agent"),
            Node(
                node_id="n3",
                session_id="s1",
                kind="expert_step_override",
                payload={},
                actor="human",
            ),
        ],
    )
    r = client.get("/api/admin/statistics/provenienz/doc-a", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan_proposals"] == 2
    assert body["expert_overrides"] == 1
    assert body["correction_rate"] == pytest.approx(0.5)


def test_provenienz_stats_zero_proposals_returns_null_rate(client):
    cfg = client.app.state.config
    (cfg.data_root / "empty").mkdir()
    r = client.get("/api/admin/statistics/provenienz/empty", headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["plan_proposals"] == 0
    assert body["expert_overrides"] == 0
    assert body["correction_rate"] is None


def test_provenienz_stats_404_when_doc_missing(client):
    r = client.get("/api/admin/statistics/provenienz/nonexistent", headers=AUTH)
    assert r.status_code == 404


def test_capability_wishes_endpoint_returns_skill_buckets(client):
    cfg = client.app.state.config
    _seed_session(
        cfg.data_root,
        "doc-a",
        "s1",
        [
            Node(
                node_id="n1",
                session_id="s1",
                kind="capability_request",
                payload={"name": "RegisterLookup", "description": ""},
                actor="agent",
            ),
            Node(
                node_id="n2",
                session_id="s1",
                kind="capability_request",
                payload={"name": "RegisterMatch", "description": ""},
                actor="agent",
            ),
        ],
    )
    r = client.get("/api/admin/statistics/capability-wishes", headers=AUTH)
    assert r.status_code == 200, r.text
    wishes = r.json()["wishes"]
    names = {w["name"] for w in wishes}
    assert {"RegisterLookup", "RegisterMatch"} <= names
    for w in wishes:
        assert w["skill_bucket"] == "register"
