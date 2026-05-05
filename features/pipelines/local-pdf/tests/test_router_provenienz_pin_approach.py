"""Pin/unpin sessions to approaches + verify injection wires through."""

from __future__ import annotations

import io
from types import SimpleNamespace

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


class _FakeClient:
    def __init__(self, response_text: str):
        self._text = response_text
        self.captured_system: str | None = None

    def complete(self, *, messages, model):
        for m in messages:
            if m.role == "system":
                self.captured_system = m.content
        return SimpleNamespace(text=self._text)


def _seed_session(client) -> tuple[str, str]:
    upload = client.post(
        "/api/admin/docs",
        headers={"X-Auth-Token": "tok"},
        files={
            "file": (
                "d.pdf",
                io.BytesIO(b"%PDF-1.4\n%%EOF\n"),
                "application/pdf",
            )
        },
    )
    slug = upload.json()["slug"]
    cfg = client.app.state.config
    write_mineru(
        cfg.data_root,
        slug,
        {
            "elements": [{"box_id": "p1-b0", "html_snippet": "<p>X</p>"}],
            "diagnostics": [],
        },
    )
    sid = client.post(
        "/api/admin/provenienz/sessions",
        headers={"X-Auth-Token": "tok"},
        json={"slug": slug, "root_chunk_id": "p1-b0"},
    ).json()["session_id"]
    detail = client.get(
        f"/api/admin/provenienz/sessions/{sid}",
        headers={"X-Auth-Token": "tok"},
    ).json()
    chunk_id = next(n["node_id"] for n in detail["nodes"] if n["kind"] == "chunk")
    return sid, chunk_id


def _create_approach(client, name="A", step_kinds=("extract_claims",), text="hi"):
    return client.post(
        "/api/admin/provenienz/approaches",
        headers={"X-Auth-Token": "tok"},
        json={
            "name": name,
            "step_kinds": list(step_kinds),
            "extra_system": text,
        },
    ).json()["approach"]


def test_pin_appends_to_meta_idempotent(client):
    sid, _ = _seed_session(client)
    a = _create_approach(client, name="A")
    r1 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    assert r1.status_code == 200
    assert a["approach_id"] in r1.json()["meta"]["pinned_approach_ids"]
    # second pin = no-op
    r2 = client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    assert r2.json()["meta"]["pinned_approach_ids"].count(a["approach_id"]) == 1


def test_unpin_removes_from_meta(client):
    sid, _ = _seed_session(client)
    a = _create_approach(client, name="A")
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/unpin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    assert r.status_code == 200
    assert r.json()["meta"]["pinned_approach_ids"] == []


def test_pinned_approach_injects_into_prompt(client, monkeypatch):
    sid, chunk_id = _seed_session(client)
    a = _create_approach(
        client,
        name="thorough",
        step_kinds=["extract_claims"],
        text="Sei besonders gründlich bei Zahlen.",
    )
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    fake = _FakeClient('["Aussage 1"]')
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert r.status_code == 201
    assert "Sei besonders gründlich bei Zahlen." in fake.captured_system
    refs = r.json()["payload"]["guidance_consulted"]
    assert any(g["kind"] == "approach" and g["id"] == a["approach_id"] for g in refs)


def test_pinned_approach_with_non_matching_step_kind_is_skipped(client, monkeypatch):
    sid, chunk_id = _seed_session(client)
    a = _create_approach(
        client,
        name="eval-only",
        step_kinds=["evaluate"],
        text="should NOT appear in extract prompt",
    )
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    fake = _FakeClient('["X"]')
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert r.status_code == 201
    assert "should NOT appear" not in (fake.captured_system or "")
    refs = r.json()["payload"]["guidance_consulted"]
    assert all(g["id"] != a["approach_id"] for g in refs)


def test_disabled_pinned_approach_is_skipped(client, monkeypatch):
    sid, chunk_id = _seed_session(client)
    a = _create_approach(
        client,
        name="off",
        step_kinds=["extract_claims"],
        text="DISABLED text",
    )
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a["approach_id"]},
    )
    # Disable
    client.patch(
        f"/api/admin/provenienz/approaches/{a['approach_id']}",
        headers={"X-Auth-Token": "tok"},
        json={"enabled": False},
    )
    fake = _FakeClient('["X"]')
    monkeypatch.setattr(router_mod, "get_llm_client", lambda: fake)
    monkeypatch.setattr(router_mod, "get_default_model", lambda: "test-model")
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/extract-claims",
        headers={"X-Auth-Token": "tok"},
        json={"chunk_node_id": chunk_id},
    )
    assert r.status_code == 201
    assert "DISABLED text" not in (fake.captured_system or "")
