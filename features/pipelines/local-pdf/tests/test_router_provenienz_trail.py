"""Trail-as-Trunk: ``triggered_from_node_id`` propagates from the step
endpoint request body onto the action_proposal payload, then onto every
spawned downstream node via the decide-handler.

Also covers evaluation breadcrumbs: when the trail head is an evaluation,
``promote_search_result`` and decompose-hit-spawned ``sub_statement`` Nodes
get ``origin_evaluation_*`` fields, and ``_build_origin_context`` renders
them as a German prompt-prefix block.
"""

from __future__ import annotations

import io

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.storage import Node
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
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate",
        lambda *a, **kw: {
            "verdict": "supports",
            "confidence": 0.9,
            "reasoning": "Treffer enthält die Wärmeleistung",
            "sentences": [],
        },
    )
    monkeypatch.setattr(
        router_mod,
        "_llm_decompose_hit",
        lambda hit_text, **_: ["Wärmeleistung 5.6 kW", "Anlage TRINO"],
    )
    monkeypatch.setattr(
        router_mod,
        "_llm_propose_stop",
        lambda anchor_text, provider, **_: "Recherche abgeschlossen.",
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _bootstrap_chunk(client) -> tuple[str, str]:
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
    return sid, chunk["node_id"]


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


def _spawn_evaluation(client, sid: str, sr_id: str) -> str:
    p = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    ).json()
    d = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p["node_id"], "accepted": "recommended"},
    ).json()
    eval_nodes = [n for n in d["spawned_nodes"] if n["kind"] == "evaluation"]
    assert eval_nodes
    return eval_nodes[0]["node_id"]


# ── Step-endpoint trail persistence ────────────────────────────────────


def test_extract_claims_persists_trail_id_on_action_proposal(client):
    sid, chunk_id = _bootstrap_chunk(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id, "triggered_from_node_id": "trail-xyz"},
    )
    assert r.status_code == 201
    assert r.json()["payload"]["triggered_from_node_id"] == "trail-xyz"


def test_extract_claims_no_trail_omits_field(client):
    sid, chunk_id = _bootstrap_chunk(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert "triggered_from_node_id" not in r.json()["payload"]


def test_formulate_task_persists_trail_id_on_action_proposal(client):
    sid, chunk_id = _bootstrap_chunk(client)
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
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/formulate-task",
        headers={"X-Auth-Token": "tok"},
        json={"claim_node_id": claim_id, "triggered_from_node_id": "trail-abc"},
    )
    assert r.status_code == 201
    assert r.json()["payload"]["triggered_from_node_id"] == "trail-abc"


# ── decide-handler propagation ─────────────────────────────────────────


def test_decide_propagates_trail_to_spawned_claims(client):
    sid, chunk_id = _bootstrap_chunk(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id, "triggered_from_node_id": "trail-eval-1"},
    ).json()
    body = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    ).json()
    claims = [n for n in body["spawned_nodes"] if n["kind"] == "claim"]
    assert claims
    for c in claims:
        assert c["payload"]["triggered_from_node_id"] == "trail-eval-1"


def test_decide_no_trail_means_no_trail_field_on_spawned_nodes(client):
    sid, chunk_id = _bootstrap_chunk(client)
    proposal = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    ).json()
    body = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": proposal["node_id"], "accepted": "recommended"},
    ).json()
    for n in body["spawned_nodes"]:
        assert "triggered_from_node_id" not in n["payload"]


def test_decide_propagates_trail_to_spawned_task(client):
    sid, chunk_id = _bootstrap_chunk(client)
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
        json={
            "claim_node_id": claim_id,
            "triggered_from_node_id": "trail-from-eval",
        },
    ).json()
    d2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p2["node_id"], "accepted": "recommended"},
    ).json()
    tasks = [n for n in d2["spawned_nodes"] if n["kind"] == "task"]
    assert tasks
    assert tasks[0]["payload"]["triggered_from_node_id"] == "trail-from-eval"


def test_decide_propagates_trail_to_spawned_search_results(client):
    sid, chunk_id = _bootstrap_chunk(client)
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
        json={
            "task_node_id": task_id,
            "top_k": 5,
            "triggered_from_node_id": "trail-search",
        },
    ).json()
    d3 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p3["node_id"], "accepted": "recommended"},
    ).json()
    srs = [n for n in d3["spawned_nodes"] if n["kind"] == "search_result"]
    assert srs
    for sr in srs:
        assert sr["payload"]["triggered_from_node_id"] == "trail-search"


def test_decide_propagates_trail_to_spawned_evaluation(client):
    sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    p = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={
            "search_result_node_id": sr_id,
            "triggered_from_node_id": "trail-eval-x",
        },
    ).json()
    d = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p["node_id"], "accepted": "recommended"},
    ).json()
    evals = [n for n in d["spawned_nodes"] if n["kind"] == "evaluation"]
    assert evals
    assert evals[0]["payload"]["triggered_from_node_id"] == "trail-eval-x"


def test_decide_propagates_trail_to_spawned_sub_statements(client):
    sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    eval_id = _spawn_evaluation(client, sid, sr_id)
    p = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decompose-hit",
        headers={"X-Auth-Token": "tok"},
        json={
            "search_result_node_id": sr_id,
            "triggered_from_node_id": eval_id,
        },
    ).json()
    d = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p["node_id"], "accepted": "recommended"},
    ).json()
    subs = [n for n in d["spawned_nodes"] if n["kind"] == "sub_statement"]
    assert subs
    for s in subs:
        assert s["payload"]["triggered_from_node_id"] == eval_id


