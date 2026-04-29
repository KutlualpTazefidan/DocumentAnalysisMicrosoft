"""Tests for goldens.creation._time."""

from __future__ import annotations

import re

from goldens.creation._time import now_utc_iso


def test_now_utc_iso_format() -> None:
    value = now_utc_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value), value
