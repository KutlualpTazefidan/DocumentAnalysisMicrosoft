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
    # Substitute the LLM helper with a deterministic stub.
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


def _bootstrap_session(client) -> tuple[str, str]:
    """Create a doc + session with one chunk, return (session_id, chunk_node_id)."""
    upload = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    slug = upload.json()["slug"]

    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {
            "elements": [
                {
                    "box_id": "p1-b0",
                    "html_snippet": "<p>Die Gesamtwärmeleistung beträgt 5.6 kW.</p>",
                }
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
    chunk_node = next(n for n in detail["nodes"] if n["kind"] == "chunk")
    return sid, chunk_node["node_id"]


def test_extract_claims_emits_action_proposal_with_alternatives(client):
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_node_id},
    )
    assert r.status_code == 201, r.text
    proposal = r.json()
    assert proposal["kind"] == "action_proposal"
    p = proposal["payload"]
    assert p["step_kind"] == "extract_claims"
    assert p["anchor_node_id"] == chunk_node_id
    # Recommended carries the list of claim strings; alternatives is a single
    # "skip" option for v1.
    assert p["recommended"]["args"]["claims"] == [
        "Gesamtwärmeleistung beträgt 5.6 kW",
        "Die Baugruppe ist X",
    ]
    assert p["alternatives"][0]["args"]["claims"] == []


def test_extract_claims_persists_proposal_to_event_log(client):
    sid, chunk_node_id = _bootstrap_session(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_node_id},
    ).json()

    # Re-fetch session detail; the proposal node should be present.
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    proposal_nodes = [n for n in detail["nodes"] if n["kind"] == "action_proposal"]
    assert len(proposal_nodes) == 1
    assert proposal_nodes[0]["node_id"] == proposal["node_id"]


def test_extract_claims_404_when_session_missing(client):
    r = client.post(
        "/api/admin/provenienz/sessions/missing/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": "any"},
    )
    assert r.status_code == 404


def test_extract_claims_404_when_chunk_node_missing(client):
    sid, _ = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": "not-a-real-node"},
    )
    assert r.status_code == 404


def test_extract_claims_400_when_anchor_is_not_a_chunk(client):
    """Anchor must be a node of kind=chunk."""
    sid, chunk_node_id = _bootstrap_session(client)
    # First call creates an action_proposal node — feed THAT id back.
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_node_id},
    ).json()

    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": proposal["node_id"]},
    )
    # 404 with a clear "not a chunk" detail is fine; route may also use
    # 400. Accept either.
    assert r.status_code in (400, 404)
