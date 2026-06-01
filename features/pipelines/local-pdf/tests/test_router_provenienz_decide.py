import io
import json as _json

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.storage import (
    Node,
    append_node,
    new_id,
    session_dir,
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
        lambda chunk_text, provider, **_: [
            "Gesamtwärmeleistung beträgt 5.6 kW",
            "Die Baugruppe ist X",
        ],
    )
    # Phase-RGA: the gap-detection evaluator (Step 4 wire-in) would
    # otherwise fire on every plan_proposal /decide and burn real LLM
    # calls. The legacy decide tests below don't exercise RGA; opt out
    # via the kill-switch. RGA-specific tests at the bottom of this
    # file re-enable per-test.
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: False)
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


def _plan_propose(
    client,
    *,
    step_name: str = "extract_claims",
    reasoning: str = "Chunk has claims to extract.",
) -> tuple[str, str, str]:
    """Returns (session_id, chunk_node_id, plan_proposal_node_id).

    Injects a plan_proposal Node directly into the session storage —
    bypasses /next-step so the test doesn't need a real LLM. Mirrors
    the shape /next-step writes (kind="executable_step", plus name +
    reasoning + anchor_node_id payload fields).
    """
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
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
    sd = session_dir(cfg.data_root, slug, sid)
    plan = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="plan_proposal",
            payload={
                "kind": "executable_step",
                "name": step_name,
                "reasoning": reasoning,
                "anchor_node_id": chunk_id,
                "considered_alternatives": [],
                "confidence": 0.9,
                "tool": None,
                "approach_id": None,
                "triggered_from_node_id": "",
            },
            actor="planner",
        ),
    )
    return sid, chunk_id, plan.node_id


# ── plan_proposal /decide branch tests (expert-override capture) ─────────


def test_decide_plan_proposal_known_step_spawns_expert_step_override(client):
    """Phase-3: Override with a known step lands as a single
    expert_step_override Node (Purpose 1 — teach the agent), actor=human.
    No capability_request because the intended_step is registered, no
    is_unimplemented flag (the Node-Kind is the discriminator).
    Plan-proposal stays alive (audit-trail)."""
    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Chunk benennt eine Konstrukt-Definition — Task passt besser.",
            },
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # decision Node carries the synthetic "plan_override" verb.
    assert body["decision_node"]["kind"] == "decision"
    assert body["decision_node"]["payload"]["accepted"] == "plan_override"
    # Exactly one spawned node — the typed override. No capability_request.
    assert len(body["spawned_nodes"]) == 1
    ec = body["spawned_nodes"][0]
    assert ec["kind"] == "expert_step_override"
    assert ec["actor"] == "human"
    assert "is_unimplemented" not in ec["payload"]
    assert ec["payload"]["target_proposal_node_id"] == plan_id
    assert ec["payload"]["target_step_kind"] == "extract_claims"
    # Edges: decided-by (decision → plan) + overrides (ec → plan).
    edge_kinds = {e["kind"] for e in body["spawned_edges"]}
    assert {"decided-by", "overrides"} <= edge_kinds
    # Plan-proposal still in the session (not tombstoned).
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    assert any(n["node_id"] == plan_id and n["kind"] == "plan_proposal" for n in sess["nodes"])


def test_decide_plan_proposal_unknown_step_spawns_expert_method_request(client):
    """Phase-3: Override with an unimplemented step name lands as a
    SINGLE expert_method_request Node (Purpose 2 — mark a capability
    gap), with the capability_request payload fields (`name`,
    `description`) folded in directly. No parallel capability_request
    Node spawn — the capability_request kind stays agent-only by
    invariant."""
    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "summarize_section",
                "reason": "Chunk braucht erst eine Zusammenfassung.",
            },
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # Exactly one spawned Node — the method-request. NO separate CR.
    assert len(body["spawned_nodes"]) == 1
    emr = body["spawned_nodes"][0]
    assert emr["kind"] == "expert_method_request"
    assert emr["actor"] == "human"
    assert "is_unimplemented" not in emr["payload"]
    # Folded capability_request payload-fields (aggregator-readable).
    assert emr["payload"]["name"] == "summarize_section"
    assert emr["payload"]["description"].startswith("Chunk braucht erst")
    # Original expert-override fields preserved.
    assert emr["payload"]["intended_step"] == "summarize_section"
    assert emr["payload"]["target_proposal_node_id"] == plan_id
    # Edges: decided-by + overrides (method-request → plan).
    edge_kinds = {e["kind"] for e in body["spawned_edges"]}
    assert {"decided-by", "overrides"} <= edge_kinds
    # No agent-emitted capability_request was somehow created either.
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    assert not any(n["kind"] == "capability_request" for n in sess["nodes"])


