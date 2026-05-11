"""Tests for the Phase-2 auto-selection layer in approaches.py.

Covers the matcher, aggregate selector, storage backwards-compat, and
the _gather_guidance integration path.
"""

from __future__ import annotations

import io
import json

import pytest
from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.approaches import (
    Approach,
    auto_match_approach,
    auto_select_approaches,
    upsert_approach,
)
from local_pdf.storage.sidecar import write_mineru

# ── auto_match_approach: rule matrix ───────────────────────────────────


def test_empty_criteria_never_matches():
    ok, reasons = auto_match_approach({}, anchor_kind="chunk", anchor_text="x", goal="y")
    assert ok is False
    assert reasons == []


def test_anchor_kind_match():
    ok, reasons = auto_match_approach(
        {"anchor_kinds": ["chunk", "claim"]},
        anchor_kind="chunk",
        anchor_text="",
        goal="",
    )
    assert ok is True
    assert any("chunk" in r for r in reasons)


def test_anchor_kind_miss():
    ok, _ = auto_match_approach(
        {"anchor_kinds": ["claim"]},
        anchor_kind="chunk",
        anchor_text="",
        goal="",
    )
    assert ok is False


def test_goal_keyword_any_match():
    ok, reasons = auto_match_approach(
        {"goal_contains": ["Beleg", "prüfen"]},
        anchor_kind="chunk",
        anchor_text="",
        goal="Wo steht der Beleg dafür?",
    )
    assert ok is True
    assert any("Beleg" in r for r in reasons)


def test_goal_keyword_case_insensitive():
    ok, _ = auto_match_approach(
        {"goal_contains": ["beleg"]},
        anchor_kind="chunk",
        anchor_text="",
        goal="Wo steht der BELEG?",
    )
    assert ok is True


def test_text_keyword_match():
    ok, reasons = auto_match_approach(
        {"text_contains": ["kW", "MW"]},
        anchor_kind="chunk",
        anchor_text="Die Wärmeleistung beträgt 5.6 kW.",
        goal="",
    )
    assert ok is True
    assert any("kW" in r for r in reasons)


def test_and_logic_across_keys():
    """All present keys must match — anchor_kinds passes but
    goal_contains fails → no match."""
    ok, _ = auto_match_approach(
        {"anchor_kinds": ["chunk"], "goal_contains": ["Beleg"]},
        anchor_kind="chunk",
        anchor_text="",
        goal="ein anderer Text",
    )
    assert ok is False


def test_and_logic_all_keys_match():
    ok, reasons = auto_match_approach(
        {"anchor_kinds": ["chunk"], "goal_contains": ["Beleg"]},
        anchor_kind="chunk",
        anchor_text="",
        goal="finde den Beleg",
    )
    assert ok is True
    # Both reasons should be in the list.
    assert any("chunk" in r for r in reasons)
    assert any("Beleg" in r for r in reasons)


def test_empty_lists_count_as_unset():
    """Criteria with only empty lists should be treated as 'no auto-trigger
    configured', not as a wildcard match."""
    ok, _ = auto_match_approach(
        {"anchor_kinds": []},
        anchor_kind="chunk",
        anchor_text="",
        goal="",
    )
    assert ok is False


# ── auto_select_approaches: aggregate ──────────────────────────────────


def test_aggregate_filters_to_matching_only():
    approaches = [
        Approach(
            approach_id="a",
            name="match",
            version=1,
            step_kinds=["next_step"],
            selection_criteria={"anchor_kinds": ["chunk"]},
        ),
        Approach(
            approach_id="b",
            name="no-match",
            version=1,
            step_kinds=["next_step"],
            selection_criteria={"anchor_kinds": ["claim"]},
        ),
        Approach(
            approach_id="c",
            name="no-criteria",
            version=1,
            step_kinds=["next_step"],
            selection_criteria={},
        ),
    ]
    out = auto_select_approaches(approaches, anchor_kind="chunk", anchor_text="", goal="")
    assert [a.approach_id for a, _ in out] == ["a"]


# ── Storage round-trip + backwards-compat ──────────────────────────────


def test_upsert_roundtrips_selection_criteria(tmp_path):
    a = upsert_approach(
        tmp_path,
        name="x",
        step_kinds=["next_step"],
        extra_system="...",
        selection_criteria={"anchor_kinds": ["chunk"], "goal_contains": ["foo"]},
    )
    assert a.selection_criteria == {
        "anchor_kinds": ["chunk"],
        "goal_contains": ["foo"],
    }
    # On disk: full record persisted to the unified skill store.
    raw_lines = (tmp_path / "skills" / "skills.jsonl").read_text().splitlines()
    rec = json.loads(raw_lines[-1])
    assert rec["conditions"]["anchor_kinds"] == ["chunk"]


def test_skill_without_conditions_renders_as_empty_selection_criteria(tmp_path):
    """A Skill record with no conditions must render back as an Approach
    with an empty selection_criteria dict. (Previously this test seeded
    a legacy approaches.jsonl row without the Phase-2 selection_criteria
    field; now that read_approaches reads from skills.jsonl, the
    equivalent seed is a Skill with default-empty TriggerConditions.)"""
    from local_pdf.provenienz.approaches import read_approaches
    from local_pdf.provenienz.skills import (
        Skill,
        SkillKind,
        SkillPrompt,
        append_skill_event,
    )

    append_skill_event(
        tmp_path,
        Skill(
            skill_id="legacy-id",
            name="legacy",
            version=1,
            enabled=True,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            skill_kind=SkillKind.PROMPT_OVERLAY,
            fires_on=["next_step"],
            prompt=SkillPrompt(free_text="old"),
        ),
    )

    items = read_approaches(tmp_path, enabled_only=False)
    assert len(items) == 1
    assert items[0].selection_criteria == {}


