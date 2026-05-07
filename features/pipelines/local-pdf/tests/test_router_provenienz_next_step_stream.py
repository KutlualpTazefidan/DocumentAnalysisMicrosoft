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
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda anchor, goal, available_steps, tools_summary, *, extra_system="": {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "Chunk hat noch keine extrahierten Aussagen.",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
        },
    )
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
