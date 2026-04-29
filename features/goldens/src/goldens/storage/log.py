"""Event log: append + read with cross-process locking and idempotency.

The log is a JSONL file. Each line is one Event serialized via
Event.to_dict(). Append is exclusive-locked (fcntl.LOCK_EX) and
fsync'd. Idempotency on event_id: re-appending the same id is a no-op.

Reading is tolerant: malformed lines are skipped with a WARNING log,
not raised. A missing file returns [].
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from typing import TYPE_CHECKING

from goldens.schemas.base import Event

if TYPE_CHECKING:
    from pathlib import Path

_log = logging.getLogger(__name__)


def append_event(path: Path, event: Event) -> None:
    """Append `event` to the JSONL log at `path`.

    Concurrency-safe across processes (fcntl.LOCK_EX). Idempotent on
    `event.event_id` — re-appending an existing id is a no-op.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # "a+" so we can read existing content under the lock to check
    # idempotency. Opening with "w" or "r+" risks truncation.
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            if _event_id_already_present(path, event.event_id):
                return
            line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_events(path: Path) -> list[Event]:
    """Read all events from `path`. Tolerates malformed lines by
    skipping them with a warning. Returns [] if the file does not
    exist.
    """
    if not path.exists():
        return []
    out: list[Event] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                out.append(Event.from_dict(d))
            except (ValueError, KeyError) as e:
                _log.warning(
                    "skipping malformed event log line %d in %s: %s",
                    lineno,
                    path,
                    e,
                )
                continue
    return out


def _event_id_already_present(path: Path, event_id: str) -> bool:
    """Linear scan over the JSONL to check if event_id is recorded.
    Caller must hold the lock on `path`."""
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                # Malformed line — ignore for this check; read_events
                # will warn separately.
                continue
            if d.get("event_id") == event_id:
                return True
    return False
