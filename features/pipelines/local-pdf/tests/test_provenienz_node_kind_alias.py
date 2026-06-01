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


# ── MIXED session: legacy + new co-exist (defence against double-mapping) ──


def test_session_detail_mixed_legacy_and_new_kinds_coexist(client):
    """A session can plausibly carry BOTH a pre-Phase-3 expert_correction
    Node (with the parallel legacy human-CR) AND a post-Phase-3
    expert_method_request Node written by the new writer — e.g. an
    operator running migrations across versions. The alias helper
    must:
      • Map the legacy EC to expert_method_request (driven by
        is_unimplemented=true) and suppress its parallel human-CR.
      • Pass the new expert_method_request through unchanged
        (idempotent — no double-map, no spurious suppression of the
        new Node's payload-folded data).
      • Leave any agent-emitted capability_request untouched.

    Counts both gaps separately in the canvas node list AND in the
    /capability-requests aggregator.
    """
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    legacy_ec_id, legacy_cr_id = _seed_legacy_expert_correction(
        client, sid, is_unimplemented=True, intended_step="legacy_method"
    )
    assert legacy_cr_id is not None

    # Drop a new-shape expert_method_request alongside (different
    # intended_step so the aggregator surfaces both as distinct
    # wishlist entries).
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None
    new_emr = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="expert_method_request",
            payload={
                "intended_step": "new_method",
                "name": "new_method",
                "description": "post-Phase-3 write",
                "reason": "post-Phase-3 write",
                "target_proposal_node_id": "plan-x",
            },
            actor="human",
        ),
    )
    # Agent-emitted CR alongside — must be left untouched.
    agent_cr = append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="capability_request",
            payload={"name": "AgentTool", "description": "agent flagged"},
            actor="agent",
        ),
    )

    # Canvas view via session-detail.
    sess = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    by_id = {n["node_id"]: n for n in sess["nodes"]}
    # Legacy EC aliased to expert_method_request.
    assert by_id[legacy_ec_id]["kind"] == "expert_method_request"
    # Legacy human-CR suppressed.
    assert legacy_cr_id not in by_id
    # New expert_method_request passes through with kind intact + payload preserved.
    assert by_id[new_emr.node_id]["kind"] == "expert_method_request"
    assert by_id[new_emr.node_id]["payload"]["name"] == "new_method"
    # Agent-emitted CR still here.
    assert by_id[agent_cr.node_id]["kind"] == "capability_request"
    assert by_id[agent_cr.node_id]["actor"] == "agent"

    # Aggregator: three distinct gaps surface, each counted once.
    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    requests_by_name = {req["name"]: req for req in r.json()["requests"]}
    # Legacy gap surfaces via the still-present legacy human-CR (the
    # canvas-side suppression doesn't affect this aggregator).
    assert requests_by_name["legacy_method"]["count"] == 1
    assert requests_by_name["legacy_method"]["examples"][0]["actor"] == "human"
    # New gap surfaces via the new expert_method_request kind.
    assert requests_by_name["new_method"]["count"] == 1
    assert requests_by_name["new_method"]["examples"][0]["actor"] == "human"
    # Agent gap unchanged.
    assert requests_by_name["AgentTool"]["count"] == 1
    assert requests_by_name["AgentTool"]["examples"][0]["actor"] == "agent"


def test_alias_helper_does_not_suppress_new_method_request_when_legacy_ec_co_present():
    """Direct unit-level guard: when a legacy EC + a new
    expert_method_request both exist, the suppression rule (which
    targets the parallel legacy human-CR) MUST NOT accidentally drop
    the new Node. The suppression is keyed on
    payload.target_expert_correction_node_id — new method-requests
    don't carry that field, so they're safe by construction; this
    test pins that behaviour."""
    from local_pdf.provenienz.storage import Node

    legacy_ec = Node(
        node_id="ec-legacy",
        session_id="s",
        kind="expert_correction",
        payload={
            "intended_step": "old_method",
            "is_unimplemented": True,
            "target_proposal_node_id": "plan-legacy",
        },
        actor="human",
    )
    legacy_cr = Node(
        node_id="cr-legacy",
        session_id="s",
        kind="capability_request",
        payload={
            "name": "old_method",
            "target_expert_correction_node_id": "ec-legacy",
        },
        actor="human",
    )
    new_emr = Node(
        node_id="emr-new",
        session_id="s",
        kind="expert_method_request",
        payload={
            "intended_step": "new_method",
            "name": "new_method",
            "target_proposal_node_id": "plan-new",
            # Deliberately NO target_expert_correction_node_id field.
        },
        actor="human",
    )

    out = router_mod._alias_legacy_override_nodes([legacy_ec, legacy_cr, new_emr])
    kinds_by_id = {n.node_id: n.kind for n in out}
    # Legacy EC mapped to method_request kind.
    assert kinds_by_id["ec-legacy"] == "expert_method_request"
    # Legacy human-CR suppressed.
    assert "cr-legacy" not in kinds_by_id
    # New expert_method_request passes through unchanged.
    assert kinds_by_id["emr-new"] == "expert_method_request"


