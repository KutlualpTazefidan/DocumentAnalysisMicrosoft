"""Tests for goldens.creation._toml.dump_toml — happy-path only (D14)."""

from __future__ import annotations

import tomllib

import pytest
from goldens.creation._toml import dump_toml


def test_round_trip_scalar_keys() -> None:
    src = {"schema_version": 1, "pseudonym": "alice", "level": "masters"}
    text = dump_toml(src)
    assert tomllib.loads(text) == src


def test_round_trip_nested_table() -> None:
    src = {
        "schema_version": 1,
        "positions": {"doc-a": "p1-aaaaaaaa", "doc-b-2001": "p47-bbbbbbbb"},
    }
    text = dump_toml(src)
    assert tomllib.loads(text) == src


def test_quoted_string_keys_for_hyphenated_slugs() -> None:
    src = {"positions": {"doc-with-hyphens": "p1-deadbeef"}}
    text = dump_toml(src)
    assert '"doc-with-hyphens"' in text
    assert tomllib.loads(text) == src


def test_unsupported_value_type_raises() -> None:
    with pytest.raises(TypeError, match="unsupported"):
        dump_toml({"key": 1.5})


def test_unsupported_nested_shape_raises() -> None:
    with pytest.raises(TypeError, match="unsupported"):
        dump_toml({"positions": {"doc-a": ["list", "not", "ok"]}})


def test_bool_rejected_as_scalar() -> None:
    with pytest.raises(TypeError, match="bool"):
        dump_toml({"flag": True})


def test_two_nested_tables_rejected() -> None:
    with pytest.raises(TypeError, match="one nested table"):
        dump_toml({"a": {"x": "y"}, "b": {"x": "y"}})
