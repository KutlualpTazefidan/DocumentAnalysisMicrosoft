"""Sub-unit decomposition: split a `DocumentElement` into the
testable pieces that the synthetic generator turns into questions.

Per element_type:
    - "paragraph"  → pysbd-split into sentences (German segmentation)
    - "table"      → one sub-unit per data row (header line dropped here;
                     the LLM-loop renderer pairs the header back in)
    - "list_item"  → split on bullet (`-`, `*`, `•`) and numbered
                     (`\\d+\\.`) patterns; whitespace stripped
    - "heading"    → ()  (v1 skips, see spec Q6.2)
    - "figure"     → ()  (v1 skips, see spec Q6.2)

The pysbd `Segmenter` is built lazily and cached at module level — the
rule trie is non-trivial to construct.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pysbd

if TYPE_CHECKING:
    from goldens.creation._elements_stub import DocumentElement

__all__ = ["decompose_to_sub_units"]

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+")
_segmenter: pysbd.Segmenter | None = None


def _get_segmenter() -> pysbd.Segmenter:
    global _segmenter
    if _segmenter is None:
        _segmenter = pysbd.Segmenter(language="de", clean=False)
    return _segmenter


def decompose_to_sub_units(element: DocumentElement) -> tuple[str, ...]:
    et = element.element_type
    content = element.content

    if et == "paragraph":
        if not content.strip():
            return ()
        seg = _get_segmenter()
        sentences = [s.strip() for s in seg.segment(content)]
        return tuple(s for s in sentences if s)

    if et == "table":
        # Pair the header (first line) with each data row so each
        # sub-unit carries column meaning. Spec §4.2 + §9: "header +
        # that row".
        lines = [ln for ln in content.split("\n") if ln.strip()]
        if len(lines) <= 1:
            # Header-only or empty → no testable rows.
            return ()
        header = lines[0]
        return tuple(f"{header}\n{row}" for row in lines[1:])

    if et == "list_item":
        out: list[str] = []
        for raw in content.split("\n"):
            stripped = _BULLET_RE.sub("", raw).strip()
            if stripped:
                out.append(stripped)
        return tuple(out)

    # heading / figure: skip in v1.
    return ()
