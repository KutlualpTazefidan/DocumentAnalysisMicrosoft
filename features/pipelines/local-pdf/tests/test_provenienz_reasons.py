"""Unit tests for the reasons corpus storage."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from local_pdf.provenienz.reasons import (
    Reason,
    append_reason,
    build_reason_id,
    read_reasons,
)


def _r(step_kind: str, text: str = "weil X", session_id: str = "s1") -> Reason:
    return Reason(
        reason_id=build_reason_id(),
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


def test_build_reason_id_is_unique_and_ulid_shaped():
    a = build_reason_id()
    b = build_reason_id()
    assert a != b
    assert len(a) == 26
