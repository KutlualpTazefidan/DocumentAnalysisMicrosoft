"""Phase-3 multi-agent pipeline tests.

When approaches are marked ``mode="active"`` the next_step pipeline
fans out into per-skill LLM calls and a final Coordinator merge. These
tests stub the LLM helpers and verify:

- Active approach text is NOT injected into the Meta-Planner prompt
- Each active approach gets its own ``skill_call:idx`` phase event
- A ``coordinate`` phase fires after the skills with the merged plan
- When no active skills exist, the pipeline matches Phase 1+2 exactly
- Audit captures meta_plan + skill_outputs verbatim
"""

from __future__ import annotations

import io
import json

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.approaches import upsert_approach
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


def _bootstrap(client) -> tuple[str, str]:
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
            "elements": [{"box_id": "p1-b0", "html_snippet": "<p>5.6 kW.</p>"}],
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
    out: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        if not block.strip():
            continue
        ev = "message"
        data: list[str] = []
        for ln in block.split("\n"):
            if ln.startswith("event:"):
                ev = ln.split(":", 1)[1].strip()
            elif ln.startswith("data:"):
                data.append(ln.split(":", 1)[1].strip())
        if data:
            out.append((ev, json.loads("\n".join(data))))
    return out


def _stub_meta(monkeypatch, *, name: str = "extract_claims", reasoning: str = "meta-r"):
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": name,
            "description": "",
            "reasoning": reasoning,
            "goal_alignment": "Ziel: 'x'. Step bringt y.",
            "considered_alternatives": [],
            "confidence": 0.7,
            "tool": None,
            "approach_id": None,
        },
    )


def _stub_skill(monkeypatch, *, suggested: str = "extract_claims", reasoning: str = "skill-r"):
    monkeypatch.setattr(
        router_mod,
        "_llm_active_skill",
        lambda *, skill_name, skill_extra_system, anchor, session_goal, available_steps: {
            "reasoning": f"{skill_name}: {reasoning}",
            "suggested_step": suggested,
            "confidence": 0.85,
        },
    )


def _stub_coordinator(monkeypatch, *, name: str = "extract_claims", reasoning: str = "coord-r"):
    monkeypatch.setattr(
        router_mod,
        "_llm_coordinator",
        lambda **kw: {
            "kind": "executable_step",
            "name": name,
            "description": "",
            "reasoning": reasoning,
            "goal_alignment": "Ziel: 'x'. Coordinator-Wahl bringt y.",
            "considered_alternatives": [],
            "confidence": 0.92,
            "tool": None,
            "approach_id": None,
        },
    )


# ── Backwards-compat: no active approaches → identical to Phase 1+2 ─────


def test_no_active_skills_pipeline_matches_phase_1_2(client, monkeypatch):
    """Without any mode=active approaches, the pipeline emits the same
    5 phases as Phase 1+2 — no skill_call, no coordinate."""
    _stub_meta(monkeypatch)
    sid, chunk_id = _bootstrap(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    events = _parse_sse(r.text)
    started = [e[1]["phase"] for e in events if e[0] == "phase" and e[1]["status"] == "started"]
    assert started == [
        "gather_guidance",
        "gather_tools",
        "llm_call",
        "validate",
        "persist",
    ]


# ── Active approaches → skill_call + coordinate phases fire ────────────


def test_active_approach_triggers_skill_and_coordinator_phases(client, monkeypatch):
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="ziel-fokus",
        step_kinds=["next_step"],
        extra_system="Beziehe deine Begründung wörtlich aufs Ziel.",
        selection_criteria={"anchor_kinds": ["chunk"]},
        mode="active",
    )
    _stub_meta(monkeypatch)
    _stub_skill(monkeypatch, suggested="extract_claims", reasoning="trigger weil text-pflicht")
    _stub_coordinator(monkeypatch, name="extract_claims", reasoning="konsens mit skill")

    sid, chunk_id = _bootstrap(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    events = _parse_sse(r.text)
    started_phases = [
        e[1]["phase"] for e in events if e[0] == "phase" and e[1]["status"] == "started"
    ]
    # Order: gather → tools → meta → skill_call:0 → coordinate → validate → persist
    assert started_phases == [
        "gather_guidance",
        "gather_tools",
        "llm_call",
        "skill_call:0",
        "coordinate",
        "validate",
        "persist",
    ]
    # The skill_call:0 completed event carries the skill's verbatim output.
    skill_done = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "skill_call:0" and e[1]["status"] == "completed"
    )
    assert skill_done["payload"]["approach_name"] == "ziel-fokus"
    assert "trigger weil text-pflicht" in skill_done["payload"]["reasoning"]
    assert skill_done["payload"]["suggested_step"] == "extract_claims"

    # Coordinator output becomes the final plan.
    coord_done = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "coordinate" and e[1]["status"] == "completed"
    )
    assert "konsens mit skill" in coord_done["payload"]["reasoning"]

    complete = next(e[1] for e in events if e[0] == "complete")
    assert complete["node"]["payload"]["reasoning"] == "konsens mit skill"


