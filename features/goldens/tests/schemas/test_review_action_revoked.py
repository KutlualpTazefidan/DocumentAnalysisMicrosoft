from goldens.schemas.base import Event, HumanActor, Review


def test_review_accepts_revoked_action():
    actor = HumanActor(pseudonym="Tester", level="other")
    r = Review(timestamp_utc="2026-06-03T00:00:00Z", action="revoked", actor=actor)
    assert r.action == "revoked"


def test_event_carries_revoked_action_in_payload():
    actor = HumanActor(pseudonym="Tester", level="other")
    ev = Event(
        event_id="ev-1",
        timestamp_utc="2026-06-03T00:00:00Z",
        event_type="reviewed",
        entry_id="q-1",
        schema_version=1,
        payload={"action": "revoked", "actor": actor.model_dump(mode="json"), "notes": None},
    )
    assert ev.payload["action"] == "revoked"
