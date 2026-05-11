"""Tests for the /investigate-table choreography endpoint.

The endpoint orchestrates a 3-axis investigation around a table-typed
search_result. Two axes (Text-Referenz, Quellen-Attribution) pre-run
InDocSearcher with derived queries; the third (Semantik-Rueckpruefung)
spawns a no-search evaluate proposal that just emits the prompt for the
user to accept.
"""

from __future__ import annotations

import io

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.storage import (
    Edge,
    Node,
    append_edge,
    append_node,
    new_id,
)
from local_pdf.storage.sidecar import write_mineru


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    # Semantik-Rueckpruefung pre-bakes the verdict via _llm_evaluate at
    # investigate-table-spawn time. Stub the LLM so tests stay
    # deterministic + fast.
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate",
        lambda claim_text, candidate_text, provider, *, extra_system="", calc_hint="": {
            "verdict": "partial-support",
            "confidence": 0.6,
            "reasoning": "Stub-Bewertung: Zeilen-/Spalten-Bindung nicht eindeutig.",
            "sentences": [],
        },
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _setup_session_with_table_sr(
    client,
    *,
    caption_text: str,
) -> tuple[str, str]:
    """Spawn a session with chunk -> claim -> task -> table search_result
    by manipulating the JSONL stores directly. Returns (session_id, sr_id).
    """
    upload = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    slug = upload.json()["slug"]
    cfg = client.app.state.config
    # Mineru with: root chunk (p1) + table the SR points at (p2) +
    # candidate boxes for axes 2 + 3 to find.
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
                    "box_id": "p2-table",
                    "html_snippet": (
                        "<table><tr><th>Gr</th><th>Wert</th></tr>"
                        "<tr><td>X</td><td>5</td></tr></table>"
                    ),
                },
                {
                    "box_id": "p3-mention",
                    "html_snippet": (
                        "<p>Wie in Tabelle 3.7 gezeigt, betraegt die Wärmeleistung 5 kW.</p>"
                    ),
                },
                {
                    "box_id": "p4-source",
                    "html_snippet": "<p>Quelle [4]: Müller et al. 2019, Reaktorhandbuch.</p>",
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
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    # Build the rest of the graph directly: claim, task, search_result.
    claim_id = new_id()
    append_node(
        sd,
        Node(
            node_id=claim_id,
            session_id=sid,
            kind="claim",
            payload={"text": "Die Anlage hat 5 kW Wärmeleistung.", "goal": "leistung"},
            actor="human",
        ),
    )
    task_id = new_id()
    task_payload: dict = {
        "query": "Wärmeleistung Anlage",
        "focus_claim_id": claim_id,
        "context": {"visited_box_ids": ["p1-b0"], "origin_chain": []},
    }
    append_node(
        sd,
        Node(
            node_id=task_id,
            session_id=sid,
            kind="task",
            payload=task_payload,
            actor="human",
        ),
    )
    sr_id = new_id()
    append_node(
        sd,
        Node(
            node_id=sr_id,
            session_id=sid,
            kind="search_result",
            payload={
                "box_id": "p2-table",
                "doc_slug": slug,
                "text": "Tabelle: ...",
                "score": 1.0,
                "task_node_id": task_id,
                "box_kind": "table",
                "caption_text": caption_text,
            },
            actor="human",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id=new_id(),
            session_id=sid,
            from_node=sr_id,
            to_node=task_id,
            kind="answers",
            reason=None,
            actor="human",
        ),
    )
    return sid, sr_id


def test_investigate_table_spawns_three_proposals_when_caption_complete(client):
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten (nach [4]).",
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["proposals"]) == 3
    assert body["skipped"] == []
    step_kinds = [p["payload"]["step_kind"] for p in body["proposals"]]
    assert step_kinds.count("search") == 2
    assert step_kinds.count("evaluate") == 1
    # Search proposals should carry investigation_axis labels.
    axes = [
        p["payload"]["recommended"]["args"].get("investigation_axis") for p in body["proposals"]
    ]
    assert "Text-Referenz" in axes
    assert "Quellen-Attribution" in axes
    assert "Semantik-Rueckpruefung" in axes


def test_investigate_table_semantik_proposal_carries_prebaked_verdict(client):
    """The Semantik-Rueckpruefung proposal is a step_kind=evaluate
    action_proposal. /decide on it must work without a special branch,
    which requires args to carry verdict/confidence/reasoning/
    against_claim_id like a regular evaluate proposal.
    """
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten",
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    body = r.json()
    semantik = next(
        p
        for p in body["proposals"]
        if p["payload"]["recommended"]["args"].get("investigation_axis") == "Semantik-Rueckpruefung"
    )
    args = semantik["payload"]["recommended"]["args"]
    # All fields /decide's evaluate branch reads must be present.
    assert "verdict" in args
    assert "confidence" in args
    assert "reasoning" in args
    assert "against_claim_id" in args
    assert "search_result_node_id" in args
    # Pre-baked values from the stubbed _llm_evaluate.
    assert args["verdict"] == "partial-support"
    assert args["confidence"] == 0.6
    assert "Bindung" in args["reasoning"] or "Stub" in args["reasoning"]


