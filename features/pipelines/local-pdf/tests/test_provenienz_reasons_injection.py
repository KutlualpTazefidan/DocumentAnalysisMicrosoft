"""Verify the reasons corpus is fetched + threaded into LLM system prompts
+ recorded as guidance_consulted on the resulting ActionProposal."""

from __future__ import annotations

import io
from pathlib import Path  # noqa: TC003
from types import SimpleNamespace

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.reasons import Reason, append_reason
from local_pdf.storage.sidecar import write_mineru


class _FakeClient:
    def __init__(self, response_text: str):
        self._text = response_text
        self.captured_system: str | None = None

    def complete(self, *, messages, model, max_tokens=None, **_):
        for m in messages:
            if m.role == "system":
                self.captured_system = m.content
        return SimpleNamespace(text=self._text)


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _seed_doc(client) -> str:
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
    return slug


def _seed_reason(data_root: Path, step_kind: str, text: str) -> str:
    r = append_reason(
        data_root,
        Reason(
            reason_id="",
            step_kind=step_kind,
            session_id="prev-session",
            proposal_id="prev-prop",
            proposal_summary="Vorher: Auto-Empfehlung",
            override_summary="Vorher: Bessere Korrektur",
            reason_text=text,
            actor="human",
        ),
    )
    return r.reason_id


