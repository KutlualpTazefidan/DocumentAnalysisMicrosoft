"""HTTP CRUD for the unified skills library."""

from __future__ import annotations

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    from fastapi.testclient import TestClient
    from local_pdf.api.app import create_app

    return TestClient(create_app())


def _enrichment_body(name: str = "myenrichment") -> dict:
    return {
        "name": name,
        "skill_kind": "enrichment",
        "fires_on": ["extract_claims"],
        "prompt": {
            "free_text": "",
            "questions": ["What is the unit?"],
            "domain_rules": "",
        },
        "output": {
            "annotation_kind": "claim_background",
            "attaches_to": "claim",
            "consumed_by": ["formulate_task"],
        },
    }


def _overlay_body(name: str = "thorough") -> dict:
    return {
        "name": name,
        "skill_kind": "prompt-overlay",
        "fires_on": ["extract_claims"],
        "prompt": {
            "free_text": "Sei gründlich.",
            "questions": [],
            "domain_rules": "",
        },
    }


def test_list_skills_empty_returns_only_seeded_default(client):
    r = client.get(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "claim_background"
    assert data[0]["skill_kind"] == "enrichment"


def test_create_skill_via_post_writes_to_jsonl(client):
    r = client.post(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
        json=_overlay_body(name="thorough"),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "thorough"
    assert body["version"] == 1
    assert body["enabled"] is True
    assert body["skill_kind"] == "prompt-overlay"
    assert body.get("skill_id")
    assert body["created_at"] != ""

    # GET shows it
    r2 = client.get(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
    )
    assert r2.status_code == 200
    names = [s["name"] for s in r2.json()]
    assert "thorough" in names
    assert "claim_background" in names


def test_patch_skill_bumps_version(client):
    create = client.post(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
        json=_overlay_body(name="patchme"),
    )
    sid = create.json()["skill_id"]

    r = client.patch(
        f"/api/admin/provenienz/skills/{sid}",
        headers={"X-Auth-Token": "tok"},
        json={"description": "now described"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 2
    assert body["description"] == "now described"
    assert body["name"] == "patchme"


def test_delete_skill_tombstones_via_event(client):
    create = client.post(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
        json=_overlay_body(name="deleteme"),
    )
    sid = create.json()["skill_id"]

    r = client.delete(
        f"/api/admin/provenienz/skills/{sid}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 204, r.text

    r2 = client.get(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
    )
    names = [s["name"] for s in r2.json()]
    assert "deleteme" not in names


def test_get_skill_by_id_returns_record(client):
    create = client.post(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
        json=_overlay_body(name="lookup"),
    )
    sid = create.json()["skill_id"]

    r = client.get(
        f"/api/admin/provenienz/skills/{sid}",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skill_id"] == sid
    assert body["name"] == "lookup"


def test_get_skill_by_unknown_id_returns_404(client):
    r = client.get(
        "/api/admin/provenienz/skills/does-not-exist",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 404


def test_create_rejects_enrichment_without_attaches_to(client):
    body = _enrichment_body(name="bad")
    body["output"]["attaches_to"] = ""
    r = client.post(
        "/api/admin/provenienz/skills",
        headers={"X-Auth-Token": "tok"},
        json=body,
    )
    assert r.status_code in (400, 422), r.text


def test_token_required_returns_401(client):
    r = client.get("/api/admin/provenienz/skills")
    assert r.status_code == 401


def test_list_skill_runs_returns_filtered_list(client, monkeypatch, tmp_path):
    """Fire a skill via run_enrichment_skill, verify the runs endpoint
    surfaces it (and excludes runs from a different skill_id)."""
    from local_pdf.provenienz.skill_dispatcher import run_enrichment_skill
    from local_pdf.provenienz.skills import (
        Skill,
        SkillKind,
        SkillOutput,
        SkillPrompt,
    )

    s1 = Skill(
        skill_id="s1",
        name="a",
        version=1,
        skill_kind=SkillKind.ENRICHMENT,
        fires_on=["extract_claims"],
        prompt=SkillPrompt(questions=["?"]),
        output=SkillOutput(annotation_kind="x", attaches_to="claim"),
    )
    s2 = Skill(
        skill_id="s2",
        name="b",
        version=1,
        skill_kind=SkillKind.ENRICHMENT,
        fires_on=["extract_claims"],
        prompt=SkillPrompt(questions=["?"]),
        output=SkillOutput(annotation_kind="x", attaches_to="claim"),
    )

    class _Client:
        def complete(self, *, messages, model, max_tokens=None, **_):
            class C:
                text = '["x"]'

            return C()

    monkeypatch.setattr("local_pdf.provenienz.skill_dispatcher.get_llm_client", lambda: _Client())
    monkeypatch.setattr("local_pdf.provenienz.skill_dispatcher.get_default_model", lambda: "test")
    data_root = client.app.state.config.data_root
    run_enrichment_skill(s1, ["c"], chunk_text="x", data_root=data_root)
    run_enrichment_skill(s2, ["c"], chunk_text="x", data_root=data_root)

    r = client.get(
        "/api/admin/provenienz/skills/s1/runs",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    runs = r.json()
    assert isinstance(runs, list)
    assert len(runs) == 1
    assert runs[0]["skill_id"] == "s1"
    assert runs[0]["success"] is True


def test_list_skill_runs_returns_empty_when_no_log(client):
    """No runs file → endpoint returns []."""
    r = client.get(
        "/api/admin/provenienz/skills/never-fired/runs",
        headers={"X-Auth-Token": "tok"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []
