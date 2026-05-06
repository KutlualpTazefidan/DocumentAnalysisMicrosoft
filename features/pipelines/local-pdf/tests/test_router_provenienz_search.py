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
        router_mod, "_llm_extract_claims", lambda t, p, **_: ["Wärmeleistung Anlage"]
    )
    monkeypatch.setattr(router_mod, "_llm_formulate_task", lambda c, p, **_: "Wärmeleistung")
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _setup_task_node(client) -> tuple[str, str]:
    """Doc with a root chunk + 2 candidate chunks, walk through to a task node."""
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
                {
                    "box_id": "p1-b0",
                    "html_snippet": "<p>Die Anlage hat eine Wärmeleistung von 5.6 kW.</p>",
                },
                {
                    "box_id": "p2-b0",
                    "html_snippet": "<p>Tabelle: Wärmeleistung pro Komponente</p>",
                },
                {"box_id": "p3-b0", "html_snippet": "<p>Wetterbericht Berlin</p>"},
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
    return sid, task_id


def test_search_emits_action_proposal_with_hits(client):
    sid, task_id = _setup_task_node(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/search",
        headers={"X-Auth-Token": "tok"},
        json={"task_node_id": task_id, "top_k": 5},
    )
    assert r.status_code == 201, r.text
    p = r.json()["payload"]
    assert p["step_kind"] == "search"
    assert p["anchor_node_id"] == task_id
    hits = p["recommended"]["args"]["hits"]
    # Root chunk (p1-b0) MUST be excluded; we should at least get p2-b0
    assert all(h["box_id"] != "p1-b0" for h in hits)
    assert any(h["box_id"] == "p2-b0" for h in hits)


def test_decide_search_recommended_spawns_search_results(client):
    sid, task_id = _setup_task_node(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/search",
        headers={"X-Auth-Token": "tok"},
        json={"task_node_id": task_id, "top_k": 5},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    )
    assert r.status_code == 201
    body = r.json()
    sr = [n for n in body["spawned_nodes"] if n["kind"] == "search_result"]
    assert len(sr) >= 1
    assert all("box_id" in n["payload"] and "score" in n["payload"] for n in sr)
    assert all(n["payload"]["task_node_id"] == task_id for n in sr)
    edge_kinds = {e["kind"] for e in body["spawned_edges"]}
    assert "candidates-for" in edge_kinds
    assert "triggers" in edge_kinds


def test_decide_search_override_returns_400(client):
    sid, task_id = _setup_task_node(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/search",
        headers={"X-Auth-Token": "tok"},
        json={"task_node_id": task_id, "top_k": 5},
    ).json()
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": proposal["node_id"],
            "accepted": "override",
            "override": "manual hits",
        },
    )
    assert r.status_code == 400


def test_search_404_when_task_missing(client):
    sid, _task_id = _setup_task_node(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/search",
        headers={"X-Auth-Token": "tok"},
        json={"task_node_id": "missing", "top_k": 5},
    )
    assert r.status_code == 404