def test_decide_propagates_trail_to_spawned_stop_proposal(client):
    sid, chunk_id = _bootstrap_chunk(client)
    p = client.post(
        f"/api/admin/provenienz/sessions/{sid}/propose-stop",
        headers={"X-Auth-Token": "tok"},
        json={
            "anchor_node_id": chunk_id,
            "triggered_from_node_id": "trail-stop",
        },
    ).json()
    d = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p["node_id"], "accepted": "recommended"},
    ).json()
    stops = [n for n in d["spawned_nodes"] if n["kind"] == "stop_proposal"]
    assert stops
    assert stops[0]["payload"]["triggered_from_node_id"] == "trail-stop"


# ── promote_search_result + evaluation breadcrumbs ─────────────────────


def test_promote_writes_origin_evaluation_breadcrumbs_when_trail_set(client):
    sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    eval_id = _spawn_evaluation(client, sid, sr_id)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={
            "search_result_node_id": sr_id,
            "triggered_from_node_id": eval_id,
        },
    )
    assert r.status_code == 201, r.text
    chunk = r.json()
    assert chunk["kind"] == "chunk"
    p = chunk["payload"]
    assert p["triggered_from_node_id"] == eval_id
    assert p["origin_evaluation_id"] == eval_id
    assert p["origin_evaluation_verdict"] == "supports"
    assert "Wärmeleistung" in p["origin_evaluation_reasoning"]


def test_promote_without_trail_omits_evaluation_breadcrumbs(client):
    sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    assert r.status_code == 201
    p = r.json()["payload"]
    assert "triggered_from_node_id" not in p
    assert "origin_evaluation_id" not in p
    assert "origin_evaluation_verdict" not in p


def test_promote_with_trail_pointing_at_non_evaluation_skips_breadcrumbs(client):
    """Trail pointing at a non-evaluation Node (e.g. a chunk) should
    persist trail_id but NOT inject evaluation breadcrumbs."""
    sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/promote-search-result",
        headers={"X-Auth-Token": "tok"},
        json={
            "search_result_node_id": sr_id,
            "triggered_from_node_id": chunk_id,  # not an evaluation
        },
    )
    assert r.status_code == 201
    p = r.json()["payload"]
    assert p["triggered_from_node_id"] == chunk_id
    assert "origin_evaluation_id" not in p


# ── decompose_hit + evaluation breadcrumbs on sub_statements ──────────


def test_decompose_hit_writes_evaluation_breadcrumbs_on_sub_statements(client):
    sid, chunk_id = _bootstrap_chunk(client)
    sr_id = _walk_to_search_result(client, sid, chunk_id)
    eval_id = _spawn_evaluation(client, sid, sr_id)
    p = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decompose-hit",
        headers={"X-Auth-Token": "tok"},
        json={
            "search_result_node_id": sr_id,
            "triggered_from_node_id": eval_id,
        },
    ).json()
    d = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": p["node_id"], "accepted": "recommended"},
    ).json()
    subs = [n for n in d["spawned_nodes"] if n["kind"] == "sub_statement"]
    assert subs
    for s in subs:
        assert s["payload"]["origin_evaluation_id"] == eval_id
        assert s["payload"]["origin_evaluation_verdict"] == "supports"
        assert "Wärmeleistung" in s["payload"]["origin_evaluation_reasoning"]


# ── _build_origin_context — evaluation block in prompt ─────────────────


def test_build_origin_context_includes_evaluation_block_when_present():
    chunk = Node(
        node_id="chunk-1",
        session_id="sess-1",
        kind="chunk",
        payload={
            "promoted_from": "sr-1",
            "origin_claim_text": "Wärmeleistung 5.6 kW",
            "origin_query": "Wärmeleistung",
            "origin_evaluation_id": "eval-1",
            "origin_evaluation_verdict": "partial-support",
            "origin_evaluation_reasoning": "deckt nicht jeden Wert ab",
        },
        actor="human",
    )
    ctx = router_mod._build_origin_context(chunk)
    assert "Vorherige Bewertung" in ctx
    assert "partial-support" in ctx
    assert "deckt nicht jeden Wert ab" in ctx
    # The original recherche-context block should still be there too.
    assert "Kontext der Recherche" in ctx
    assert "Wärmeleistung 5.6 kW" in ctx


def test_build_origin_context_eval_only_no_claim_query():
    """When the chunk has only origin_evaluation_* (no claim/query
    breadcrumbs), the evaluation block alone is rendered."""
    chunk = Node(
        node_id="chunk-1",
        session_id="sess-1",
        kind="chunk",
        payload={
            "promoted_from": "sr-1",
            "origin_evaluation_id": "eval-1",
            "origin_evaluation_verdict": "not-source",
            "origin_evaluation_reasoning": "Treffer falsch zugeordnet",
        },
        actor="human",
    )
    ctx = router_mod._build_origin_context(chunk)
    assert "Vorherige Bewertung" in ctx
    assert "not-source" in ctx
    # No "Kontext der Recherche" block since there's no claim/query.
    assert "Kontext der Recherche" not in ctx


def test_build_origin_context_unchanged_when_no_evaluation_breadcrumbs():
    chunk = Node(
        node_id="chunk-1",
        session_id="sess-1",
        kind="chunk",
        payload={
            "promoted_from": "sr-1",
            "origin_claim_text": "Wärmeleistung 5.6 kW",
            "origin_query": "Wärmeleistung",
        },
        actor="human",
    )
    ctx = router_mod._build_origin_context(chunk)
    assert "Vorherige Bewertung" not in ctx
    assert "Kontext der Recherche" in ctx


def test_build_origin_context_empty_for_non_promoted_chunk():
    chunk = Node(
        node_id="chunk-1",
        session_id="sess-1",
        kind="chunk",
        payload={"text": "irgendein Text"},
        actor="human",
    )
    assert router_mod._build_origin_context(chunk) == ""
