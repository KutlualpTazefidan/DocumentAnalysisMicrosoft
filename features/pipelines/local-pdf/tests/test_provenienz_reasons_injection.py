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

    def complete(self, *, messages, model):
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
