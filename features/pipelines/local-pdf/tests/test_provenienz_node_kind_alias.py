"""Phase-3 alias-on-read tests for the legacy expert_correction → new
Node-Kind mapping in the session-detail endpoint, plus the
/capability-requests aggregator's expanded kind filter.

These exercise the read-path layered on top of legacy data: events.jsonl
is append-only, so post-Phase-3 the canvas + wishlist consumers must
present pre-Phase-3 expert_correction Nodes through the new typed lens
without touching the underlying records.
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
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _seed_session_with_chunk(client) -> tuple[str, str]:
    """Bootstrap a doc + provenienz session anchored on one chunk so we
    have a session-dir to write legacy Nodes into via the storage API."""
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
    return slug, sid


def _seed_legacy_expert_correction(
    client, sid: str, *, is_unimplemented: bool, intended_step: str
) -> tuple[str, str | None]:
    """Append a Phase-1-shape expert_correction Node directly into the
    session-dir (bypassing the writer, which is now Phase-3-shaped).
    When is_unimplemented=True, also append the parallel legacy
    capability_request Node with actor='human' so the test mirrors
    real pre-Phase-3 data."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None, f"session dir for {sid} not found"

    ec = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="expert_correction",
            payload={
                "intended_step": intended_step,
                "intended_args": {},
                "reason": "legacy override",
                "target_proposal_node_id": "plan-legacy",
                "target_step_kind": "extract_claims",
                "is_unimplemented": is_unimplemented,
            },
            actor="human",
        ),
    )
    cr_id: str | None = None
    if is_unimplemented:
        cr = append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="capability_request",
                payload={
                    "name": intended_step,
                    "description": "legacy override",
                    "target_expert_correction_node_id": ec.node_id,
                    "target_proposal_node_id": "plan-legacy",
                },
                actor="human",
            ),
        )
        cr_id = cr.node_id
    return ec.node_id, cr_id


# ── session-detail alias-on-read ───────────────────────────────────────


def test_session_detail_aliases_legacy_known_step_to_expert_step_override(client):
    """Legacy expert_correction + is_unimplemented=False reads as
    expert_step_override in the session-detail payload — the canvas
    sees the new Phase-3 kind without any rewrite to events.jsonl."""
    _slug, sid = _seed_session_with_chunk(client)
    ec_id, _ = _seed_legacy_expert_correction(
        client, sid, is_unimplemented=False, intended_step="formulate_task"
    )
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    aliased = next(n for n in sess["nodes"] if n["node_id"] == ec_id)
    assert aliased["kind"] == "expert_step_override"
    # Payload is untouched (is_unimplemented stays on legacy records
    # forever; the discriminator is now the Node-Kind).
    assert aliased["payload"]["is_unimplemented"] is False
    assert aliased["payload"]["intended_step"] == "formulate_task"


def test_session_detail_aliases_legacy_unimplemented_and_suppresses_human_cr(client):
    """Legacy expert_correction + is_unimplemented=True reads as
    expert_method_request AND the parallel legacy capability_request
    (actor='human', target_expert_correction_node_id pointing at the
    EC) is suppressed from the node list — the canvas shows ONE tile
    per expert-prescribed gap, matching the post-Phase-3 shape."""
    _slug, sid = _seed_session_with_chunk(client)
    ec_id, cr_id = _seed_legacy_expert_correction(
        client, sid, is_unimplemented=True, intended_step="summarize_section"
    )
    assert cr_id is not None
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    aliased = next(n for n in sess["nodes"] if n["node_id"] == ec_id)
    assert aliased["kind"] == "expert_method_request"
    # Suppressed: the parallel legacy human-CR no longer appears in
    # the session-detail node list.
    assert all(n["node_id"] != cr_id for n in sess["nodes"])


def test_session_detail_passes_agent_emitted_capability_request_through(client):
    """Agent-emitted capability_request (actor='agent') is the
    post-Phase-3 Invariante for the kind. It must pass through the
    alias unchanged."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    agent_cr = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="capability_request",
            payload={"name": "TableComparator", "description": "agent flagged"},
            actor="agent",
        ),
    )
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    surviving = next(n for n in sess["nodes"] if n["node_id"] == agent_cr.node_id)
    assert surviving["kind"] == "capability_request"
    assert surviving["actor"] == "agent"


# ── /capability-requests aggregator widened kind filter ────────────────


def test_capability_requests_aggregator_includes_expert_method_request(client):
    """The aggregator includes the new expert_method_request kind so
    post-Phase-3 wishes surface in the wishlist without any client
    change. Legacy human capability_request Nodes still surface
    directly (aggregator-level dedup is the consumer's job)."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="expert_method_request",
            payload={
                "intended_step": "summarize_section",
                "name": "summarize_section",
                "description": "Expert prescribes",
                "reason": "Expert prescribes",
                "target_proposal_node_id": "plan-x",
            },
            actor="human",
        ),
    )
    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    assert r.status_code == 200
    matches = [req for req in r.json()["requests"] if req["name"] == "summarize_section"]
    assert len(matches) == 1
    assert matches[0]["count"] == 1
    assert matches[0]["examples"][0]["actor"] == "human"


def test_capability_requests_aggregator_still_counts_agent_capability_requests(client):
    """Agent-emitted capability_request Nodes still flow through the
    aggregator post-Phase-3 — the kind invariant is preserved."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="capability_request",
            payload={"name": "TableComparator", "description": "agent flagged"},
            actor="agent",
        ),
    )
    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    matches = [req for req in r.json()["requests"] if req["name"] == "TableComparator"]
    assert len(matches) == 1
    assert matches[0]["examples"][0]["actor"] == "agent"


# ── Direct unit test on the alias helper (no HTTP layer) ───────────────


def test_alias_helper_is_idempotent_on_already_new_kinds():
    """Nodes already carrying the Phase-3 kinds (expert_step_override,
    expert_method_request) pass through the alias helper unchanged.
    Catches regressions where the helper might double-map or strip
    payloads."""
    from local_pdf.provenienz.storage import Node

    new_step_override = Node(
        node_id="n1",
        session_id="s",
        kind="expert_step_override",
        payload={"intended_step": "formulate_task"},
        actor="human",
    )
    new_method_request = Node(
        node_id="n2",
        session_id="s",
        kind="expert_method_request",
        payload={"name": "summarize_section", "description": "x"},
        actor="human",
    )
    out = router_mod._alias_legacy_override_nodes([new_step_override, new_method_request])
    assert out == [new_step_override, new_method_request]
