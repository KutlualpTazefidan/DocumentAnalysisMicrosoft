"""``recursion_depth`` metadata on chunks + claims.

The new pipeline replaces ``decompose_hit`` with the canonical
``promote_search_result → chunk → extract_claims → claim`` chain.
Each new chunk created via ``promote_search_result`` increments the
depth by 1; claims inherit the depth of the chunk they're extracted
from. Top-level chunks (created via ``create_session``) start at
depth 0.

These tests pin:
  * ``create_session`` → chunk has ``recursion_depth = 0``.
  * ``promote_search_result`` → spawned chunk's depth =
    parent_chunk.depth + 1.
  * ``decide(extract_claims)`` → spawned claim inherits chunk depth.
  * ``decompose_hit`` is no longer in the planner's available steps
    for ``search_result`` anchors (legacy soft-deprecate).
  * Legacy ``sub_statement`` Nodes still round-trip through
    ``read_session`` — old sessions stay readable.
"""

from __future__ import annotations

import io

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.storage import (
    Edge,
    Node,
    SessionMeta,
    append_edge,
    append_node,
    new_id,
    read_session,
    session_dir,
    write_meta,
)
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
        lambda chunk_text, provider, **_: ["Wärmeleistung beträgt 5.6 kW"],
    )
    monkeypatch.setattr(
        router_mod,
        "_llm_formulate_task",
        lambda c, p, **_: "Wärmeleistung",
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _bootstrap_chunk(client) -> tuple[str, str, str]:
    """Create a doc + session, return (slug, session_id, chunk_node_id)."""
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
                    "html_snippet": "<p>Die Anlage hat 5.6 kW.</p>",
                },
                {
                    "box_id": "p2-b0",
                    "html_snippet": "<p>Tabelle Wärmeleistung pro Komponente.</p>",
                },
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
    return slug, sid, chunk["node_id"]


def _walk_to_search_result(client, sid: str, chunk_id: str) -> str:
    """Run extract → decide → formulate → decide → search → decide.

    Returns the spawned search_result.node_id.
    """
    p1 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
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
    sr_nodes = [n for n in d3["spawned_nodes"] if n["kind"] == "search_result"]
    assert sr_nodes, "expected at least one search_result"
    return sr_nodes[0]["node_id"]


def test_create_session_chunk_has_depth_zero(client):
    """Top-level chunks (created via ``create_session``) start at depth 0."""
    _slug, sid, chunk_id = _bootstrap_chunk(client)
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk = next(n for n in detail["nodes"] if n["node_id"] == chunk_id)
    assert chunk["payload"]["recursion_depth"] == 0


def test_promote_search_result_increments_chunk_depth(client):
    """``promote_search_result`` spawns a chunk with depth = parent + 1."""
    _slug, sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    assert r.status_code == 201, r.text
    promoted = r.json()
    assert promoted["kind"] == "chunk"
    # Parent chunk lives at depth 0 → promoted chunk at depth 1.
    assert promoted["payload"]["recursion_depth"] == 1


def test_promote_search_result_chunk_at_depth_two(client):
    """A second-level promote should land at depth 2 — depth tracking
    works through chained recursive exploration."""
    _slug, sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    promoted = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    ).json()
    # Re-walk on the promoted chunk to spawn a fresh search_result.
    sr2_id = _walk_to_search_result(client, sid, promoted["node_id"])
    promoted2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr2_id},
    ).json()
    assert promoted2["payload"]["recursion_depth"] == 2


def test_extract_claims_inherits_chunk_depth(client):
    """Claims spawned by ``decide(extract_claims)`` inherit the chunk's
    ``recursion_depth``."""
    _slug, sid, chunk_id = _bootstrap_chunk(client)
    # Claims off the top-level chunk → depth 0.
    p_top = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    ).json()
    d_top = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p_top["node_id"], "accepted": "recommended"},
    ).json()
    top_claims = [n for n in d_top["spawned_nodes"] if n["kind"] == "claim"]
    assert top_claims
    for c in top_claims:
        assert c["payload"]["recursion_depth"] == 0

    # Now promote a search_result and extract claims from the promoted
    # chunk; new claims inherit the promoted chunk's depth (1).
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    promoted = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    ).json()
    p_deep = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": promoted["node_id"]},
    ).json()
    d_deep = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p_deep["node_id"], "accepted": "recommended"},
    ).json()
    deep_claims = [n for n in d_deep["spawned_nodes"] if n["kind"] == "claim"]
    assert deep_claims
    for c in deep_claims:
        assert c["payload"]["recursion_depth"] == 1


def test_decompose_hit_no_longer_in_search_result_step_list():
    """The Planner's ``_VALID_STEPS_FOR_KIND[search_result]`` no longer
    advertises ``decompose_hit`` — new flows use ``promote_search_result``
    + ``extract_claims`` instead. Legacy ``sub_statement`` anchor still
    has its full step set so old data stays readable."""
    sr_steps = router_mod._VALID_STEPS_FOR_KIND["search_result"]
    assert "decompose_hit" not in sr_steps
    assert "promote_search_result" in sr_steps
    # Legacy sub_statement nodes still need their pipeline.
    sub_steps = router_mod._VALID_STEPS_FOR_KIND["sub_statement"]
    assert sub_steps == ["evaluate", "propose_stop"]


def test_legacy_sub_statement_node_still_renders(tmp_path, monkeypatch):
    """An older session that contains a ``sub_statement`` Node (spawned
    by the legacy decompose_hit pipeline) round-trips through
    ``read_session`` unchanged. We don't migrate old data; the kind stays
    a first-class string and the Node payload is opaque to storage."""
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(tmp_path))
    sd = session_dir(tmp_path, "doc-x", "sess-x")
    write_meta(
        sd,
        SessionMeta(
            session_id="sess-x",
            slug="doc-x",
            root_chunk_id="p1-b0",
            status="open",
        ),
    )
    sr_node = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id="sess-x",
            kind="search_result",
            payload={"text": "Wärmeleistung 5.6 kW"},
            actor="system",
        ),
    )
    sub = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id="sess-x",
            kind="sub_statement",
            payload={"text": "Wärmeleistung 5.6 kW", "source_node_id": sr_node.node_id},
            actor="human",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id="sess-x",
            from_node=sub.node_id,
            to_node=sr_node.node_id,
            kind="decomposes",
            reason=None,
            actor="human",
        ),
    )
    nodes, edges = read_session(sd)
    sub_nodes = [n for n in nodes if n.kind == "sub_statement"]
    assert len(sub_nodes) == 1
    assert sub_nodes[0].payload["text"] == "Wärmeleistung 5.6 kW"
    assert any(e.kind == "decomposes" for e in edges)
