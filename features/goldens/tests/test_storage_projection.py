"""Tests for goldens.storage.projection — build_state semantics,
out-of-order tolerance, refinement, orphan-event handling."""

from __future__ import annotations

from goldens.schemas.base import Event, HumanActor, LLMActor
from goldens.storage.projection import active_entries, build_state

# --- helpers ------------------------------------------------------


def _human_actor_dict(level: str = "phd", name: str = "alice") -> dict:
    return {"kind": "human", "pseudonym": name, "level": level}


def _llm_actor_dict() -> dict:
    return {
        "kind": "llm",
        "model": "gpt-4o",
        "model_version": "2024-08-06",
        "prompt_template_version": "v1",
        "temperature": 0.0,
    }


def _created(
    *,
    event_id: str,
    entry_id: str = "r1",
    ts: str = "2026-04-29T10:00:00Z",
    actor: dict | None = None,
    action: str = "created_from_scratch",
    refines: str | None = None,
    query: str = "What is X?",
) -> Event:
    return Event(
        event_id=event_id,
        timestamp_utc=ts,
        event_type="created",
        entry_id=entry_id,
        schema_version=1,
        payload={
            "task_type": "retrieval",
            "actor": actor or _human_actor_dict(),
            "action": action,
            "notes": None,
            "entry_data": {
                "query": query,
                "expected_chunk_ids": ["c1", "c2"],
                "chunk_hashes": {"c1": "sha256:aaa", "c2": "sha256:bbb"},
                "refines": refines,
            },
        },
    )


def _reviewed(
    *,
    event_id: str,
    entry_id: str = "r1",
    ts: str = "2026-04-29T11:00:00Z",
    actor: dict | None = None,
    action: str = "approved",
) -> Event:
    return Event(
        event_id=event_id,
        timestamp_utc=ts,
        event_type="reviewed",
        entry_id=entry_id,
        schema_version=1,
        payload={
            "actor": actor or _human_actor_dict(level="expert", name="bob"),
            "action": action,
            "notes": "LGTM",
        },
    )


def _deprecated(
    *,
    event_id: str,
    entry_id: str = "r1",
    ts: str = "2026-04-29T12:00:00Z",
    actor: dict | None = None,
    reason: str | None = "obsolete",
) -> Event:
    return Event(
        event_id=event_id,
        timestamp_utc=ts,
        event_type="deprecated",
        entry_id=entry_id,
        schema_version=1,
        payload={
            "actor": actor or _human_actor_dict(),
            "reason": reason,
        },
    )


# --- tests --------------------------------------------------------


def test_created_event_yields_retrieval_entry():
    state = build_state([_created(event_id="e1")])
    assert "r1" in state
    entry = state["r1"]
    assert entry.query == "What is X?"
    assert entry.deprecated is False
    assert len(entry.review_chain) == 1
    assert entry.review_chain[0].action == "created_from_scratch"


def test_reviewed_appends_to_chain():
    state = build_state(
        [
            _created(event_id="e1"),
            _reviewed(event_id="e2", action="approved"),
        ]
    )
    chain = state["r1"].review_chain
    assert len(chain) == 2
    assert chain[0].action == "created_from_scratch"
    assert chain[1].action == "approved"
    assert isinstance(chain[1].actor, HumanActor)


def test_reviewed_with_llm_actor():
    state = build_state(
        [
            _created(event_id="e1"),
            _reviewed(event_id="e2", actor=_llm_actor_dict(), action="rejected"),
        ]
    )
    last = state["r1"].review_chain[-1]
    assert isinstance(last.actor, LLMActor)
    assert last.action == "rejected"


def test_deprecated_flips_flag_and_appends_review():
    state = build_state(
        [
            _created(event_id="e1"),
            _deprecated(event_id="e2", reason="bad chunk hashes"),
        ]
    )
    entry = state["r1"]
    assert entry.deprecated is True
    assert entry.review_chain[-1].action == "deprecated"
    assert entry.review_chain[-1].notes == "bad chunk hashes"


