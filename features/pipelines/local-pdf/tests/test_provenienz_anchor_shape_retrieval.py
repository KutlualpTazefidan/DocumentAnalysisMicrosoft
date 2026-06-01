"""Unit tests for Phase-2 anchor-shape retrieval in _gather_reason_guidance.

When the next-step planner is about to act on an anchor of a given shape,
it prefers past corrections that targeted the same shape (binary
patterns + anchor_kind match) over more recent ones on different shapes.
This makes "the agent learned from a similar table-correction" actually
visible at retrieval time rather than just at storage time.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from local_pdf.api.routers.admin import provenienz as router_mod
from local_pdf.provenienz.reasons import Reason, append_reason
from local_pdf.provenienz.storage import Node


def _seed(
    data_root: Path,
    *,
    text: str,
    fp: dict,
    sec: int,
) -> Reason:
    """Append a reason with an explicit created_at so tier-then-recency
    ordering can be asserted without relying on append latency. Same
    step_kind across all seeded reasons so the prioritisation is the
    only differentiator."""
    return append_reason(
        data_root,
        Reason(
            reason_id="",
            step_kind="extract_claims",
            session_id="prev",
            proposal_id="prevp",
            proposal_summary="vorher: Auto-Empfehlung",
            override_summary="lieber so",
            reason_text=text,
            actor="human",
            created_at=f"2026-01-01T00:00:{sec:02d}Z",
            anchor_fingerprint=fp,
        ),
    )


def _anchor(payload: dict) -> Node:
    return Node(
        node_id="n",
        session_id="s",
        kind="chunk",
        payload=payload,
        actor="planner",
    )


def test_pattern_overlap_beats_recency_when_last_n_is_tight(tmp_path: Path):
    # Older reason on a table-shaped anchor; newer reason on a different
    # shape. With last_n=1 only one wins — the tier-2 (pattern overlap)
    # match must take it.
    _seed(
        tmp_path,
        text="alt aber gleiche Form",
        fp={"anchor_kind": "chunk", "patterns": ["has_table"]},
        sec=1,
    )
    _seed(
        tmp_path,
        text="neuer aber andere Form",
        fp={"anchor_kind": "chunk", "patterns": []},
        sec=2,
    )
    block, refs = router_mod._gather_reason_guidance(
        tmp_path,
        "extract_claims",
        anchor=_anchor({"html_snippet": "<p><table>X</table></p>"}),
        last_n=1,
    )
    assert len(refs) == 1
    assert "alt aber gleiche Form" in block
    assert "neuer aber andere Form" not in block


def test_anchor_kind_match_without_pattern_overlap_outranks_no_fingerprint(
    tmp_path: Path,
):
    # Tier 1 (anchor_kind match, no pattern overlap) beats tier 0
    # (no fingerprint / mismatch) even if the legacy reason is newer.
    _seed(
        tmp_path,
        text="gleiche kind, keine pattern",
        fp={"anchor_kind": "chunk", "patterns": []},
        sec=1,
    )
    _seed(tmp_path, text="legacy ohne fingerprint", fp={}, sec=2)
    block, _refs = router_mod._gather_reason_guidance(
        tmp_path,
        "extract_claims",
        anchor=_anchor({"text": "kurz"}),
        last_n=1,
    )
    assert "gleiche kind, keine pattern" in block
    assert "legacy ohne fingerprint" not in block


def test_falls_back_to_recency_when_no_anchor(tmp_path: Path):
    # Without an anchor, current_fp is empty → every candidate scores
    # tier 0 → ordering collapses to "newest first". Preserves the
    # Phase-1 contract for callers that don't pass an anchor.
    _seed(
        tmp_path,
        text="alt",
        fp={"anchor_kind": "chunk", "patterns": ["has_table"]},
        sec=1,
    )
    _seed(tmp_path, text="neu", fp={"anchor_kind": "chunk", "patterns": []}, sec=2)
    block, _refs = router_mod._gather_reason_guidance(
        tmp_path,
        "extract_claims",
        anchor=None,
        last_n=1,
    )
    assert "neu" in block
    assert "alt" not in block


def test_legacy_reasons_without_fingerprint_still_surface_in_block(tmp_path: Path):
    # The only seeded reason carries no fingerprint (Phase-1 origin).
    # It must still appear so the migration doesn't silently lose
    # historical corrections from the LLM context window.
    _seed(tmp_path, text="legacy", fp={}, sec=1)
    block, refs = router_mod._gather_reason_guidance(
        tmp_path,
        "extract_claims",
        anchor=_anchor({"text": "kurz"}),
        last_n=5,
    )
    assert "legacy" in block
    assert len(refs) == 1


def test_kept_reasons_render_in_chronological_order(tmp_path: Path):
    # Tier ordering decides *which* reasons land in the block; the
    # block itself reads chronologically so the prompt feels like a
    # small timeline of past corrections.
    _seed(
        tmp_path,
        text="zuerst",
        fp={"anchor_kind": "chunk", "patterns": ["has_table"]},
        sec=1,
    )
    _seed(
        tmp_path,
        text="dann",
        fp={"anchor_kind": "chunk", "patterns": ["has_table"]},
        sec=2,
    )
    block, _refs = router_mod._gather_reason_guidance(
        tmp_path,
        "extract_claims",
        anchor=_anchor({"html_snippet": "<p><table>x</table></p>"}),
        last_n=5,
    )
    assert block.index("zuerst") < block.index("dann")


def test_no_reasons_returns_empty_block_and_refs(tmp_path: Path):
    # Preserves the Phase-1 sentinel that signals "skip the
    # Frühere-Korrekturen header in the prompt".
    block, refs = router_mod._gather_reason_guidance(
        tmp_path,
        "extract_claims",
        anchor=_anchor({"text": "kurz"}),
        last_n=5,
    )
    assert block == ""
    assert refs == []
