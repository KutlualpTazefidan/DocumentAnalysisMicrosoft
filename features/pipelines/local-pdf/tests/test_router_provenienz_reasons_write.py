"""Integration test: /decide with accepted=override appends to reasons.jsonl."""

from __future__ import annotations

import io

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.reasons import read_reasons
from local_pdf.storage.sidecar import write_mineru


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.setattr(router_mod, "_llm_extract_claims", lambda t, p, **_: ["LLM-Aussage A"])
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _setup_extract_proposal(client) -> tuple[str, str]:
    upload = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    slug = upload.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {"elements": [{"box_id": "p1-b0", "html_snippet": "<p>X</p>"}], "diagnostics": []},
    )
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk = next(n for n in detail["nodes"] if n["kind"] == "chunk")
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk["node_id"]},
    ).json()
    return sid, proposal["node_id"]


def test_override_with_reason_writes_to_corpus(client):
    sid, proposal_id = _setup_extract_proposal(client)
    cfg = client.app.state.config
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": proposal_id,
            "accepted": "override",
            "override": "Bessere Aussage 1; Bessere Aussage 2",
            "reason": "Heuristik hat zu viel Boilerplate übernommen",
        },
    )
    assert r.status_code == 201
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims")
    assert len(reasons) == 1
    rec = reasons[0]
    assert rec.session_id == sid
    assert rec.proposal_id == proposal_id
    assert rec.reason_text == "Heuristik hat zu viel Boilerplate übernommen"
    assert "Bessere Aussage" in rec.override_summary
    assert rec.actor == "human"


def test_recommended_does_not_write(client):
    sid, proposal_id = _setup_extract_proposal(client)
    cfg = client.app.state.config
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal_id, "accepted": "recommended"},
    )
    assert r.status_code == 201
    assert read_reasons(cfg.data_root) == []


def test_override_without_reason_does_not_write(client):
    sid, proposal_id = _setup_extract_proposal(client)
    cfg = client.app.state.config
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": proposal_id,
            "accepted": "override",
            "override": "Bessere Aussage 1",
            "reason": "",
        },
    )
    assert r.status_code == 201
    assert read_reasons(cfg.data_root) == []


def test_two_overrides_two_records(client):
    cfg = client.app.state.config
    sid1, p1 = _setup_extract_proposal(client)
    client.post(
        f"/api/admin/provenienz/sessions/{sid1}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": p1,
            "accepted": "override",
            "override": "ovr1",
            "reason": "grund1",
        },
    )
    sid2, p2 = _setup_extract_proposal(client)
    client.post(
        f"/api/admin/provenienz/sessions/{sid2}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": p2,
            "accepted": "override",
            "override": "ovr2",
            "reason": "grund2",
        },
    )
    out = read_reasons(cfg.data_root)
    assert [r.reason_text for r in out] == ["grund1", "grund2"]
