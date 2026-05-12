"""Smoke tests for the SSE variant of /next-step.

The non-streaming endpoint shares the same phase generator, so testing
the stream variant exercises both code paths end-to-end.
"""

from __future__ import annotations

import io
import json

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.storage.sidecar import write_mineru


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))

    def _fake_next_step(
        anchor,
        goal,
        available_steps,
        tools_summary,
        *,
        extra_system="",
        triggered_from_node=None,
    ):
        return {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "Chunk hat noch keine extrahierten Aussagen.",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
        }

    monkeypatch.setattr(router_mod, "_llm_next_step", _fake_next_step)
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _bootstrap_session(client) -> tuple[str, str]:
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
            "elements": [{"box_id": "p1-b0", "html_snippet": "<p>Wärmeleistung 5.6 kW.</p>"}],
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


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """Tiny SSE parser: yields (event_name, data_dict) for each block."""
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def test_stream_emits_all_five_phases_and_completes(client):
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    assert r.status_code == 200, r.text
    assert "text/event-stream" in r.headers["content-type"]
    events = _parse_sse(r.text)

    phase_events = [e for e in events if e[0] == "phase"]
    complete_events = [e for e in events if e[0] == "complete"]

    # Each of the five phases emits started + completed.
    phase_names_started = [e[1]["phase"] for e in phase_events if e[1]["status"] == "started"]
    assert phase_names_started == [
        "gather_guidance",
        "gather_tools",
        "llm_call",
        "validate",
        "persist",
    ]
    phase_names_completed = [e[1]["phase"] for e in phase_events if e[1]["status"] == "completed"]
    assert phase_names_completed == phase_names_started

    # Exactly one complete event with the persisted Node.
    assert len(complete_events) == 1
    node = complete_events[0][1]["node"]
    assert node["kind"] == "plan_proposal"
    assert node["payload"]["name"] == "extract_claims"
    assert node["payload"]["anchor_node_id"] == chunk_node_id


def test_stream_validate_phase_demotes_invalid_step(client, monkeypatch):
    """LLM picks 'search' for a chunk where only extract_claims/propose_stop
    are valid. The validate phase clamps it to manual_review."""
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": "search",  # not in the chunk-anchor whitelist
            "description": "",
            "reasoning": "halluzinierter Step-Name",
            "considered_alternatives": [],
            "confidence": 0.7,
            "tool": None,
            "approach_id": None,
        },
    )
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    events = _parse_sse(r.text)
    validate_completed = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "validate" and e[1]["status"] == "completed"
    )
    assert validate_completed["payload"]["ok"] is False
    assert validate_completed["payload"]["demoted_from"] == "search"
    assert validate_completed["payload"]["final_kind"] == "manual_review"

    complete = next(e[1] for e in events if e[0] == "complete")
    assert complete["node"]["kind"] == "manual_review"


def test_validate_phase_auto_promotes_misclassified_manual_review(client, monkeypatch):
    """LLM picks a registered executable step (extract_claims) but
    wrongly tags it as kind=manual_review. The validate phase promotes
    it back to executable_step so the user gets a Akzeptieren button,
    not a 'Mensch-Aufgabe' dead end.
    """
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "manual_review",
            "name": "extract_claims",
            "description": "Mensch sollte das prüfen",
            "reasoning": "Aussagen extrahieren erfordert Urteil",
            "considered_alternatives": [],
            "confidence": 0.7,
            "tool": None,
            "approach_id": None,
        },
    )
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    events = _parse_sse(r.text)
    validate_completed = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "validate" and e[1]["status"] == "completed"
    )
    assert validate_completed["payload"]["promoted_from"] == "manual_review"
    assert validate_completed["payload"]["final_kind"] == "executable_step"
    assert validate_completed["payload"]["final_name"] == "extract_claims"

    complete = next(e[1] for e in events if e[0] == "complete")
    assert complete["node"]["kind"] == "plan_proposal"
    assert complete["node"]["payload"]["kind"] == "executable_step"
    assert complete["node"]["payload"]["name"] == "extract_claims"
    # Description carries the Auto-promote marker so the audit trail
    # makes the LLM precedence error visible to reviewers.
    assert "Auto-promoted" in complete["node"]["payload"]["description"]


def test_validate_phase_aliases_decompose_hit_to_extract_claims_on_chunk(client, monkeypatch):
    """LLM picks 'decompose_hit' on a chunk anchor — should map to
    'extract_claims' (the canonical 'split into atomic claims' step
    on chunks) instead of demoting to manual_review.
    """
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": "decompose_hit",
            "description": "Chunk in Teil-Aussagen zerlegen",
            "reasoning": "Mehrere messbare Aussagen im Chunk",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
        },
    )
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    events = _parse_sse(r.text)
    validate_completed = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "validate" and e[1]["status"] == "completed"
    )
    assert validate_completed["payload"]["aliased_from"] == "decompose_hit"
    assert validate_completed["payload"]["demoted_from"] is None
    assert validate_completed["payload"]["final_name"] == "extract_claims"

    complete = next(e[1] for e in events if e[0] == "complete")
    assert complete["node"]["payload"]["name"] == "extract_claims"


