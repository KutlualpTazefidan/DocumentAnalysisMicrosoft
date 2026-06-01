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
    monkeypatch.setattr(router_mod, "_llm_extract_claims", lambda t, p, **_: ["Wärmeleistung"])
    monkeypatch.setattr(router_mod, "_llm_propose_stop", lambda txt, p, **_: "Quelle gefunden")
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _setup_claim(client) -> tuple[str, str]:
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
    p = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk["node_id"]},
    ).json()
    d = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p["node_id"], "accepted": "recommended"},
    ).json()
    return sid, d["spawned_nodes"][0]["node_id"]


def test_propose_stop_emits_action_proposal(client):
    sid, claim_id = _setup_claim(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/propose-stop",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": claim_id},
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["step_kind"] == "propose_stop"
    assert p["anchor_node_id"] == claim_id
    assert p["recommended"]["args"]["close_session"] is True
    assert p["recommended"]["args"]["reason"] == "Quelle gefunden"


def test_decide_propose_stop_recommended_closes_session(client):
    sid, claim_id = _setup_claim(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/propose-stop",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    )
    assert r.status_code == 201
    body = r.json()
    stops = [n for n in body["spawned_nodes"] if n["kind"] == "stop_proposal"]
    assert len(stops) == 1
    assert stops[0]["payload"]["reason"] == "Quelle gefunden"
    assert stops[0]["payload"]["close_session"] is True

    # Session meta flipped to closed.
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    assert detail["meta"]["status"] == "closed"


def test_decide_propose_stop_alt_keeps_session_open(client):
    sid, claim_id = _setup_claim(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/propose-stop",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "alt", "alt_index": 0},
    )
    assert r.status_code == 201
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    assert detail["meta"]["status"] == "open"


def test_decide_propose_stop_override_uses_freeform_reason(client):
    sid, claim_id = _setup_claim(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/propose-stop",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": claim_id},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": proposal["node_id"],
            "accepted": "override",
            "override": "Sackgasse — keine weitere Recherche möglich",
            "reason": "Anschluss an Lit-Verzeichnis fehlt",
        },
    )
    assert r.status_code == 201
    body = r.json()
    stops = [n for n in body["spawned_nodes"] if n["kind"] == "stop_proposal"]
    assert stops[0]["payload"]["reason"] == "Sackgasse — keine weitere Recherche möglich"
    assert stops[0]["payload"]["close_session"] is True
    assert stops[0]["actor"] == "human"
