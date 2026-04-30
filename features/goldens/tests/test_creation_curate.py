"""Tests for goldens.creation.curate helpers."""

from __future__ import annotations

from goldens.creation.curate import query_substring_overlap


def test_overlap_true_for_paste_above_threshold() -> None:
    source = "Der Tragkorb wird in zwei Hälften gefertigt und vor Ort verschraubt."
    pasted = "Der Tragkorb wird in zwei Hälften gefertigt"
    assert query_substring_overlap(pasted, source, threshold=30) is True


def test_overlap_false_for_short_quote_below_threshold() -> None:
    source = "Der Tragkorb wird in zwei Hälften gefertigt und vor Ort verschraubt."
    quoted = "§47 Abs. 2"
    assert query_substring_overlap(quoted, source, threshold=30) is False


def test_overlap_false_when_query_shorter_than_threshold() -> None:
    source = "long source text " * 10
    short = "abc"
    assert query_substring_overlap(short, source, threshold=30) is False


def test_overlap_normalises_whitespace_and_case() -> None:
    source = "Der  Tragkorb   wird in zwei  Hälften gefertigt und vor Ort verschraubt."
    paste = "der tragkorb wird IN zwei Hälften gefertigt"
    assert query_substring_overlap(paste, source, threshold=30) is True


def test_overlap_zero_threshold_short_circuits_true() -> None:
    assert query_substring_overlap("anything", "anything else", threshold=0) is True