def test_validate_phase_aliases_bare_verb_extract_to_extract_claims(client, monkeypatch):
    """Bare-verb hallucination ('extract') on a chunk -> extract_claims."""
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": "extract",
            "description": "",
            "reasoning": "Aussagen rausziehen",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
        },
    )
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    events = _parse_sse(r.text)
    complete = next(e[1] for e in events if e[0] == "complete")
    assert complete["node"]["payload"]["name"] == "extract_claims"
    assert "Auto-mapped from 'extract'" in complete["node"]["payload"]["description"]


def test_validate_phase_aliases_decompose_hit_to_formulate_task_on_claim(client, monkeypatch):
    """LLM picks the deprecated 'decompose_hit' on a claim anchor.
    The alias remap maps it to 'formulate_task' (the canonical
    successor for a claim) instead of demoting to manual_review.
    """
    from local_pdf.provenienz.storage import Node, append_node, new_id

    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": "decompose_hit",  # DEPRECATED — should be aliased
            "description": "Claim hat mehrere Teil-Aussagen",
            "reasoning": "Zerlegung sinnvoll",
            "considered_alternatives": [],
            "confidence": 0.7,
            "tool": None,
            "approach_id": None,
        },
    )
    sid, _chunk_node_id = _bootstrap_session(client)
    # Plant a claim node directly so we don't touch _llm_extract_claims
    # or the rest of the LLM-driven extract chain.
    cfg = client.app.state.config
    sd = router_mod._find_session_dir(cfg.data_root, sid)
    assert sd is not None
    claim_id = new_id()
    append_node(
        sd,
        Node(
            node_id=claim_id,
            session_id=sid,
            kind="claim",
            payload={"text": "Test claim", "goal": ""},
            actor="human",
        ),
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": claim_id},
    )
    events = _parse_sse(r.text)
    validate_completed = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "validate" and e[1]["status"] == "completed"
    )
    # Alias fired; no demotion to manual_review.
    assert validate_completed["payload"]["aliased_from"] == "decompose_hit"
    assert validate_completed["payload"]["demoted_from"] is None
    assert validate_completed["payload"]["final_kind"] == "executable_step"
    assert validate_completed["payload"]["final_name"] == "formulate_task"

    complete = next(e[1] for e in events if e[0] == "complete")
    assert complete["node"]["kind"] == "plan_proposal"
    assert complete["node"]["payload"]["name"] == "formulate_task"
    assert "Auto-mapped from 'decompose_hit'" in complete["node"]["payload"]["description"]


def test_validate_phase_keeps_genuine_manual_review_when_name_is_not_a_step(client, monkeypatch):
    """Auto-promote only fires when the LLM-picked name matches an
    available executable step. A legitimate manual_review (e.g.
    'Juristische Bewertung') stays manual_review.
    """
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "manual_review",
            "name": "Juristische Bewertung",
            "description": "Konsultation mit Rechtsabteilung",
            "reasoning": "Compliance-Frage",
            "considered_alternatives": [],
            "confidence": 0.7,
            "tool": None,
            "approach_id": None,
        },
    )
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    events = _parse_sse(r.text)
    validate_completed = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "validate" and e[1]["status"] == "completed"
    )
    assert validate_completed["payload"]["promoted_from"] is None
    assert validate_completed["payload"]["final_kind"] == "manual_review"
    assert validate_completed["payload"]["final_name"] == "Juristische Bewertung"


def test_non_streaming_endpoint_still_returns_node(client):
    """Ensure /next-step (non-streaming) still works after the
    refactor — both endpoints share _next_step_run."""
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_node_id},
    )
    assert r.status_code == 201, r.text
    node = r.json()
    assert node["kind"] == "plan_proposal"
    assert node["payload"]["name"] == "extract_claims"
    # Audit is captured the same way as before.
    assert "audit" in node["payload"]
    assert node["payload"]["audit"]["source_label"].startswith("Was als nächstes?")
    # Direct-anchor invocations (no click-trail) persist the field as
    # an empty string — keeps the payload shape stable.
    assert node["payload"]["triggered_from_node_id"] == ""


def test_triggered_from_node_id_persists_on_plan_proposal(client, monkeypatch):
    """When the request carries triggered_from_node_id, the spawned
    plan_proposal persists it AND the planner sees the trail node as
    extra context (when it resolves to an evaluation Node)."""
    captured: dict = {}

    def _fake(
        anchor, goal, available_steps, tools_summary, *, extra_system="", triggered_from_node=None
    ):
        captured["triggered_from_node"] = triggered_from_node
        return {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "r",
            "considered_alternatives": [],
            "confidence": 0.7,
            "tool": None,
            "approach_id": None,
        }

    monkeypatch.setattr(router_mod, "_llm_next_step", _fake)
    sid, chunk_node_id = _bootstrap_session(client)
    # Use the chunk_node_id itself as the trail — backend only treats
    # an evaluation-kind trail specially, but plain non-evaluation
    # trails still get persisted on the spawned node.
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={
            "anchor_node_id": chunk_node_id,
            "triggered_from_node_id": chunk_node_id,
        },
    )
    assert r.status_code == 201, r.text
    node = r.json()
    assert node["payload"]["triggered_from_node_id"] == chunk_node_id
    # Trail Node was resolved and forwarded to the LLM call.
    assert captured["triggered_from_node"] is not None
    assert captured["triggered_from_node"].node_id == chunk_node_id


