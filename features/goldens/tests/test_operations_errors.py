"""Tests for goldens.operations.errors — exception hierarchy."""

from __future__ import annotations

from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError


def test_entry_not_found_is_lookup_error():
    """LookupError base lets a future FastAPI handler map to 404."""
    assert issubclass(EntryNotFoundError, LookupError)


def test_entry_deprecated_is_value_error():
    """ValueError base lets a future FastAPI handler map to 409."""
    assert issubclass(EntryDeprecatedError, ValueError)


def test_entry_not_found_message_carries_entry_id():
    err = EntryNotFoundError("r-missing")
    assert "r-missing" in str(err)


def test_entry_deprecated_message_carries_entry_id():
    err = EntryDeprecatedError("r-already-dep")
    assert "r-already-dep" in str(err)