def test_upsert_inherits_criteria_from_previous_version(tmp_path):
    """Patch with no criteria override must keep the old criteria."""
    upsert_approach(
        tmp_path,
        name="x",
        step_kinds=["next_step"],
        extra_system="v1",
        selection_criteria={"anchor_kinds": ["chunk"]},
    )
    bumped = upsert_approach(
        tmp_path,
        name="x",
        step_kinds=["next_step"],
        extra_system="v2",
        # Note: NO selection_criteria arg — should inherit.
    )
    assert bumped.version == 2
    assert bumped.selection_criteria == {"anchor_kinds": ["chunk"]}


# ── End-to-end: /next-step/stream gather_guidance phase ────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("GOLDENS_API_TOKEN", "tok")
    monkeypatch.setenv("LOCAL_PDF_DATA_ROOT", str(root))
    monkeypatch.setattr(
        router_mod,
        "_llm_next_step",
        lambda *a, **k: {
            "kind": "executable_step",
            "name": "extract_claims",
            "description": "",
            "reasoning": "test",
            "considered_alternatives": [],
            "confidence": 0.9,
            "tool": None,
            "approach_id": None,
        },
    )
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


def test_next_step_auto_pins_matching_approach(client):
    """An approach with selection_criteria matching the anchor + goal
    should appear in gather_guidance.payload.active_guidance even when
    not pinned to the session."""
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="auto-chunk",
        step_kinds=["next_step"],
        extra_system="Spezial-Heuristik für Chunks",
        selection_criteria={"anchor_kinds": ["chunk"]},
    )
    sid, chunk_id = _bootstrap(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    events = _parse_sse(r.text)
    gather = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "gather_guidance" and e[1]["status"] == "completed"
    )
    refs = gather["payload"]["active_guidance"]
    auto_refs = [g for g in refs if g.get("kind") == "approach" and g.get("auto_selected")]
    assert len(auto_refs) == 1
    assert auto_refs[0]["summary"] == "auto-chunk"
    assert any("chunk" in r for r in auto_refs[0]["selection_reasons"])


def test_next_step_skips_approach_when_criteria_dont_match(client):
    cfg = client.app.state.config
    upsert_approach(
        cfg.data_root,
        name="claim-only",
        step_kinds=["next_step"],
        extra_system="...",
        selection_criteria={"anchor_kinds": ["claim"]},  # not chunk
    )
    sid, chunk_id = _bootstrap(client)
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    events = _parse_sse(r.text)
    gather = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "gather_guidance" and e[1]["status"] == "completed"
    )
    auto_refs = [
        g
        for g in gather["payload"]["active_guidance"]
        if g.get("kind") == "approach" and g.get("auto_selected")
    ]
    assert auto_refs == []


def test_pinned_approach_takes_precedence_over_auto(client):
    """If the same approach matches AND is pinned, it appears once with
    auto_selected=False (pinned wins)."""
    cfg = client.app.state.config
    a = upsert_approach(
        cfg.data_root,
        name="dual",
        step_kinds=["next_step"],
        extra_system="...",
        selection_criteria={"anchor_kinds": ["chunk"]},
    )
    sid, chunk_id = _bootstrap(client)
    # Pin the approach to the session.
    client.post(
        f"/api/admin/provenienz/sessions/{sid}/pin-approach",
        headers={"X-Auth-Token": "tok"},
        json={"approach_id": a.approach_id},
    )
    r = client.post(
        f"/api/admin/provenienz/sessions/{sid}/next-step/stream",
        headers={"X-Auth-Token": "tok"},
        json={"anchor_node_id": chunk_id},
    )
    events = _parse_sse(r.text)
    gather = next(
        e[1]
        for e in events
        if e[0] == "phase" and e[1]["phase"] == "gather_guidance" and e[1]["status"] == "completed"
    )
    refs_for_approach = [
        g
        for g in gather["payload"]["active_guidance"]
        if g.get("kind") == "approach" and g.get("id") == a.approach_id
    ]
    assert len(refs_for_approach) == 1
    assert refs_for_approach[0]["auto_selected"] is False


def test_patch_endpoint_persists_selection_criteria(client):
    cfg = client.app.state.config
    a = upsert_approach(
        cfg.data_root,
        name="patchable",
        step_kinds=["next_step"],
        extra_system="...",
    )
    r = client.patch(
        f"/api/admin/provenienz/approaches/{a.approach_id}",
        headers={"X-Auth-Token": "tok"},
        json={"selection_criteria": {"anchor_kinds": ["chunk"], "goal_contains": ["x"]}},
    )
    assert r.status_code == 200, r.text
    body = r.json()["approach"]
    assert body["selection_criteria"]["anchor_kinds"] == ["chunk"]
    assert body["selection_criteria"]["goal_contains"] == ["x"]
