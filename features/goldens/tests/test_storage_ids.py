"""Tests for goldens.storage.ids."""

from __future__ import annotations

import re

from goldens.storage.ids import new_entry_id, new_event_id

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def test_event_id_is_uuid4_hex():
    eid = new_event_id()
    assert _HEX32.match(eid)


def test_entry_id_is_uuid4_hex():
    rid = new_entry_id()
    assert _HEX32.match(rid)


def test_event_ids_are_unique_across_many_calls():
    """Probabilistic — UUID4 collision odds are vanishingly small.
    1k calls is more than enough to catch a broken implementation."""
    ids = {new_event_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_entry_ids_are_unique_across_many_calls():
    ids = {new_entry_id() for _ in range(1000)}
    assert len(ids) == 1000