def test_extract_claims_injects_reasons_into_system_prompt(client, monkeypatch):
    cfg = client.app.state.config
    rid = _seed_reason(cfg.data_root, "extract_claims", "Heuristik nimmt zu viel Boilerplate")
    fake = _FakeClient('["Aussage 1"]')
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")

    slug = _seed_doc(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert r.status_code == 201
    # System prompt contains the reasons block.
    assert fake.captured_system is not None
    assert "Frühere Korrekturen" in fake.captured_system
    assert "Heuristik nimmt zu viel Boilerplate" in fake.captured_system
    # ActionProposal records the guidance ref.
    refs = r.json()["payload"]["guidance_consulted"]
    assert len(refs) == 1
    assert refs[0]["kind"] == "reason"
    assert refs[0]["id"] == rid


def test_evaluate_only_pulls_evaluate_step_kind_reasons(client, monkeypatch):
    """Reasons of unrelated step kinds must NOT leak into another step's prompt."""
    cfg = client.app.state.config
    _seed_reason(
        cfg.data_root, "extract_claims", "irrelevant — sollte nicht in evaluate auftauchen"
    )
    _seed_reason(cfg.data_root, "evaluate", "evaluate-spezifischer Hinweis")

    fake = _FakeClient('{"verdict":"likely-source","confidence":0.9,"reasoning":"r"}')
    fake_ec = _FakeClient('["claim"]')
    # Two clients won't fit through one factory; use a stateful one.
    seq: list[_FakeClient] = []

    def _factory():
        if not seq:
            seq.append(fake_ec)
        else:
            seq.append(fake)
        return seq[-1]

    monkeypatch.setattr(router_mod, "get_llm_client", _factory)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    # _llm_pre_reason (ReAct "Thought" layer prepended to every step)
    # also calls get_llm_client. Without this stub it would consume the
    # next client in seq before _llm_extract_claims even gets to run,
    # leaving the actual step with the wrong fake client and tripping
    # a JSON-parse RuntimeError. Returning "" matches its real-world
    # failure-mode shape (the field is best-effort).
    monkeypatch.setattr(router_mod, "_llm_pre_reason", lambda *a, **k: "")

    slug = _seed_doc(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    # Walk to a search_result node so we can hit /evaluate.
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
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
    # Stub formulate_task + search through monkey-patches so we don't need real LLM
    # calls. We need a search_result node to evaluate against.
    monkeypatch.setattr(router_mod, "_llm_formulate_task", lambda c, p, *, extra_system="": "Q")
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
    # Need at least one elements row for InDocSearcher to find — already have p1-b0
    # (excluded as root). Add p2-b0:
    write_mineru(
        cfg.data_root,
        slug,
        {
            "elements": [
                {"box_id": "p1-b0", "html_snippet": "<p>X</p>"},
                {"box_id": "p2-b0", "html_snippet": "<p>Q matches Q</p>"},
            ],
            "diagnostics": [],
        },
    )
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
    sr_id = next(n["node_id"] for n in d3["spawned_nodes"] if n["kind"] == "search_result")
    # NOW the evaluate call. Should pull only "evaluate" step_kind reasons.
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/evaluate",
        headers={"X-Auth-Token": "tok"},
        json={"search_result_node_id": sr_id, "against_claim_id": claim_id},
    )
    assert r.status_code == 201
    # Last fake-client invocation = evaluate.
    sys_prompt = seq[-1].captured_system or ""
    assert "evaluate-spezifischer Hinweis" in sys_prompt
    assert "irrelevant — sollte nicht in evaluate auftauchen" not in sys_prompt


def test_rga_pending_reason_surfaces_in_planner_prompt_then_clarification_lands(
    client,
    monkeypatch,
):
    """Phase-RGA write-now+pending: a gap-detected expert override
    writes the Reason IMMEDIATELY with pending_clarification=True.
    That pending Reason MUST surface in the planner's "Frühere
    Korrekturen" block on the next /next-step run — pending raw
    expert reasoning is still signal. After /clarify resolves, the
    read-side dedup collapses the two append-events to exactly one
    record, and the prompt-injector still emits the reason exactly
    once (no double-render from the pending + resolved events).
    """
    from local_pdf.provenienz.reasons import read_reasons

    cfg = client.app.state.config

    # Enable RGA and force the evaluator to a deterministic gap verdict.
    monkeypatch.setattr(router_mod, "_rga_enabled", lambda: True)
    monkeypatch.setattr(
        router_mod,
        "_llm_evaluate_plan_override",
        lambda anchor, goal, reason, intended: {
            "ranked_steps_raw": ["extract_claims", "propose_stop"],
            "ranked_steps_canonical": ["extract_claims", "propose_stop"],
            "rank": None,
            "score": 1,  # < _RGA_DEFAULT_THRESHOLD (3) → gap_detected=True
            "rationale": "intended_step absent from plausible list",
            "parse_error": False,
        },
    )
    # Planner LLM stub — survives all three /next-step calls. Bypasses
    # get_llm_client entirely so we don't need a _FakeClient here.
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda anchor, goal, available_steps, tools_summary, **kwargs: {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "planner stub",
            "considered_alternatives": [],
            "confidence": 0.8,
            "tool": None,
            "approach_id": None,
            "goal_alignment": "",
        },
    )

    # Bootstrap a session.
    slug = _seed_doc(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")

    # 1) /next-step → plan_proposal → /decide with a gap-detected override.
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
                "reason": "Konstrukt-Definition, kein Faktum.",
            },
        },
    ).json()
    assert decide["clarification"] is not None
    override_node_id = decide["clarification"]["override_node_id"]

    # 2) Corpus contains exactly ONE Reason with pending=True.
    pending_reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=10)
    assert len(pending_reasons) == 1
    assert pending_reasons[0].pending_clarification is True
    assert pending_reasons[0].clarification == ""
    assert pending_reasons[0].reason_text == "Konstrukt-Definition, kein Faktum."

    # Install a capture wrapper around _gather_guidance_split BEFORE the
    # second /next-step so we see the extra_system that the planner-prompt
    # actually receives.
    captured: dict = {}
    real_gather = router_mod._gather_guidance_split

    def _capture_gather(*args, **kwargs):
        result = real_gather(*args, **kwargs)
        captured["extra_system"] = result[0]
        return result

    monkeypatch.setattr(router_mod, "_gather_guidance_split", _capture_gather)

    # 3) /next-step #2 — pending Reason MUST surface in "Frühere Korrekturen".
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    assert "extra_system" in captured
    extra_system_pending = captured["extra_system"]
    assert "Frühere Korrekturen" in extra_system_pending
    assert "Konstrukt-Definition, kein Faktum" in extra_system_pending

    # 4) Resolve via /clarify (submit-path).
    resolve = client.post(
        f"/api/admin/provenienz/sessions/{sid}/clarify",
        headers={"X-Auth-Token": "tok"},
        json={
            "override_node_id": override_node_id,
            "clarification": (
                "Der Term verweist auf eine Variable, nicht ein empirisches "
                "Faktum — formulate_task ist passend."
            ),
        },
    )
    assert resolve.status_code == 201

    # 5) read_reasons dedups (latest-wins, dict-by-reason_id):
    #    pending + resolved append-events collapse to ONE record.
    resolved_reasons = read_reasons(cfg.data_root, step_kind="extract_claims", last_n=10)
    assert len(resolved_reasons) == 1, (
        "Dedup must collapse pending + resolved append-events to one record; "
        f"got {len(resolved_reasons)} entries."
    )
    assert resolved_reasons[0].pending_clarification is False
    assert resolved_reasons[0].clarification.startswith("Der Term verweist")
    assert resolved_reasons[0].reason_id == pending_reasons[0].reason_id

    # 6) /next-step #3 — prompt-injector still emits the reason exactly
    # ONCE (no double-count from the two append-events on the same
    # reason_id). This is the load-bearing dedup-in-prompt invariant.
    captured.clear()
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    assert "extra_system" in captured
    extra_system_resolved = captured["extra_system"]
    assert "Frühere Korrekturen" in extra_system_resolved
    assert "Konstrukt-Definition, kein Faktum" in extra_system_resolved
    # Dedup invariant: the reason_text appears exactly ONCE in the
    # rendered block (not twice from pending + resolved events).
    assert extra_system_resolved.count("Konstrukt-Definition, kein Faktum") == 1
    # After /clarify, the prompt-injector emits the Klarstellung line
    # for the resolved Reason, so the planner sees the enriched
    # reasoning on subsequent runs.
    assert "Klarstellung:" in extra_system_resolved
    assert "Der Term verweist" in extra_system_resolved