def test_decide_auto_heals_legacy_semantik_proposal_without_verdict(client):
    """An older Semantik-Rueckpruefung proposal -- spawned before
    pre-baking landed -- has args = {search_result_node_id,
    investigation_axis} with no verdict. /decide must not crash on
    KeyError; instead it back-fills via _llm_evaluate.
    """
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten",
    )
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None
    # Hand-craft a legacy-shape action_proposal directly in the JSONL.
    legacy_proposal_id = new_id()
    append_node(
        sd,
        Node(
            node_id=legacy_proposal_id,
            session_id=sid,
            kind="action_proposal",
            payload={
                "step_kind": "evaluate",
                "anchor_node_id": sr_id,
                "recommended": {
                    "label": "Semantik-Rueckpruefung: erneut bewerten",
                    "args": {
                        "search_result_node_id": sr_id,
                        "investigation_axis": "Semantik-Rueckpruefung",
                        # NO verdict / confidence / reasoning / against_claim_id
                    },
                },
                "alternatives": [],
                "reasoning": "Legacy proposal without pre-baked verdict",
                "guidance_consulted": [],
            },
            actor="system",
        ),
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": legacy_proposal_id,
            "accepted": "recommended",
        },
    )
    assert r.status_code == 201, r.text
    eval_nodes = [n for n in r.json()["spawned_nodes"] if n["kind"] == "evaluation"]
    assert len(eval_nodes) == 1
    # Auto-heal back-filled via the stubbed _llm_evaluate in the fixture.
    assert eval_nodes[0]["payload"]["verdict"] == "partial-support"
    # against_claim_id was empty in args; auto-heal must resolve it from
    # the sr -> task -> focus_claim_id chain.
    assert eval_nodes[0]["payload"]["against_claim_id"]


def test_investigate_table_decide_on_semantik_proposal_succeeds(client):
    """End-to-end: spawn the Semantik proposal via /investigate-table,
    accept it via /decide. The /decide call must NOT crash with the
    KeyError on args['verdict'] that pre-bakeing was added to prevent.
    """
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten",
    )
    spawn = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    ).json()
    semantik = next(
        p
        for p in spawn["proposals"]
        if p["payload"]["recommended"]["args"].get("investigation_axis") == "Semantik-Rueckpruefung"
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": semantik["node_id"],
            "accepted": "recommended",
        },
    )
    assert r.status_code == 201, r.text
    decision = r.json()
    eval_nodes = [n for n in decision["spawned_nodes"] if n["kind"] == "evaluation"]
    assert len(eval_nodes) == 1
    assert eval_nodes[0]["payload"]["verdict"] == "partial-support"


def test_investigate_table_skips_text_reference_when_no_identifier(client):
    sid, sr_id = _setup_session_with_table_sr(
        client,
        # Caption has source attribution but no Tabelle-X identifier.
        caption_text="Reaktor-Hauptdaten (nach [4]).",
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["proposals"]) == 2  # Quellen + Semantik only
    skipped_axes = [s["axis"] for s in body["skipped"]]
    assert skipped_axes == ["Text-Referenz"]


def test_investigate_table_skips_source_attribution_when_no_token(client):
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten",
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    assert r.status_code == 201
    body = r.json()
    assert len(body["proposals"]) == 2  # Text-Referenz + Semantik only
    skipped_axes = [s["axis"] for s in body["skipped"]]
    assert skipped_axes == ["Quellen-Attribution"]


def test_investigate_table_rejects_non_table_search_result(client):
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten",
    )
    # Mutate the SR's box_kind to text post-hoc by spawning a fresh
    # text SR with the same task linkage. Easier than mutating the
    # JSONL.
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None
    nodes, _ = router_mod.read_session(sd)
    sr = next(n for n in nodes if n.node_id == sr_id)
    text_sr_id = new_id()
    append_node(
        sd,
        Node(
            node_id=text_sr_id,
            session_id=sid,
            kind="search_result",
            payload={
                **sr.payload,
                "box_kind": "text",
            },
            actor="human",
        ),
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": text_sr_id},
    )
    assert r.status_code == 400
    assert "box_kind=table" in r.json()["detail"]


def test_investigate_table_text_reference_finds_mention(client):
    """Axis-2 pre-runs a search for the table identifier; the mineru
    fixture has 'p3-mention' that contains 'Tabelle 3.7'. The proposal's
    hits should include it."""
    sid, sr_id = _setup_session_with_table_sr(
        client,
        caption_text="Tabelle 3.7: Reaktor-Hauptdaten",
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/investigate-table",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id},
    )
    body = r.json()
    text_ref = next(
        p
        for p in body["proposals"]
        if p["payload"]["recommended"]["args"].get("investigation_axis") == "Text-Referenz"
    )
    hits = text_ref["payload"]["recommended"]["args"]["hits"]
    box_ids = {h["box_id"] for h in hits}
    assert "p3-mention" in box_ids
    # Table itself must NOT appear in its own text-reference hits.
    assert "p2-table" not in box_ids
