"""Tests for goldens.operations._time."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from goldens.operations._time import now_utc_iso


def test_now_utc_iso_format_is_iso8601_z():
    s = now_utc_iso()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s) is not None, s


def test_now_utc_iso_is_close_to_real_now():
    """The returned string should round-trip to a datetime within ~5s of `now`."""
    s = now_utc_iso()
    parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    diff = abs((datetime.now(UTC) - parsed).total_seconds())
    assert diff < 5