def test_triggered_from_unresolvable_node_is_silently_dropped(client):
    """An unknown trail id doesn't 404 — it just resolves to None and
    the spawned node still records the raw id for forensics."""
    sid, chunk_node_id = _bootstrap_session(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={
            "anchor_node_id": chunk_node_id,
            "triggered_from_node_id": "does-not-exist",
        },
    )
    assert r.status_code == 201, r.text
    # Raw id flows through to the persisted payload — the layout
    # passes silently skip it because g.byId.has() returns false.
    assert r.json()["payload"]["triggered_from_node_id"] == "does-not-exist"


def test_goal_alignment_field_flows_through_pipeline(monkeypatch):
    """The Phase-1.5 goal_alignment field is parsed from the LLM,
    surfaced in the llm_call phase event, and persisted on the node."""
    import io as _io

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", "/tmp/pytest-goal-align-prov")
    # Reset data dir.
    import shutil

    shutil.rmtree("/tmp/pytest-goal-align-prov", ignore_errors=True)
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "Aussagen liegen noch nicht vor.",
            "goal_alignment": "Ziel: 'Belege finden'. Dieser Step liefert "
            "extrahierte Aussagen, die wir dann einzeln belegen.",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
        },
    )
    client = TestClient(create_app())
    upload = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", _io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    slug = upload.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {"elements": [{"box_id": "p1-b0", "html_snippet": "<p>x</p>"}], "diagnostics": []},
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
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk["node_id"]},
    )
    events = _parse_sse(r.text)
    llm_completed = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "llm_call" and e[1]["status"] == "completed"
    )
    assert "Belege finden" in llm_completed["payload"]["goal_alignment"]
    # Final persisted node carries the field too.
    complete = next(e[1] for e in events if e[0] == "complete")
    assert "Belege finden" in complete["node"]["payload"]["goal_alignment"]


def test_strip_json_fence_removes_qwen3_thinking_block():
    """Qwen3 / DeepSeek-R1 prepend <think>…</think> reasoning before the
    JSON output. The parser must strip them so downstream json.loads
    gets clean input."""
    from local_pdf.api.routers.admin.provenienz import _strip_json_fence

    raw = (
        "<think>\n"
        "Okay, the user wants me to extract claims. Let me think.\n"
        "</think>\n"
        '{"kind": "executable_step", "name": "extract_claims"}'
    )
    cleaned = _strip_json_fence(raw)
    assert cleaned.startswith("{")
    assert "<think>" not in cleaned
    assert '"kind"' in cleaned


def test_strip_json_fence_handles_truncated_thinking_block():
    """If the model ran out of tokens mid-think, only the opening tag
    survives. We still try to parse what's there by jumping to the
    first ``{`` / ``[``."""
    from local_pdf.api.routers.admin.provenienz import _strip_json_fence

    raw = '<think>truncated mid-thought... {"kind": "executable_step"}'
    cleaned = _strip_json_fence(raw)
    assert cleaned.startswith("{")
    assert "<think>" not in cleaned


def test_goal_alignment_defaults_to_empty_when_llm_omits_it(monkeypatch):
    """LLM returns a plan dict without the new field — parser tolerates
    and the empty string flows through (UI shows the warning)."""
    import io as _io
    import shutil

    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", "/tmp/pytest-goal-align-empty")
    shutil.rmtree("/tmp/pytest-goal-align-empty", ignore_errors=True)

    # Stub at the json.loads level — easier than monkey-patching
    # _llm_next_step here. Use a fake LLM client that returns JSON
    # without goal_alignment.
    class _FakeCompletion:
        text = (
            '{"kind": "executable_step", "name": "extract_claims", '
            '"reasoning": "...", "confidence": 0.7}'
        )

    class _FakeClient:
        def complete(self, *a, **k):
            return _FakeCompletion()

    monkeypatch.setattr(router_mod, "get_llm_client", lambda: _FakeClient())
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test")

    client = TestClient(create_app())
    upload = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={"file": ("d.pdf", _io.BytesIO(b"%PDF-1.4\n%%EOF\n"), "application/pdf")},
    )
    slug = upload.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {"elements": [{"box_id": "p1-b0", "html_snippet": "<p>x</p>"}], "diagnostics": []},
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
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk["node_id"]},
    )
    node = r.json()
    # Field exists, defaults to empty string when LLM omits.
    assert node["payload"]["goal_alignment"] == ""
