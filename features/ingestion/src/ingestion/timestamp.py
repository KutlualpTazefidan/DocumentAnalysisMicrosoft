"""Compact UTC ISO-8601 timestamp helpers for filenames.

Format: 'YYYYMMDDTHHMMSS' — sortable as text, equal to chronological order.
No timezone suffix; UTC is implicit by convention.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_compact_utc() -> str:
    """Return the current UTC time as a compact ISO-8601 string.

    Suitable for filenames (no colons, no whitespace, sortable).
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
