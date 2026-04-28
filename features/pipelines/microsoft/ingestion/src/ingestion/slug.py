"""Filename → URL-safe slug.

Used to derive per-document folder names under outputs/. Deterministic,
no external dependencies.
"""

from __future__ import annotations

import re

_TRIM_EXTENSION = re.compile(r"\.pdf$", re.IGNORECASE)
_NON_ALNUM_OR_HYPHEN = re.compile(r"[^a-z0-9-]+")
_RUN_OF_HYPHENS = re.compile(r"-+")


def slug_from_filename(filename: str) -> str:
    """Convert a filename to a URL-safe slug.

    Steps:
        1. Strip a trailing `.pdf` extension (case-insensitive).
        2. Lowercase.
        3. Replace any non-(letter|digit|hyphen) run with a single hyphen.
        4. Collapse runs of hyphens into one.
        5. Trim leading and trailing hyphens.

    Examples:
        'GNB B 147_2001 Rev. 1.pdf' -> 'gnb-b-147-2001-rev-1'
        'IAEA TS-G-1.1.pdf'         -> 'iaea-ts-g-1-1'
    """
    base = _TRIM_EXTENSION.sub("", filename)
    lowered = base.lower()
    replaced = _NON_ALNUM_OR_HYPHEN.sub("-", lowered)
    collapsed = _RUN_OF_HYPHENS.sub("-", replaced)
    return collapsed.strip("-")
