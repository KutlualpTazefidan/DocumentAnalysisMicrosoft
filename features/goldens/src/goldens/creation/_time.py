"""Internal time helper used by the creation layer (mirror of
goldens.operations._time so creation does not import a sibling layer's
private module)."""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc_iso() -> str:
    """Current UTC time formatted as 'YYYY-MM-DDTHH:MM:SSZ'.

    Tests that need deterministic timestamps should monkeypatch this
    function in the importing module."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
