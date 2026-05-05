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
        router_mod, "_llm_extract_claims", lambda t, p, **_: ["Gesamtwärmeleistung 5.6 kW"]
    )
    monkeypatch.setattr(
        router_mod, "_llm_formulate_task", lambda c, p, **_: f"finde Quelle für: {c[:30]}"
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _claim_setup(client) -> tuple[str, str]:
    """Returns (session_id, claim_node_id) after running through extract-claims+decide."""
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
    decide = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    ).json()
    return sid, decide["spawned_nodes"][0]["node_id"]


def test_formulate_task_emits_action_proposal_with_query(client):
    sid, claim_id = _claim_setup(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": claim_id},
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["step_kind"] == "formulate_task"
    assert p["anchor_node_id"] == claim_id
    assert "query" in p["recommended"]["args"]
    assert p["recommended"]["args"]["query"].startswith("finde Quelle")


def test_decide_formulate_recommended_spawns_task_node(client):
    sid, claim_id = _claim_setup(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    )
    assert r.status_code == 201
    body = r.json()
    tasks = [n for n in body["spawned_nodes"] if n["kind"] == "task"]
    assert len(tasks) == 1
    assert tasks[0]["payload"]["focus_claim_id"] == claim_id
    assert "query" in tasks[0]["payload"]
    edge_kinds = {e["kind"] for e in body["spawned_edges"]}
    assert "verifies" in edge_kinds
    assert "decided-by" in edge_kinds
    assert "triggers" in edge_kinds


def test_decide_formulate_override_uses_freeform_query(client):
    sid, claim_id = _claim_setup(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": proposal["node_id"],
            "accepted": "override",
            "override": "Eigene Suchanfrage X",
            "reason": "Heuristik nicht spezifisch genug",
        },
    )
    assert r.status_code == 201
    tasks = [n for n in r.json()["spawned_nodes"] if n["kind"] == "task"]
    assert tasks[0]["payload"]["query"] == "Eigene Suchanfrage X"
    assert tasks[0]["actor"] == "human"


def test_formulate_task_404_when_claim_missing(client):
    sid, _claim_id = _claim_setup(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": "missing"},
    )
    assert r.status_code == 404


def test_formulate_task_400_when_anchor_not_claim(client):
    sid, _claim_id = _claim_setup(client)
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk = next(n for n in detail["nodes"] if n["kind"] == "chunk")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": chunk["node_id"]},
    )
    assert r.status_code in (400, 404)
