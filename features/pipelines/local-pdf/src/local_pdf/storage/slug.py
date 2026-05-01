"""Deterministic slug derivation from a filename.

Slug rules:
- Lowercased, ASCII-only (Unicode NFKD-decomposed, non-ASCII stripped)
- Underscores and spaces become hyphens
- Trailing `.pdf` extension dropped
- On collision against an existing directory, append `-2`, `-3`, ...
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def slugify_filename(filename: str) -> str:
    """Return a slug suitable for `data/raw-pdfs/<slug>/`."""
    stem = filename
    if stem.lower().endswith(".pdf"):
        stem = stem[:-4]
    decomposed = unicodedata.normalize("NFKD", stem)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    hyphenated = re.sub(r"[\s_]+", "-", lowered)
    cleaned = re.sub(r"[^a-z0-9-]", "", hyphenated)
    collapsed = re.sub(r"-+", "-", cleaned).strip("-")
    return collapsed or "untitled"


def unique_slug(parent_dir: Path, filename: str) -> str:
    """Return a slug guaranteed not to collide with an existing subdir of parent_dir."""
    base = slugify_filename(filename)
    if not (parent_dir / base).exists():
        return base
    n = 2
    while (parent_dir / f"{base}-{n}").exists():
        n += 1
    return f"{base}-{n}"
