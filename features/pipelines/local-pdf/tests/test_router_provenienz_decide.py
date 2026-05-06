import io

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.storage.sidecar import write_mineru


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.setattr(
        router_mod,
        "_llm_extract_claims",
        lambda chunk_text, provider, **_: [
            "Gesamtwärmeleistung beträgt 5.6 kW",
            "Die Baugruppe ist X",
        ],
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _propose(client) -> tuple[str, str, str]:
    """Returns (session_id, chunk_node_id, proposal_node_id) for a session
    that already has one extract_claims proposal queued."""
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
        {"elements": [{"box_id": "p1-b0", "html_snippet": "<p>X.</p>"}], "diagnostics": []},
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
    return sid, chunk["node_id"], proposal["node_id"]


def test_decide_recommended_spawns_two_claim_nodes(client):
    sid, chunk_id, prop_id = _propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": prop_id, "accepted": "recommended"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["decision_node"]["kind"] == "decision"
    assert body["decision_node"]["payload"]["accepted"] == "recommended"
    assert len(body["spawned_nodes"]) == 2
    assert all(n["kind"] == "claim" for n in body["spawned_nodes"])
    assert {n["payload"]["text"] for n in body["spawned_nodes"]} == {
        "Gesamtwärmeleistung beträgt 5.6 kW",
        "Die Baugruppe ist X",
    }

    # Edges shapes:
    edges = body["spawned_edges"]
    edge_kinds = {e["kind"] for e in edges}
    assert "extracts-from" in edge_kinds
    assert "decided-by" in edge_kinds
    assert "triggers" in edge_kinds

    # extracts-from goes claim → chunk
    extracts = [e for e in edges if e["kind"] == "extracts-from"]
    assert all(e["to_node"] == chunk_id for e in extracts)

    # decided-by goes decision → proposal (single)
    decided = [e for e in edges if e["kind"] == "decided-by"]
    assert len(decided) == 1
    assert decided[0]["to_node"] == prop_id


def test_decide_override_spawns_single_claim_with_freeform_text(client):
    sid, _chunk, prop_id = _propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": prop_id,
            "accepted": "override",
            "override": "Eigene Aussage manuell",
            "reason": "der Stub hat eine wichtige Aussage übersehen",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    claims = [n for n in body["spawned_nodes"] if n["kind"] == "claim"]
    assert len(claims) == 1
    assert claims[0]["payload"]["text"] == "Eigene Aussage manuell"
    assert claims[0]["actor"] == "human"
    # Decision payload carries the reason verbatim.
    assert body["decision_node"]["payload"]["reason"] == (
        "der Stub hat eine wichtige Aussage übersehen"
    )
    assert body["decision_node"]["payload"]["override"] == "Eigene Aussage manuell"


def test_decide_alt_uses_alternative_index(client):
    sid, _chunk, prop_id = _propose(client)
    # alt_index 0 = the "skip" alternative whose args.claims == []
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": prop_id, "accepted": "alt", "alt_index": 0},
    )
    assert r.status_code == 201
    body = r.json()
    claims = [n for n in body["spawned_nodes"] if n["kind"] == "claim"]
    assert len(claims) == 0  # skip → no claims spawned
    # But the decision node IS persisted, plus the decided-by edge.
    assert body["decision_node"]["payload"]["accepted"] == "alt"
    assert body["decision_node"]["payload"]["alt_index"] == 0
    assert any(e["kind"] == "decided-by" for e in body["spawned_edges"])


def test_decide_override_without_text_returns_400(client):
    sid, _chunk, prop_id = _propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": prop_id, "accepted": "override"},
    )
    assert r.status_code == 400


def test_decide_404_when_proposal_missing(client):
    sid, _chunk, _prop_id = _propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": "missing-id", "accepted": "recommended"},
    )
    assert r.status_code == 404


def test_decide_400_when_anchor_not_action_proposal(client):
    sid, chunk_id, _prop_id = _propose(client)
    # Feed the chunk node id instead of an action_proposal — should reject.
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": chunk_id, "accepted": "recommended"},
    )
    # 400 or 404 acceptable; route should not crash.
    assert r.status_code in (400, 404)


def test_decide_persists_decision_and_edges_in_event_log(client):
    sid, _chunk_id, prop_id = _propose(client)
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": prop_id, "accepted": "recommended"},
    )
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    decisions = [n for n in detail["nodes"] if n["kind"] == "decision"]
    claims = [n for n in detail["nodes"] if n["kind"] == "claim"]
    assert len(decisions) == 1
    assert len(claims) == 2
    # Edges land in the file too.
    edge_kinds = {e["kind"] for e in detail["edges"]}
    assert {"extracts-from", "decided-by", "triggers"} <= edge_kinds
