"""Phase-RGA Step 6: /clarify endpoint tests.

Exercises the resolution-path for pending clarifications. Setup:
build a session through /decide with the evaluator stubbed to return
a low score (gap detected), capture the override_node_id from the
response, then hit /clarify to resolve.
"""

from __future__ import annotations

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
    # Force the LLM to a deterministic gap on every /decide:
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: True)
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
    # Stub _llm_next_step for the plan_proposal creation
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda anchor, goal, available_steps, tools_summary, **kwargs: {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "test stub",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
        },
    )
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _seed_pending_override(client) -> tuple[str, str]:
    """Bootstrap a doc + session + plan_proposal + gap-detected /decide.
    Returns (session_id, override_node_id)."""
    r = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    slug = r.json()["slug"]
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
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in sess["nodes"] if n["kind"] == "chunk")
    plan = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    ).json()
    plan_id = plan["node_id"]
    decide = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Konstrukt-Definition.",
            },
        },
    ).json()
    assert decide["clarification"] is not None
    override_id = decide["clarification"]["override_node_id"]
    return sid, override_id


def test_clarify_submit_flips_pending_and_writes_clarification(client):
    sid, oid = _seed_pending_override(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={
            "override_node_id": oid,
            "clarification": (
                "Der Term 'Konstrukt-Definition' bezeichnet eine Variable, "
                "kein empirisches Faktum — formulate_task ist passend."
            ),
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["override_node"]["payload"]["pending_clarification"] is False
    assert body["override_node"]["payload"]["clarification"].startswith("Der Term")
    assert body["spawned_nodes"] == []  # submit path doesn't spawn skipped-Node

    # Reason is updated in corpus
    from local_pdf.provenienz.reasons import read_reasons

    cfg = client.app.state.config
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=10)
    assert len(reasons) == 1
    assert reasons[0].pending_clarification is False
    assert reasons[0].clarification.startswith("Der Term")


def test_clarify_skip_spawns_clarification_skipped_node_and_edge(client):
    sid, oid = _seed_pending_override(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={
            "override_node_id": oid,
            "skipped": True,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["override_node"]["payload"]["pending_clarification"] is False
    assert body["override_node"]["payload"].get("clarification", "") == ""
    # Spawned a clarification_skipped Node
    assert len(body["spawned_nodes"]) == 1
    skip_node = body["spawned_nodes"][0]
    assert skip_node["kind"] == "clarification_skipped"
    assert skip_node["payload"]["target_override_node_id"] == oid
    assert skip_node["payload"]["intended_step"] == "formulate_task"
    assert "question" in skip_node["payload"]
    # Edge "annotates" from skip-Node -> override
    assert len(body["spawned_edges"]) == 1
    ann_edge = body["spawned_edges"][0]
    assert ann_edge["kind"] == "annotates"
    assert ann_edge["from_node"] == skip_node["node_id"]
    assert ann_edge["to_node"] == oid

    # Reason is updated in corpus with empty clarification + pending=False
    from local_pdf.provenienz.reasons import read_reasons

    cfg = client.app.state.config
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=10)
    assert len(reasons) == 1
    assert reasons[0].pending_clarification is False
    assert reasons[0].clarification == ""


def test_clarify_double_resolve_returns_409(client):
    sid, oid = _seed_pending_override(client)
    # First resolution
    r1 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid, "clarification": "first answer"},
    )
    assert r1.status_code == 201
    # Second attempt should 409
    r2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid, "clarification": "second"},
    )
    assert r2.status_code == 409
    assert "already resolved" in r2.json()["detail"]


def test_clarify_invalid_override_node_id_returns_404(client):
    sid, _oid = _seed_pending_override(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": "01NOSUCHNODE", "clarification": "answer"},
    )
    assert r.status_code == 404
    assert "override node not found" in r.json()["detail"]


def test_clarify_neither_text_nor_skipped_returns_422(client):
    sid, oid = _seed_pending_override(client)
    # Empty clarification AND skipped=False -> validator fails
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid, "clarification": "", "skipped": False},
    )
    assert r.status_code == 422  # Pydantic validation


def test_clarify_endpoint_skipped_on_obvious_override_returns_409(client, monkeypatch):
    """If the original /decide was 'obvious' (no clarification spawn),
    the override has pending_clarification=False from the start — calling
    /clarify on it should 409."""
    # Override the evaluator to return obvious (rank 0, score 5)
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate_plan_override",
        lambda anchor, goal, reason, intended: {
            "ranked_steps_raw": ["formulate_task", "propose_stop"],
            "ranked_steps_canonical": ["formulate_task", "propose_stop"],
            "rank": 0,
            "score": 5,
            "rationale": "obvious",
            "parse_error": False,
        },
    )
    # Manually build: doc + session + plan + obvious /decide
    r = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    slug = r.json()["slug"]
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
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in sess["nodes"] if n["kind"] == "chunk")
    plan = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    ).json()
    plan_id = plan["node_id"]
    decide = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Claim braucht Suche.",
            },
        },
    ).json()
    assert decide["clarification"] is None  # obvious path
    # Find the override node_id from spawned_nodes
    override = decide["spawned_nodes"][0]
    oid = override["node_id"]
    # /clarify on this override must 409 (pending_clarification was never True)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid, "clarification": "anyway"},
    )
    assert r.status_code == 409