def test_alias_helper_does_not_double_map_legacy_known_step():
    """Pin: a legacy EC with is_unimplemented=false maps to
    expert_step_override exactly once. No re-mapping back to
    expert_correction or onward to expert_method_request even on
    repeated invocation (defends against the alias being applied
    twice in some future composition)."""
    from local_pdf.provenienz.storage import Node

    legacy_ec = Node(
        node_id="ec-legacy",
        session_id="s",
        kind="expert_correction",
        payload={
            "intended_step": "formulate_task",
            "is_unimplemented": False,
            "target_proposal_node_id": "plan-legacy",
        },
        actor="human",
    )

    first_pass = router_mod._alias_legacy_override_nodes([legacy_ec])
    assert len(first_pass) == 1
    assert first_pass[0].kind == "expert_step_override"
    # Idempotence: applying the alias to its own output is a no-op.
    second_pass = router_mod._alias_legacy_override_nodes(first_pass)
    assert second_pass == first_pass


# ── Phase-4: count_by_actor + canonical sort tiebreaker ─────────────────


def test_capability_requests_aggregator_count_by_actor_mixed_method(client):
    """Mixed actors on the same name: 2 expert_method_request (human) +
    1 capability_request (agent) collapse into one wishlist entry whose
    count_by_actor splits cleanly. Pins the dual-purpose sub-count
    behaviour the Phase-4 UI relies on."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    for _ in range(2):
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
    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="capability_request",
            payload={"name": "summarize_section", "description": "agent flagged"},
            actor="agent",
        ),
    )

    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    matches = [req for req in r.json()["requests"] if req["name"] == "summarize_section"]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["count"] == 3
    assert entry["count_by_actor"] == {"human": 2, "agent": 1}
    assert entry["count_by_actor"]["human"] + entry["count_by_actor"]["agent"] == entry["count"]


def test_capability_requests_aggregator_count_by_actor_agent_only(client):
    """Pure-agent method: 3 capability_request Nodes (actor='agent')
    bucket entirely to the agent side, leaving human at 0."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    for _ in range(3):
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
    entry = matches[0]
    assert entry["count"] == 3
    assert entry["count_by_actor"] == {"human": 0, "agent": 3}


def test_capability_requests_aggregator_count_by_actor_human_only_mixed_legacy_and_new(client):
    """Legacy human capability_request + post-Phase-3
    expert_method_request on the same name both bucket as human.
    Confirms the aggregator treats the two kinds as equivalent
    expert-prescribed signal sources (no canvas-style suppression
    leaking into this path)."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    # Legacy human-actor capability_request — no
    # target_expert_correction_node_id, so the canvas-side suppression
    # rule doesn't kick in (and the aggregator doesn't apply it anyway).
    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="capability_request",
            payload={"name": "legacy_x_human", "description": "pre-Phase-3 human capture"},
            actor="human",
        ),
    )
    # New-shape expert_method_request, same name.
    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="expert_method_request",
            payload={
                "intended_step": "legacy_x_human",
                "name": "legacy_x_human",
                "description": "post-Phase-3 write",
                "reason": "post-Phase-3 write",
                "target_proposal_node_id": "plan-x",
            },
            actor="human",
        ),
    )

    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    matches = [req for req in r.json()["requests"] if req["name"] == "legacy_x_human"]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["count"] == 2
    assert entry["count_by_actor"] == {"human": 2, "agent": 0}


def test_capability_requests_aggregator_count_by_actor_defaults_unknown_actor_to_agent(client):
    """Only the literal "human" string counts toward the human bucket.
    Empty strings, unknown values, and the canonical "agent" all fall
    into the agent bucket. Pins that the response shape carries exactly
    two keys ("human", "agent") — no third bucket like "?" leaks
    through."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    for actor_value in ("", "bot", "agent"):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="capability_request",
                payload={"name": "unknown_method_actor_test", "description": "x"},
                actor=actor_value,
            ),
        )

    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    matches = [req for req in r.json()["requests"] if req["name"] == "unknown_method_actor_test"]
    assert len(matches) == 1
    entry = matches[0]
    assert entry["count"] == 3
    assert entry["count_by_actor"] == {"human": 0, "agent": 3}
    # Response shape invariant: exactly two buckets, no orphan keys.
    assert set(entry["count_by_actor"].keys()) == {"human", "agent"}


