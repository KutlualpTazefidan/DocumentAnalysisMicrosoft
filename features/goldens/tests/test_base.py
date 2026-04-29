"""Tests for goldens.schemas.base — full coverage of dataclasses,
validators, and serialization round-trips."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from goldens.schemas.base import (
    Event,
    HumanActor,
    LLMActor,
    Review,
    SourceElement,
    actor_from_dict,
)

# --- HumanActor ---------------------------------------------------


def test_human_actor_defaults_kind():
    a = HumanActor(pseudonym="alice", level="phd")
    assert a.kind == "human"


def test_human_actor_is_frozen():
    a = HumanActor(pseudonym="alice", level="phd")
    with pytest.raises(FrozenInstanceError):
        a.pseudonym = "bob"  # type: ignore[misc]


def test_human_actor_rejects_empty_pseudonym():
    with pytest.raises(ValueError, match="pseudonym"):
        HumanActor(pseudonym="", level="phd")


def test_human_actor_round_trip():
    a = HumanActor(pseudonym="alice", level="expert")
    assert HumanActor.from_dict(a.to_dict()) == a


def test_human_actor_from_dict_defaults_kind():
    a = HumanActor.from_dict({"pseudonym": "alice", "level": "phd"})
    assert a.kind == "human"


# --- LLMActor -----------------------------------------------------


def test_llm_actor_defaults_kind():
    a = LLMActor(
        model="gpt-4o",
        model_version="2024-08-06",
        prompt_template_version="v1",
        temperature=0.0,
    )
    assert a.kind == "llm"


def test_llm_actor_rejects_empty_model():
    with pytest.raises(ValueError, match="model must be"):
        LLMActor(
            model="",
            model_version="v1",
            prompt_template_version="v1",
            temperature=0.0,
        )


def test_llm_actor_rejects_empty_model_version():
    with pytest.raises(ValueError, match="model_version"):
        LLMActor(
            model="gpt-4o",
            model_version="",
            prompt_template_version="v1",
            temperature=0.0,
        )


def test_llm_actor_rejects_empty_prompt_template_version():
    with pytest.raises(ValueError, match="prompt_template_version"):
        LLMActor(
            model="gpt-4o",
            model_version="v1",
            prompt_template_version="",
            temperature=0.0,
        )


def test_llm_actor_round_trip():
    a = LLMActor(
        model="gpt-4o",
        model_version="2024-08-06",
        prompt_template_version="synth-v1",
        temperature=0.3,
    )
    assert LLMActor.from_dict(a.to_dict()) == a


# --- actor_from_dict ---------------------------------------------


def test_actor_from_dict_dispatches_human():
    d = {"kind": "human", "pseudonym": "alice", "level": "phd"}
    a = actor_from_dict(d)
    assert isinstance(a, HumanActor)


def test_actor_from_dict_dispatches_llm():
    d = {
        "kind": "llm",
        "model": "gpt-4o",
        "model_version": "2024-08-06",
        "prompt_template_version": "v1",
        "temperature": 0.0,
    }
    a = actor_from_dict(d)
    assert isinstance(a, LLMActor)


def test_actor_from_dict_rejects_unknown_kind():
    with pytest.raises(ValueError, match="unknown actor kind"):
        actor_from_dict({"kind": "alien"})


# --- Review -------------------------------------------------------


def test_review_round_trip_with_human_actor():
    r = Review(
        timestamp_utc="2026-04-28T10:00:00Z",
        action="approved",
        actor=HumanActor(pseudonym="alice", level="expert"),
        notes="LGTM",
    )
    restored = Review.from_dict(r.to_dict())
    assert restored == r
    assert isinstance(restored.actor, HumanActor)


def test_review_round_trip_with_llm_actor():
    r = Review(
        timestamp_utc="2026-04-28T10:00:00Z",
        action="synthesised",
        actor=LLMActor(
            model="gpt-4o",
            model_version="2024-08-06",
            prompt_template_version="synth-v1",
            temperature=0.0,
        ),
        notes=None,
    )
    restored = Review.from_dict(r.to_dict())
    assert restored == r
    assert isinstance(restored.actor, LLMActor)


def test_review_rejects_unknown_action():
    with pytest.raises(ValueError, match="unknown review action"):
        Review(
            timestamp_utc="2026-04-28T10:00:00Z",
            action="weird",  # type: ignore[arg-type]
            actor=HumanActor(pseudonym="alice", level="phd"),
            notes=None,
        )


def test_review_rejects_bad_timestamp():
    with pytest.raises(ValueError, match="not ISO-8601"):
        Review(
            timestamp_utc="yesterday",
            action="approved",
            actor=HumanActor(pseudonym="alice", level="phd"),
            notes=None,
        )


def test_review_rejects_empty_timestamp():
    with pytest.raises(ValueError, match="timestamp_utc must be non-empty"):
        Review(
            timestamp_utc="",
            action="approved",
            actor=HumanActor(pseudonym="alice", level="phd"),
            notes=None,
        )


def test_review_notes_default_none():
    r = Review(
        timestamp_utc="2026-04-28T10:00:00Z",
        action="approved",
        actor=HumanActor(pseudonym="alice", level="phd"),
    )
    assert r.notes is None


# --- Event --------------------------------------------------------


def test_event_round_trip_minimal():
    e = Event(
        event_id="e1",
        timestamp_utc="2026-04-28T10:00:00Z",
        event_type="created",
        entry_id="r1",
        schema_version=1,
    )
    restored = Event.from_dict(e.to_dict())
    assert restored == e


def test_event_round_trip_with_payload():
    e = Event(
        event_id="e2",
        timestamp_utc="2026-04-28T10:00:00Z",
        event_type="reviewed",
        entry_id="r1",
        schema_version=1,
        payload={"action": "approved", "actor_pseudonym": "alice"},
    )
    restored = Event.from_dict(e.to_dict())
    assert restored == e
    assert restored.payload["actor_pseudonym"] == "alice"


def test_event_payload_defaults_empty():
    e = Event(
        event_id="e3",
        timestamp_utc="2026-04-28T10:00:00Z",
        event_type="deprecated",
        entry_id="r1",
        schema_version=1,
    )
    assert e.payload == {}


def test_event_rejects_empty_event_id():
    with pytest.raises(ValueError, match="event_id"):
        Event(
            event_id="",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="created",
            entry_id="r1",
            schema_version=1,
        )


def test_event_rejects_empty_entry_id():
    with pytest.raises(ValueError, match="entry_id"):
        Event(
            event_id="e1",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="created",
            entry_id="",
            schema_version=1,
        )


def test_event_rejects_schema_version_zero():
    with pytest.raises(ValueError, match="schema_version"):
        Event(
            event_id="e1",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="created",
            entry_id="r1",
            schema_version=0,
        )


def test_event_rejects_unknown_event_type():
    with pytest.raises(ValueError, match="unknown event_type"):
        Event(
            event_id="e1",
            timestamp_utc="2026-04-28T10:00:00Z",
            event_type="archived",  # type: ignore[arg-type]
            entry_id="r1",
            schema_version=1,
        )


def test_event_from_dict_ignores_unknown_keys():
    d = {
        "event_id": "e1",
        "timestamp_utc": "2026-04-28T10:00:00Z",
        "event_type": "created",
        "entry_id": "r1",
        "schema_version": 1,
        "payload": {},
        "future_field": "ignored silently",
    }
    e = Event.from_dict(d)
    assert e.event_id == "e1"


# --- SourceElement -----------------------------------------------


def test_source_element_holds_all_fields():
    el = SourceElement(
        document_id="tragkorb-b-147-2001-rev-1",
        page_number=47,
        element_id="p4",
        element_type="paragraph",
    )
    assert el.document_id == "tragkorb-b-147-2001-rev-1"
    assert el.page_number == 47
    assert el.element_id == "p4"
    assert el.element_type == "paragraph"


def test_source_element_is_frozen():
    el = SourceElement(document_id="d1", page_number=1, element_id="p1", element_type="paragraph")
    with pytest.raises(FrozenInstanceError):
        el.page_number = 2  # type: ignore[misc]


def test_source_element_rejects_empty_document_id():
    with pytest.raises(ValueError, match="document_id"):
        SourceElement(document_id="", page_number=1, element_id="p1", element_type="paragraph")


def test_source_element_rejects_empty_element_id():
    with pytest.raises(ValueError, match="element_id"):
        SourceElement(document_id="d1", page_number=1, element_id="", element_type="paragraph")


def test_source_element_rejects_zero_page_number():
    with pytest.raises(ValueError, match="page_number"):
        SourceElement(document_id="d1", page_number=0, element_id="p1", element_type="paragraph")


def test_source_element_rejects_negative_page_number():
    with pytest.raises(ValueError, match="page_number"):
        SourceElement(document_id="d1", page_number=-1, element_id="p1", element_type="paragraph")


def test_source_element_rejects_unknown_element_type():
    with pytest.raises(ValueError, match="unknown element_type"):
        SourceElement(
            document_id="d1",
            page_number=1,
            element_id="x1",
            element_type="banana",  # type: ignore[arg-type]
        )


def test_source_element_accepts_all_documented_types():
    for kind in ("paragraph", "heading", "table", "figure", "list_item"):
        el = SourceElement(
            document_id="d1",
            page_number=1,
            element_id=f"x-{kind}",
            element_type=kind,  # type: ignore[arg-type]
        )
        assert el.element_type == kind


def test_source_element_round_trip():
    original = SourceElement(
        document_id="tragkorb-b-147-2001-rev-1",
        page_number=47,
        element_id="t1",
        element_type="table",
    )
    restored = SourceElement.from_dict(original.to_dict())
    assert restored == original