def test_decide_plan_proposal_persists_note_skill_with_origin_marker(client):
    """The override lands in the existing reason corpus (NOTE skill in
    skills.jsonl) so _gather_reason_guidance picks it up on the next
    /next-step. NOTE skill name carries the `-plan_proposal-` origin
    marker so a future Phase-2 migration can filter without crawling
    the DAG."""
    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Task formulieren ist passender.",
            },
        },
    )
    assert r.status_code == 201, r.text
    cfg = client.app.state.config
    skills_file = cfg.data_root / "skills" / "skills.jsonl"
    lines = [_json.loads(line) for line in skills_file.read_text().splitlines() if line.strip()]
    notes = [s for s in lines if str(s.get("skill_kind", "")).lower() == "note"]
    plan_notes = [s for s in notes if "note-plan_proposal-" in s.get("name", "")]
    assert len(plan_notes) == 1, f"expected 1 plan_proposal NOTE, got {len(plan_notes)}"
    note = plan_notes[0]
    # step_kind anchors on the source proposal's step name so future
    # plan_proposals of the same kind surface this correction.
    assert note["fires_on"] == ["extract_claims"]


def test_decide_action_proposal_backcompat_recommended(client):
    """The widening doesn't break the existing action_proposal branch.
    The recommended path still spawns claim nodes via _llm_extract_claims."""
    sid, chunk_id, prop_id = _propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": prop_id, "accepted": "recommended"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # Decision Node payload preserves the legacy accepted verb (not "plan_override").
    assert body["decision_node"]["payload"]["accepted"] == "recommended"
    # Two claim Nodes spawn from the mocked _llm_extract_claims fixture.
    spawned_kinds = [n["kind"] for n in body["spawned_nodes"]]
    assert spawned_kinds.count("claim") == 2
    # Phase-3: none of the override Node-Kinds appear in the
    # action_proposal path (the kind-widening only enables them on the
    # plan_proposal branch).
    _override_kinds = {"expert_correction", "expert_step_override", "expert_method_request"}
    assert all(n["kind"] not in _override_kinds for n in body["spawned_nodes"])
    # Edges anchor the claims to the source chunk (legacy behavior).
    edge_kinds = {e["kind"] for e in body["spawned_edges"]}
    assert {"extracts-from", "decided-by", "triggers"} <= edge_kinds
    assert all(
        e["to_node"] == chunk_id for e in body["spawned_edges"] if e["kind"] == "extracts-from"
    )


def test_decide_plan_proposal_empty_expert_correction_400(client):
    """plan_proposal /decide requires expert_correction. Sending the
    legacy action_proposal-shaped body (accepted=recommended, no EC)
    must be rejected — defends against clients that didn't migrate."""
    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={"proposal_node_id": plan_id, "accepted": "recommended"},
    )
    assert r.status_code == 400, r.text
    assert "expert_correction" in r.json()["detail"]


def test_decide_plan_proposal_with_accepted_400(client):
    """accepted is forbidden on the plan_proposal branch — guards against
    confusing dual-mode submissions where the client tries to express
    both an accept choice AND an override at the same time."""
    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "accepted": "recommended",
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "irrelevant — accepted forbidden",
            },
        },
    )
    assert r.status_code == 400, r.text
    assert "accepted" in r.json()["detail"]


def test_decide_plan_proposal_aggregator_surfaces_actor(client):
    """The /capability-requests aggregator surfaces actor=human on CRs
    spawned via the expert-override path, distinguishing them from
    actor=agent CRs the planner emits during /next-step. Lets the UI
    badge them differently in the Wünsche tab."""
    sid, _chunk, plan_id = _plan_propose(client)
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "summarize_section",
                "reason": "Expert prescribes this method",
            },
        },
    )
    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    matches = [req for req in r.json()["requests"] if req["name"] == "summarize_section"]
    assert len(matches) == 1
    assert matches[0]["count"] == 1
    assert matches[0]["examples"][0]["actor"] == "human"


def test_decide_plan_proposal_concurrent_overrides_append_only(client):
    """Two sequential overrides on the same plan_proposal both succeed
    and both land in the session's event log (append-only). The plan
    stays alive after either; reviewers see the full override history."""
    sid, _chunk, plan_id = _plan_propose(client)
    r1 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Erste Überlegung",
            },
        },
    )
    r2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "search",
                "reason": "Nach Nachdenken: lieber suchen",
            },
        },
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    # Phase-3: both intended_steps ("formulate_task", "search") are
    # known steps → each lands as an expert_step_override (not the
    # legacy expert_correction kind). Both Nodes persist; no
    # last-write-wins replacement — event log is append-only.
    eso_nodes = [n for n in sess["nodes"] if n["kind"] == "expert_step_override"]
    assert len(eso_nodes) == 2
    # Both linked to the same source plan_proposal.
    assert all(n["payload"]["target_proposal_node_id"] == plan_id for n in eso_nodes)
    # Both reasons captured verbatim.
    reasons = {n["payload"]["reason"] for n in eso_nodes}
    assert reasons == {"Erste Überlegung", "Nach Nachdenken: lieber suchen"}


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


