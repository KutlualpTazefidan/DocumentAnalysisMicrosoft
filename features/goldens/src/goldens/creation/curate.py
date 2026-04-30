"""Interactive curate CLI + decision-bearing helpers.

The outer cmd_curate() loop body is `# pragma: no cover` because the
ergonomic UX wraps print()/input() calls; every branch with logic
worth testing is extracted into a helper that has its own unit test."""

from __future__ import annotations

import re

_WS_RE = re.compile(r"\s+")


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
