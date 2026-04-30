"""Interactive curate CLI + decision-bearing helpers.

The outer cmd_curate() loop body is `# pragma: no cover` because the
ergonomic UX wraps print()/input() calls; every branch with logic
worth testing is extracted into a helper that has its own unit test."""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

from goldens.creation._time import now_utc_iso
from goldens.creation.identity import identity_to_human_actor
from goldens.schemas import Event
from goldens.storage import new_entry_id, new_event_id

if TYPE_CHECKING:
    from pathlib import Path

    from goldens.creation.elements.adapter import DocumentElement
    from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
    from goldens.creation.identity import Identity

_WS_RE = re.compile(r"\s+")


class SlugResolutionError(Exception):
    """Raised when --doc cannot be auto-resolved (zero or multiple candidates)."""


def resolve_slug(explicit: str | None, *, outputs_root: Path) -> str:
    if explicit is not None:
        return explicit
    if not outputs_root.is_dir():
        raise SlugResolutionError(
            f"no candidate documents under {outputs_root} (directory does not exist)"
        )
    candidates: list[str] = []
    for child in sorted(outputs_root.iterdir()):
        if not child.is_dir():
            continue
        analyze_dir = child / "analyze"
        if analyze_dir.is_dir() and any(analyze_dir.glob("*.json")):
            candidates.append(child.name)
    if not candidates:
        raise SlugResolutionError(f"no candidate documents under {outputs_root}")
    if len(candidates) > 1:
        listed = ", ".join(candidates)
        raise SlugResolutionError(
            f"multiple candidate documents under {outputs_root} ({listed}); "
            "pass --doc <slug> to disambiguate"
        )
    return candidates[0]


class StartResolutionError(Exception):
    """Raised when --start-from matches no element."""


def resolve_start_position(
    elements: list[DocumentElement],
    *,
    explicit: str | None,
    cached: str | None,
) -> int:
    if explicit is not None:
        for i, el in enumerate(elements):
            if el.element_id == explicit:
                return i
        for i, el in enumerate(elements):
            if el.element_id.startswith(explicit):
                return i
        raise StartResolutionError(f"--start-from {explicit!r} matches nothing in this document")
    if cached is not None:
        for i, el in enumerate(elements):
            if el.element_id == cached:
                return i
    return 0


def _normalise(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().lower()


def query_substring_overlap(query: str, source: str, *, threshold: int) -> bool:
    """True iff some contiguous substring of `query` of length >= `threshold`
    appears in `source`. Both strings are lowercased and whitespace-collapsed
    before comparison so trivial reformatting cannot bypass the check."""
    if threshold <= 0:
        return True
    q = _normalise(query)
    s = _normalise(source)
    if len(q) < threshold:
        return False
    return any(q[start : start + threshold] in s for start in range(0, len(q) - threshold + 1))


def build_created_event(
    *,
    question: str,
    element: DocumentElement,
    loader: AnalyzeJsonLoader,
    identity: Identity,
) -> Event:
    """Assemble a `created` Event from one curator-typed question.

    `expected_chunk_ids` is intentionally empty (D13); `source_element`
    is the ground truth and the chunk-id translation lives in a
    dedicated match-type classifier (next phase)."""
    source_element = loader.to_source_element(element)
    payload = {
        "task_type": "retrieval",
        "actor": identity_to_human_actor(identity).to_dict(),
        "action": "created_from_scratch",
        "notes": None,
        "entry_data": {
            "query": question,
            "expected_chunk_ids": [],
            "chunk_hashes": {},
            "source_element": source_element.to_dict(),
        },
    }
    return Event(
        event_id=new_event_id(),
        timestamp_utc=now_utc_iso(),
        event_type="created",
        entry_id=new_entry_id(),
        schema_version=1,
        payload=payload,
    )


def require_interactive_tty() -> None:
    """Hard-exit when stdin or stdout is not a TTY. Verbatim from the legacy
    curate writer (D9). No `--no-tty` opt-out."""
    if not sys.stdin.isatty():
        print("ERROR: curate requires an interactive stdin (TTY)", file=sys.stderr)
        raise SystemExit(2)
    if not sys.stdout.isatty():
        print("ERROR: curate requires an interactive stdout (TTY)", file=sys.stderr)
        raise SystemExit(2)
