"""Unit tests for the reasons corpus storage."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from local_pdf.provenienz.reasons import (
    Reason,
    append_reason,
    compute_anchor_fingerprint,
    read_reasons,
)
from local_pdf.provenienz.storage import new_id


def _r(step_kind: str, text: str = "weil X", session_id: str = "s1") -> Reason:
    return Reason(
        reason_id=new_id(),
        step_kind=step_kind,
        session_id=session_id,
        proposal_id="prop1",
        proposal_summary="rec",
        override_summary="ovr",
        reason_text=text,
        actor="human",
    )


def test_append_and_read_round_trips_one_reason(tmp_path: Path):
    append_reason(tmp_path, _r("extract_claims"))
    out = read_reasons(tmp_path)
    assert len(out) == 1
    assert out[0].step_kind == "extract_claims"
    assert out[0].reason_text == "weil X"
    assert out[0].created_at  # populated on append


def test_read_filters_by_step_kind(tmp_path: Path):
    append_reason(tmp_path, _r("extract_claims", "ec"))
    append_reason(tmp_path, _r("evaluate", "ev"))
    append_reason(tmp_path, _r("extract_claims", "ec2"))
    out = read_reasons(tmp_path, step_kind="extract_claims")
    assert [r.reason_text for r in out] == ["ec", "ec2"]


def test_read_caps_at_last_n(tmp_path: Path):
    for i in range(7):
        append_reason(tmp_path, _r("extract_claims", f"r{i}"))
    out = read_reasons(tmp_path, step_kind="extract_claims", last_n=3)
    assert [r.reason_text for r in out] == ["r4", "r5", "r6"]


def test_read_empty_when_file_missing(tmp_path: Path):
    assert read_reasons(tmp_path) == []


# ── Phase-2: anchor_fingerprint computation ────────────────────────────


def test_fingerprint_empty_for_blank_anchor_kind():
    # Convention: empty kind = "no anchor" → empty dict so callers can
    # always store the result without conditionals.
    assert compute_anchor_fingerprint("", {"text": "anything"}) == {}


def test_fingerprint_detects_table_in_html_snippet():
    fp = compute_anchor_fingerprint("chunk", {"html_snippet": "<p>Vor <table>X</table> Nach</p>"})
    assert fp["anchor_kind"] == "chunk"
    assert "has_table" in fp["patterns"]


def test_fingerprint_detects_list_in_html_and_markdown():
    html_fp = compute_anchor_fingerprint("chunk", {"html_snippet": "<ul><li>a</li></ul>"})
    md_fp = compute_anchor_fingerprint("chunk", {"text": "- erster\n- zweiter\n- dritter"})
    assert "has_list" in html_fp["patterns"]
    assert "has_list" in md_fp["patterns"]


def test_fingerprint_detects_inline_formula_and_latex_command():
    inline = compute_anchor_fingerprint("chunk", {"text": "Wärme $Q = m c$"})
    cmd = compute_anchor_fingerprint("chunk", {"text": r"\frac{a}{b}"})
    assert "has_formula" in inline["patterns"]
    assert "has_formula" in cmd["patterns"]


def test_fingerprint_short_vs_long_text():
    short = compute_anchor_fingerprint("chunk", {"text": "kurz"})
    long_payload = compute_anchor_fingerprint("chunk", {"text": "X" * 2000})
    assert "short_text" in short["patterns"]
    assert "long_text" in long_payload["patterns"]
    assert "short_text" not in long_payload["patterns"]


def test_fingerprint_length_check_strips_html_tags():
    # 1500-char tag soup with very little real text should classify as
    # short_text — the heuristic must measure rendered length, not raw HTML.
    html = "<span>" * 200 + "kurz" + "</span>" * 200
    fp = compute_anchor_fingerprint("chunk", {"html_snippet": html})
    assert "short_text" in fp["patterns"]
    assert "long_text" not in fp["patterns"]


def test_fingerprint_patterns_are_deduped_and_sorted():
    # Multiple payload keys feeding into the same pattern signal must
    # not produce duplicate entries; the sorted-set output keeps the
    # downstream tier-comparison deterministic.
    fp = compute_anchor_fingerprint(
        "chunk",
        {"text": "<table>A</table>", "html_snippet": "<table>B</table>"},
    )
    assert fp["patterns"] == sorted(set(fp["patterns"]))


def test_fingerprint_roundtrips_through_skill_store(tmp_path: Path):
    # Round-trip via the legacy NOTE-skill packing path: the marker line
    # must survive append + read so retrieval-time scoring sees the
    # same fingerprint the recording site computed.
    seeded = append_reason(
        tmp_path,
        Reason(
            reason_id="",
            step_kind="extract_claims",
            session_id="s",
            proposal_id="p",
            proposal_summary="rec",
            override_summary="ovr",
            reason_text="weil",
            actor="human",
            anchor_fingerprint={"anchor_kind": "chunk", "patterns": ["has_table"]},
        ),
    )
    [loaded] = read_reasons(tmp_path)
    assert loaded.reason_id == seeded.reason_id
    assert loaded.anchor_fingerprint == {
        "anchor_kind": "chunk",
        "patterns": ["has_table"],
    }


def test_legacy_reason_without_fingerprint_round_trips_with_empty_dict(tmp_path: Path):
    # Reasons written before Phase 2 had no fingerprint field — the
    # decoder must return an empty dict (NOT raise) so legacy NOTEs keep
    # surfacing.
    append_reason(tmp_path, _r("extract_claims"))
    [loaded] = read_reasons(tmp_path)
    assert loaded.anchor_fingerprint == {}
