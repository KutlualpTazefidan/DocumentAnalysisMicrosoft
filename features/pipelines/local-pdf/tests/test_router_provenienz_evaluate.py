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
    monkeypatch.setattr(router_mod, "_llm_extract_claims", lambda t, p, **_: ["Wärmeleistung X"])
    monkeypatch.setattr(router_mod, "_llm_formulate_task", lambda c, p, **_: "Wärmeleistung")
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate",
        lambda c, ch, p, **_: {
            "verdict": "likely-source",
            "confidence": 0.78,
            "reasoning": "Tabelle enthält genau diesen Wert.",
        },
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _setup_search_result(client) -> tuple[str, str, str]:
    """Returns (session_id, search_result_node_id, claim_node_id)."""
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
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>Anlage Wärmeleistung</p>"},
                {"box_id": "p2-b0", "html_snippet": "<p>Tabelle Wärmeleistung 5.6 kW</p>"},
            ],
            "diagnostics": [],
        },
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
    p1 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk["node_id"]},
    ).json()
    d1 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p1["node_id"], "accepted": "recommended"},
    ).json()
    claim_id = d1["spawned_nodes"][0]["node_id"]
    p2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": claim_id},
    ).json()
    d2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p2["node_id"], "accepted": "recommended"},
    ).json()
    task_id = d2["spawned_nodes"][0]["node_id"]
    p3 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/search",
        headers={"X-Auth-Token": "tok"},
        json={"task_node_id": task_id, "top_k": 5},
    ).json()
    d3 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p3["node_id"], "accepted": "recommended"},
    ).json()
    sr_id = d3["spawned_nodes"][0]["node_id"]
    return sid, sr_id, claim_id


def test_evaluate_emits_action_proposal_with_verdict(client):
    sid, sr_id, claim_id = _setup_search_result(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id, "against_claim_id": claim_id},
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["step_kind"] == "evaluate"
    assert p["anchor_node_id"] == sr_id
    assert p["recommended"]["args"]["verdict"] == "likely-source"
    assert p["recommended"]["args"]["confidence"] == 0.78
    assert p["recommended"]["args"]["against_claim_id"] == claim_id


def test_decide_evaluate_recommended_spawns_evaluation(client):
    sid, sr_id, claim_id = _setup_search_result(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id, "against_claim_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    )
    assert r.status_code == 201
    body = r.json()
    evals = [n for n in body["spawned_nodes"] if n["kind"] == "evaluation"]
    assert len(evals) == 1
    assert evals[0]["payload"]["verdict"] == "likely-source"
    assert evals[0]["payload"]["confidence"] == 0.78
    assert evals[0]["payload"]["search_result_node_id"] == sr_id
    assert evals[0]["payload"]["against_claim_id"] == claim_id
    edge_kinds = {e["kind"] for e in body["spawned_edges"]}
    assert "evaluates" in edge_kinds
    assert "triggers" in edge_kinds


def test_decide_evaluate_alt_uses_not_source(client):
    sid, sr_id, claim_id = _setup_search_result(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id, "against_claim_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "alt", "alt_index": 0},
    )
    assert r.status_code == 201
    evals = [n for n in r.json()["spawned_nodes"] if n["kind"] == "evaluation"]
    assert evals[0]["payload"]["verdict"] == "not-source"


def test_decide_evaluate_override_captures_freeform_reasoning(client):
    sid, sr_id, claim_id = _setup_search_result(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id, "against_claim_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": proposal["node_id"],
            "accepted": "override",
            "override": "Tabelle Spalte 3 ergibt 5.6 kW",
            "reason": "LLM-Bewertung war zu vage",
        },
    )
    assert r.status_code == 201
    evals = [n for n in r.json()["spawned_nodes"] if n["kind"] == "evaluation"]
    assert evals[0]["payload"]["reasoning"] == "Tabelle Spalte 3 ergibt 5.6 kW"
    assert evals[0]["payload"]["verdict"] == "manual"
    assert evals[0]["actor"] == "human"


def test_evaluate_404_when_search_result_missing(client):
    sid, _sr, claim_id = _setup_search_result(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": "missing", "against_claim_id": claim_id},
    )
    assert r.status_code == 404
