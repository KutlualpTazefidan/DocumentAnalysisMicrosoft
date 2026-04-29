"""Internal time helper used by the operations layer."""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc_iso() -> str:
    """Current UTC time formatted as 'YYYY-MM-DDTHH:MM:SSZ'.

    Matches the parent spec's ISO-8601-with-Z naming convention. Tests
    that need deterministic timestamps should monkeypatch this function
    in the module that imports it (each operation imports it once)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
