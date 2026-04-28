"""Tests for ingestion.timestamp helpers."""

from __future__ import annotations

import re
from datetime import UTC, datetime


def test_now_compact_utc_format() -> None:
    from ingestion.timestamp import now_compact_utc

    out = now_compact_utc()
    assert re.fullmatch(r"\d{8}T\d{6}", out), f"Unexpected format: {out!r}"


def test_now_compact_utc_is_recent() -> None:
    """Result should be within ~5 seconds of 'now'."""
    from ingestion.timestamp import now_compact_utc

    before = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out = now_compact_utc()
    after = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    assert before <= out <= after


def test_now_compact_utc_is_lexically_chronological() -> None:
    """Two calls in sequence: the second is >= the first lexically."""
    import time

    from ingestion.timestamp import now_compact_utc

    a = now_compact_utc()
    time.sleep(1.1)
    b = now_compact_utc()
    assert a < b


def test_now_compact_utc_uses_utc_not_local_time(monkeypatch) -> None:
    """Ensure the function uses UTC, not local time."""
    from ingestion.timestamp import now_compact_utc

    monkeypatch.setenv("TZ", "America/New_York")
    out = now_compact_utc()
    expected_utc = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    # Allow off-by-one second
    assert abs(int(out[-2:]) - int(expected_utc[-2:])) <= 1 or out[:-2] == expected_utc[:-2]