# ── Phase-RGA: clarification spawn on gap-detected /decide ──────────────


def test_decide_plan_proposal_gap_detected_returns_clarification(client, monkeypatch):
    """When the evaluator says score < threshold, /decide response carries
    a clarification block, Reason is written with pending_clarification=True,
    override Node payload has rga + pending_clarification."""
    # Re-enable RGA for this test
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: True)
    # Stub the evaluator to force a "gap" verdict (intended_step absent
    # from ranked list -> score 1 -> gap_detected since threshold=3)
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate_plan_override",
        lambda anchor, goal, reason, intended: {
            "ranked_steps_raw": ["extract_claims", "propose_stop"],
            "ranked_steps_canonical": ["extract_claims", "propose_stop"],
            "rank": None,
            "score": 1,
            "rationale": "intended_step absent from plausible list",
            "parse_error": False,
        },
    )

    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Konstrukt-Definition.",
            },
        },
    )
    assert r.status_code == 201
    body = r.json()
    # Response carries clarification block (not None)
    assert body.get("clarification") is not None
    assert "question" in body["clarification"]
    assert body["clarification"]["score"] == 1
    assert body["clarification"]["override_node_id"] is not None
    # Override Node has rga + pending_clarification on its payload
    override = body["spawned_nodes"][0]
    assert override["payload"]["pending_clarification"] is True
    assert override["payload"]["capture_source"] == "decision_time"
    assert "rga" in override["payload"]
    assert override["payload"]["rga"]["score"] == 1
    # Reason was written immediately (write-now+pending). Verify by
    # reading reasons corpus.
    from local_pdf.provenienz.reasons import read_reasons

    cfg = client.app.state.config
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=10)
    assert len(reasons) == 1
    assert reasons[0].pending_clarification is True
    assert reasons[0].capture_source == "decision_time"
    assert reasons[0].clarification == ""


def test_decide_plan_proposal_obvious_no_clarification(client, monkeypatch):
    """When evaluator says rank 0 -> score 5 -> obvious, response has
    clarification=None, Reason has pending_clarification=False."""
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: True)
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate_plan_override",
        lambda anchor, goal, reason, intended: {
            "ranked_steps_raw": ["formulate_task", "propose_stop"],
            "ranked_steps_canonical": ["formulate_task", "propose_stop"],
            "rank": 0,
            "score": 5,
            "rationale": "obvious match",
            "parse_error": False,
        },
    )
    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Claim braucht Suche.",
            },
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body.get("clarification") is None
    override = body["spawned_nodes"][0]
    assert override["payload"]["pending_clarification"] is False
    assert override["payload"]["rga"]["score"] == 5


def test_decide_plan_proposal_post_hoc_skips_rga(client, monkeypatch):
    """post_hoc=True path skips the evaluator entirely. No rga key on
    payload, no clarification, no telemetry row."""
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: True)
    eval_called = {"count": 0}

    def _spy(*args, **kwargs):
        eval_called["count"] += 1
        return {
            "score": 1,
            "rank": None,
            "ranked_steps_raw": [],
            "ranked_steps_canonical": [],
            "rationale": "",
            "parse_error": False,
        }

    monkeypatch.setattr(router_mod, "_llm_evaluate_plan_override", _spy)

    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Im Nachhinein: andere Methode passt besser.",
                "post_hoc": True,
            },
        },
    )
    assert r.status_code == 201
    # Evaluator must NOT have been called
    assert eval_called["count"] == 0
    body = r.json()
    assert body.get("clarification") is None
    override = body["spawned_nodes"][0]
    assert override["payload"]["pending_clarification"] is False
    assert override["payload"]["capture_source"] == "post_hoc"
    assert "rga" not in override["payload"]


def test_decide_plan_proposal_kill_switch_skips_rga(client, monkeypatch):
    """When PROVENIENZ_RGA_ENABLED=false (via _rga_enabled stub), the
    evaluator is not called and response has no clarification, even
    when the override would otherwise be gap-flagged."""
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: False)
    eval_called = {"count": 0}

    def _spy(*args, **kwargs):
        eval_called["count"] += 1
        return {
            "score": 1,
            "rank": None,
            "ranked_steps_raw": [],
            "ranked_steps_canonical": [],
            "rationale": "",
            "parse_error": False,
        }

    monkeypatch.setattr(router_mod, "_llm_evaluate_plan_override", _spy)

    sid, _chunk, plan_id = _plan_propose(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Konstrukt-Definition.",
            },
        },
    )
    assert r.status_code == 201
    assert eval_called["count"] == 0
    body = r.json()
    assert body.get("clarification") is None
    override = body["spawned_nodes"][0]
    assert override["payload"]["pending_clarification"] is False
    assert "rga" not in override["payload"]
