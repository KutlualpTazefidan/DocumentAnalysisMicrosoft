"""Byte-equivalence regression test for the Pydantic v2 migration.

The canonical fixture `tests/fixtures/canonical_legacy_events.jsonl`
was generated from the *pre-migration* dataclass code. Every line in
it must round-trip through the migrated Pydantic models and
re-serialize to byte-identical output.

If this test fails, either:
1. The schema field-declaration order has drifted from the dataclass
   version (most common cause).
2. A field's default-handling differs (e.g., Pydantic emits 'null'
   where the dataclass code omitted the key).
3. A nested model serializes differently (e.g., enum-like literals).

In all three cases, the fix is in the schema definitions, NOT the
fixture. Never edit the fixture to make the test pass — that would
silently invalidate every existing event log on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

from goldens.schemas.base import Event

FIXTURE = Path(__file__).parent / "fixtures" / "canonical_legacy_events.jsonl"


def test_canonical_fixture_round_trip_byte_equivalence() -> None:
    """Every line in the canonical fixture round-trips byte-identically."""
    raw = FIXTURE.read_text(encoding="utf-8").splitlines()
    assert len(raw) > 0, "canonical fixture must not be empty"

    for lineno, line in enumerate(raw, start=1):
        event = Event.model_validate_json(line)
        redumped = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        assert redumped == line, (
            f"byte-equivalence drift at line {lineno}\n"
            f"  original:  {line!r}\n"
            f"  redumped:  {redumped!r}"
        )


def test_canonical_fixture_covers_all_event_types() -> None:
    """The fixture must include at least one of each event type, so the
    round-trip test exercises all serialization paths."""
    seen_types: set[str] = set()
    seen_actor_kinds: set[str] = set()

    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        seen_types.add(d["event_type"])
        actor = d["payload"].get("actor")
        if actor:
            seen_actor_kinds.add(actor["kind"])

    assert seen_types == {"created", "reviewed", "deprecated"}, (
        f"fixture missing event types: {{'created','reviewed','deprecated'}} - {seen_types}"
    )
    assert seen_actor_kinds == {"human", "llm"}, (
        f"fixture missing actor kinds: {{'human','llm'}} - {seen_actor_kinds}"
    )