def test_orphan_reviewed_event_is_skipped_with_warning(caplog):
    with caplog.at_level("WARNING"):
        state = build_state([_reviewed(event_id="e1", entry_id="ghost")])
    assert state == {}
    assert any("ghost" in rec.message for rec in caplog.records)


def test_orphan_deprecated_event_is_skipped_with_warning(caplog):
    with caplog.at_level("WARNING"):
        state = build_state([_deprecated(event_id="e1", entry_id="ghost")])
    assert state == {}
    assert any("ghost" in rec.message for rec in caplog.records)


def test_out_of_order_events_are_sorted():
    """Reviewed event arrives BEFORE the created event in the input
    iterable. Projection must still apply created first."""
    state = build_state(
        [
            _reviewed(event_id="e2", ts="2026-04-29T11:00:00Z"),
            _created(event_id="e1", ts="2026-04-29T10:00:00Z"),
        ]
    )
    chain = state["r1"].review_chain
    assert [r.action for r in chain] == ["created_from_scratch", "approved"]


def test_refinement_creates_new_entry_and_deprecates_old():
    """Refinement contract: a created event for the new entry with
    `refines: <old>`, plus a deprecate event on the old."""
    state = build_state(
        [
            _created(event_id="e1", entry_id="r-old", ts="2026-04-29T10:00:00Z"),
            _created(
                event_id="e2",
                entry_id="r-new",
                ts="2026-04-29T11:00:00Z",
                refines="r-old",
                query="What is X? (refined)",
            ),
            _deprecated(event_id="e3", entry_id="r-old", ts="2026-04-29T11:00:01Z"),
        ]
    )
    assert state["r-old"].deprecated is True
    assert state["r-new"].deprecated is False
    assert state["r-new"].refines == "r-old"
    assert state["r-new"].query.endswith("(refined)")


def test_active_entries_filters_deprecated():
    state = build_state(
        [
            _created(event_id="e1", entry_id="r1", ts="2026-04-29T10:00:00Z"),
            _created(event_id="e2", entry_id="r2", ts="2026-04-29T10:00:01Z"),
            _deprecated(event_id="e3", entry_id="r1", ts="2026-04-29T10:00:02Z"),
        ]
    )
    actives = list(active_entries(state))
    assert {e.entry_id for e in actives} == {"r2"}


def test_non_retrieval_created_events_are_ignored():
    """Phase B/C entry types are silently skipped by this projection."""
    other = _created(event_id="e1")
    other.payload["task_type"] = "answer_quality"
    state = build_state([other])
    assert state == {}


def test_build_state_handles_empty_iterable():
    assert build_state([]) == {}


# --- iter_active_retrieval_entries (canonical evaluator read path) -----


def test_iter_active_retrieval_entries_returns_only_active_entries(tmp_path):
    """Round-trip: write 1 active + 1 deprecated entry via append_event,
    materialize the iterator, expect just the active entry."""
    from goldens.storage.log import append_event
    from goldens.storage.projection import iter_active_retrieval_entries

    p = tmp_path / "events.jsonl"
    append_event(p, _created(event_id="e1", entry_id="r-active", ts="2026-04-29T10:00:00Z"))
    append_event(p, _created(event_id="e2", entry_id="r-old", ts="2026-04-29T10:00:01Z"))
    append_event(p, _deprecated(event_id="e3", entry_id="r-old", ts="2026-04-29T10:00:02Z"))

    entries = list(iter_active_retrieval_entries(p))
    assert {e.entry_id for e in entries} == {"r-active"}
    assert entries[0].query == "What is X?"


def test_iter_active_retrieval_entries_returns_empty_when_file_missing(tmp_path):
    """Tolerant: missing file → empty iterator (read_events returns [])."""
    from goldens.storage.projection import iter_active_retrieval_entries

    p = tmp_path / "absent.jsonl"
    assert list(iter_active_retrieval_entries(p)) == []


def test_iter_active_retrieval_entries_re_exported_from_goldens_top_level():
    """Catch the most common refactor bug — symbol silently dropped from __init__."""
    from goldens import iter_active_retrieval_entries  # noqa: F401