def test_clarify_resolves_only_reason_for_matching_session_under_text_collision(client):
    """Phase 6A regression guard: two sessions both seed a pending Reason
    with IDENTICAL override_summary + reason_text — pre-Phase-6A text-match
    lookup would resolve the wrong one (or both, or neither
    deterministically). Strict (session_id, proposal_id, pending) lookup
    isolates per-session."""
    sid_a, oid_a = _seed_pending_override(client)
    sid_b, _oid_b = _seed_pending_override(client)
    # both seedings produce identical override text (intended_step=
    # "formulate_task" + reason="Konstrukt-Definition.") — collision setup
    assert sid_a != sid_b  # distinct sessions

    # Resolve A only
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid_a}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid_a, "clarification": "A-specific clarification"},
    )
    assert r.status_code == 201, r.text

    # Verify corpus state: A is resolved, B is still pending
    from local_pdf.provenienz.reasons import read_reasons

    cfg = client.app.state.config
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=0)
    reasons_a = [r for r in reasons if r.session_id == sid_a]
    reasons_b = [r for r in reasons if r.session_id == sid_b]
    assert len(reasons_a) == 1
    assert reasons_a[0].pending_clarification is False
    assert reasons_a[0].clarification == "A-specific clarification"
    assert len(reasons_b) == 1
    assert reasons_b[0].pending_clarification is True
    assert reasons_b[0].clarification == ""


def test_clarify_resolves_only_reason_for_matching_proposal_under_same_session(client):
    """Phase 6A regression: same session, two pending overrides on
    DIFFERENT proposal_node_ids with identical override text. Strict
    lookup discriminates by proposal_id even within a single session."""
    sid, oid_a = _seed_pending_override(client)
    # Seed a second plan_proposal in the SAME session, decide again
    # with identical text.
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
    plan2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    ).json()
    plan2_id = plan2["node_id"]
    decide2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/decide",
        headers={"X-Auth-Token": "tok"},
        json={
            "proposal_node_id": plan2_id,
            "expert_correction": {
                "intended_step": "formulate_task",
                "reason": "Konstrukt-Definition.",
            },
        },
    ).json()
    assert decide2["clarification"] is not None
    oid_b = decide2["clarification"]["override_node_id"]
    assert oid_a != oid_b

    # Resolve only A
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid_a, "clarification": "A clarification"},
    )
    assert r.status_code == 201

    # Verify corpus state: A's Reason resolved, B's still pending
    from local_pdf.provenienz.reasons import read_reasons

    cfg = client.app.state.config
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=0)
    # Both Reasons share session_id; discriminate by proposal_id
    sess_reasons = [r for r in reasons if r.session_id == sid]
    assert len(sess_reasons) == 2
    by_pending = sorted(sess_reasons, key=lambda r: r.pending_clarification)
    # First is resolved (pending=False), second is still pending (pending=True)
    assert by_pending[0].pending_clarification is False
    assert by_pending[0].clarification == "A clarification"
    assert by_pending[1].pending_clarification is True


def test_clarify_returns_500_when_pending_reason_missing_from_corpus(client):
    """Phase 6A contract: override Node says pending_clarification=True
    but the corresponding Reason is missing from the corpus (e.g. /decide
    write failure, manual corpus corruption). Strict-match returns 500
    with diagnostic — NOT silent new_id() rescue."""
    sid, oid = _seed_pending_override(client)
    # Truncate skills.jsonl to simulate the pending Reason vanishing
    # between /decide and /clarify. Override Node still says pending.
    cfg = client.app.state.config
    from pathlib import Path

    skills_path = Path(cfg.data_root) / "skills" / "skills.jsonl"
    assert skills_path.exists(), f"skills.jsonl missing at {skills_path}"
    skills_path.write_text("")

    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid, "clarification": "anything"},
    )
    assert r.status_code == 500, r.text
    assert "corpus inconsistent" in r.json()["detail"]
    assert "likely /decide write failure" in r.json()["detail"]


def test_clarify_ignores_legacy_reason_with_empty_session_id(client):
    """Phase 6A: a legacy Reason with session_id='' / proposal_id=''
    (pre-Phase-6A format with no marker lines, OR a Reason explicitly
    written with empty IDs) MUST NOT match strict-lookup. The legacy
    record stays untouched in the corpus and the /clarify resolves
    only the new pending Reason for the actual session.

    Also asserts the legacy Reason is STILL IN THE CORPUS after /clarify —
    proves it wasn't accidentally mutated or tombstoned by the resolve
    path (advisor-flagged: makes the immutability contract explicit)."""
    cfg = client.app.state.config
    # Pre-seed a legacy Reason with empty session_id/proposal_id and a
    # distinctive reason_text we can recognize later.
    from local_pdf.provenienz.reasons import Reason, append_reason, read_reasons

    legacy_marker = "legacy-from-before-phase-6A-distinct-marker-xyz"
    append_reason(
        cfg.data_root,
        Reason(
            reason_id="",
            step_kind="extract_claims",
            session_id="",
            proposal_id="",
            proposal_summary="legacy proposal",
            override_summary="formulate_task",
            reason_text=legacy_marker,
            actor="human",
        ),
    )

    # Now run a normal /decide+/clarify cycle in a real session
    sid, oid = _seed_pending_override(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={"override_node_id": oid, "clarification": "real clarification"},
    )
    assert r.status_code == 201, r.text

    # Corpus state: legacy Reason still present AND untouched, new
    # session's Reason resolved with the clarification.
    reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=0)
    legacy_reasons = [r for r in reasons if r.reason_text == legacy_marker]
    assert len(legacy_reasons) == 1
    # Untouched: still has empty session_id, no clarification, not pending
    # (it was never pending in the first place since we appended it
    # without pending=True)
    assert legacy_reasons[0].session_id == ""
    assert legacy_reasons[0].proposal_id == ""
    assert legacy_reasons[0].clarification == ""
    assert legacy_reasons[0].pending_clarification is False

    # And the actual new Reason is resolved correctly
    new_reasons = [r for r in reasons if r.session_id == sid]
    assert len(new_reasons) == 1
    assert new_reasons[0].clarification == "real clarification"
    assert new_reasons[0].pending_clarification is False