def test_capability_requests_aggregator_count_by_actor_sum_equals_count_invariant(client):
    """Property-style guard: for every wishlist entry the API returns,
    count_by_actor.human + count_by_actor.agent == count. Cross-default-
    consistency invariant — the backend bucketing never produces
    orphaned counts, regardless of the actor-mix on the underlying
    Nodes."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    # method_a: 3 agent + 2 human → count=5
    for _ in range(3):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="capability_request",
                payload={"name": "method_a", "description": "x"},
                actor="agent",
            ),
        )
    for _ in range(2):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="expert_method_request",
                payload={
                    "intended_step": "method_a",
                    "name": "method_a",
                    "description": "x",
                    "reason": "x",
                    "target_proposal_node_id": "plan-x",
                },
                actor="human",
            ),
        )
    # method_b: 1 agent + 4 human → count=5
    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="capability_request",
            payload={"name": "method_b", "description": "x"},
            actor="agent",
        ),
    )
    for _ in range(4):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="expert_method_request",
                payload={
                    "intended_step": "method_b",
                    "name": "method_b",
                    "description": "x",
                    "reason": "x",
                    "target_proposal_node_id": "plan-x",
                },
                actor="human",
            ),
        )

    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    payload = r.json()
    assert len(payload["requests"]) >= 2
    for entry in payload["requests"]:
        cba = entry["count_by_actor"]
        assert cba["human"] + cba["agent"] == entry["count"], (
            f"sum invariant broken for {entry['name']!r}: "
            f"{cba['human']} + {cba['agent']} != {entry['count']}"
        )


def test_capability_requests_aggregator_sort_tiebreaker_prefers_higher_human_count(client):
    """Three methods all carrying count=3 must order by descending
    human-count: alpha (3h/0a) → beta (1h/2a) → gamma (0h/3a). Pins
    the expert-prescribed-ranks-first tiebreaker introduced in Step 1."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    # alpha_method: 3 human / 0 agent
    for _ in range(3):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="expert_method_request",
                payload={
                    "intended_step": "alpha_method",
                    "name": "alpha_method",
                    "description": "x",
                    "reason": "x",
                    "target_proposal_node_id": "plan-x",
                },
                actor="human",
            ),
        )
    # beta_method: 1 human / 2 agent
    append_node(
        sd,
        Node(
            node_id=new_id(),
            session_id=sid,
            kind="expert_method_request",
            payload={
                "intended_step": "beta_method",
                "name": "beta_method",
                "description": "x",
                "reason": "x",
                "target_proposal_node_id": "plan-x",
            },
            actor="human",
        ),
    )
    for _ in range(2):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="capability_request",
                payload={"name": "beta_method", "description": "x"},
                actor="agent",
            ),
        )
    # gamma_method: 0 human / 3 agent
    for _ in range(3):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="capability_request",
                payload={"name": "gamma_method", "description": "x"},
                actor="agent",
            ),
        )

    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    names_in_order = [
        req["name"]
        for req in r.json()["requests"]
        if req["name"] in {"alpha_method", "beta_method", "gamma_method"}
    ]
    assert names_in_order == ["alpha_method", "beta_method", "gamma_method"]


def test_capability_requests_aggregator_sort_alphabetical_within_same_human_count(client):
    """Secondary tiebreaker: when count AND human-count match,
    names sort ascending. Pins (-count, -human, +name) as the
    canonical key — "alpha_method" precedes "yankee_method" even
    though both carry count=2 with human=1/agent=1."""
    from local_pdf.provenienz.storage import Node, append_node, new_id

    _slug, sid = _seed_session_with_chunk(client)
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None

    # Seed yankee FIRST to defend against insertion-order leaking into
    # the response shape — only the canonical sort should set order.
    for name in ("yankee_method", "alpha_method"):
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="expert_method_request",
                payload={
                    "intended_step": name,
                    "name": name,
                    "description": "x",
                    "reason": "x",
                    "target_proposal_node_id": "plan-x",
                },
                actor="human",
            ),
        )
        append_node(
            sd,
            Node(
                node_id=new_id(),
                session_id=sid,
                kind="capability_request",
                payload={"name": name, "description": "x"},
                actor="agent",
            ),
        )

    r = client.get("/api/admin/provenienz/capability-requests", headers={"X-Auth-Token": "tok"})
    names_in_order = [
        req["name"]
        for req in r.json()["requests"]
        if req["name"] in {"alpha_method", "yankee_method"}
    ]
    assert names_in_order == ["alpha_method", "yankee_method"]
