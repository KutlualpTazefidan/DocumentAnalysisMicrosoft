"""Interactive curate CLI + decision-bearing helpers.

The outer cmd_curate() loop body is `# pragma: no cover` because the
ergonomic UX wraps print()/input() calls; every branch with logic
worth testing is extracted into a helper that has its own unit test."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from goldens.creation.elements.adapter import DocumentElement

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