def test_active_approach_text_not_injected_into_meta_planner(client, monkeypatch):
    """The Meta-Planer must NOT see the active approach's extra_system
    in its prompt — that text only goes to the skill call."""
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="active-only",
        step_kinds=["next_step"],
        extra_system="DIESER_TEXT_DARF_NICHT_INS_META_PROMPT",
        selection_criteria={"anchor_kinds": ["chunk"]},
        mode="active",
    )

    captured: dict = {}

    def _fake_meta(
        anchor, goal, available_steps, tools_summary, *, extra_system="", triggered_from_node=None
    ):
        captured["extra_system"] = extra_system
        return {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "m",
            "goal_alignment": "",
            "considered_alternatives": [],
            "confidence": 0.5,
            "tool": None,
            "approach_id": None,
        }

    monkeypatch.setattr(router_mod, "_llm_next_step", _fake_meta)
    _stub_skill(monkeypatch)
    _stub_coordinator(monkeypatch)

    sid, chunk_id = _bootstrap(client)
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    assert "DIESER_TEXT_DARF_NICHT_INS_META_PROMPT" not in (captured.get("extra_system") or "")


def test_passive_approach_still_text_injected_into_meta(client, monkeypatch):
    """Backwards-compat: a passive approach still gets its text into
    the Meta-Planer's extra_system."""
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="legacy-passive",
        step_kinds=["next_step"],
        extra_system="PASSIVER_TEXT_MUSS_INS_META_PROMPT",
        selection_criteria={"anchor_kinds": ["chunk"]},
        # mode default = "passive"
    )

    captured: dict = {}

    def _fake_meta(
        anchor, goal, available_steps, tools_summary, *, extra_system="", triggered_from_node=None
    ):
        captured["extra_system"] = extra_system
        return {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "m",
            "goal_alignment": "",
            "considered_alternatives": [],
            "confidence": 0.5,
            "tool": None,
            "approach_id": None,
        }

    monkeypatch.setattr(router_mod, "_llm_next_step", _fake_meta)
    sid, chunk_id = _bootstrap(client)
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    assert "PASSIVER_TEXT_MUSS_INS_META_PROMPT" in (captured.get("extra_system") or "")


def test_audit_captures_meta_plan_and_skill_outputs(client, monkeypatch):
    """Multi-agent runs persist meta_plan + skill_outputs in audit so
    the user can reconstruct the L1+L2+L3 reasoning chain."""
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="skill-a",
        step_kinds=["next_step"],
        extra_system="…",
        selection_criteria={"anchor_kinds": ["chunk"]},
        mode="active",
    )
    upsert_approach(
        cfg.data_root,
        name="skill-b",
        step_kinds=["next_step"],
        extra_system="…",
        selection_criteria={"anchor_kinds": ["chunk"]},
        mode="active",
    )
    _stub_meta(monkeypatch, name="extract_claims", reasoning="meta-r")
    _stub_skill(monkeypatch, suggested="extract_claims", reasoning="skill-r")
    _stub_coordinator(monkeypatch, name="extract_claims", reasoning="coord-r")

    sid, chunk_id = _bootstrap(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    node = r.json()
    audit = node["payload"]["audit"]
    assert audit["source_label"].startswith("Was als nächstes? (Multi-Agent")
    assert audit["meta_plan"]["reasoning"] == "meta-r"
    assert len(audit["skill_outputs"]) == 2
    skill_names = {s["skill_name"] for s in audit["skill_outputs"]}
    assert skill_names == {"skill-a", "skill-b"}


def test_two_active_skills_emit_two_skill_call_phases(client, monkeypatch):
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="alpha",
        step_kinds=["next_step"],
        extra_system="…",
        selection_criteria={"anchor_kinds": ["chunk"]},
        mode="active",
    )
    upsert_approach(
        cfg.data_root,
        name="beta",
        step_kinds=["next_step"],
        extra_system="…",
        selection_criteria={"anchor_kinds": ["chunk"]},
        mode="active",
    )
    _stub_meta(monkeypatch)
    _stub_skill(monkeypatch)
    _stub_coordinator(monkeypatch)

    sid, chunk_id = _bootstrap(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    events = _parse_sse(r.text)
    skill_phases = [
        e[1]["phase"]
        for e in events
        if e[0] == "phase"
        and e[1]["phase"].startswith("skill_call:")
        and e[1]["status"] == "started"
    ]
    assert skill_phases == ["skill_call:0", "skill_call:1"]