def test_legacy_reasons_with_empty_session_id_still_surface_in_guidance_block(
    client,
    monkeypatch,
):
    """Phase 6A: legacy NOTE-skills with empty session_id + proposal_id
    (pre-Phase-6A records or those written with empty IDs) MUST still
    surface in _gather_reason_guidance's "Frühere Korrekturen" block.
    The read-path for the most-used consumer (prompt-injector) is
    untouched by Phase 6A's strict-lookup change in /clarify."""
    cfg = client.app.state.config

    # Seed a legacy Reason with explicitly empty session_id/proposal_id
    from local_pdf.provenienz.reasons import Reason, append_reason

    append_reason(
        cfg.data_root,
        Reason(
            reason_id="",
            step_kind="extract_claims",
            session_id="",  # legacy
            proposal_id="",  # legacy
            proposal_summary="Vorher: legacy proposal",
            override_summary="legacy override",
            reason_text="legacy reasoning that must still surface",
            actor="human",
        ),
    )

    fake = _FakeClient('["Aussage 1"]')
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    monkeypatch.setattr(router_mod, "_llm_pre_reason", lambda *a, **k: "")

    slug = _seed_doc(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert r.status_code == 201
    assert fake.captured_system is not None
    # The legacy reason_text MUST appear in the planner's prompt
    assert "legacy reasoning that must still surface" in fake.captured_system
    assert "Frühere Korrekturen" in fake.captured_system


def test_no_reasons_yields_empty_guidance_block(client, monkeypatch):
    fake = _FakeClient('["Aussage"]')
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    slug = _seed_doc(client)
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}", headers={"X-Auth-Token": "tok"}
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert r.status_code == 201
    assert fake.captured_system is not None
    assert "Frühere Korrekturen" not in fake.captured_system
    assert r.json()["payload"]["guidance_consulted"] == []
