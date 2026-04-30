"""Tests for goldens.creation.curate helpers."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest
from goldens.creation.curate import (
    SlugResolutionError,
    StartResolutionError,
    query_substring_overlap,
    resolve_slug,
    resolve_start_position,
)
from goldens.creation.elements.adapter import DocumentElement


def _make_doc(root: Path, slug: str) -> None:
    analyze_dir = root / slug / "analyze"
    analyze_dir.mkdir(parents=True)
    (analyze_dir / "2026-04-29T10-00-00Z.json").write_text("{}", encoding="utf-8")


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


def test_resolve_slug_auto_picks_when_one_doc(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-a")
    assert resolve_slug(None, outputs_root=tmp_path) == "doc-a"


def test_resolve_slug_uses_explicit_when_set(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-a")
    _make_doc(tmp_path, "doc-b")
    assert resolve_slug("doc-b", outputs_root=tmp_path) == "doc-b"


def test_resolve_slug_errors_when_zero_docs(tmp_path: Path) -> None:
    with pytest.raises(SlugResolutionError, match="no candidate"):
        resolve_slug(None, outputs_root=tmp_path)


def test_resolve_slug_errors_when_multiple_docs(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-a")
    _make_doc(tmp_path, "doc-b")
    with pytest.raises(SlugResolutionError, match="doc-a") as excinfo:
        resolve_slug(None, outputs_root=tmp_path)
    assert "doc-b" in str(excinfo.value)


def test_resolve_slug_errors_when_outputs_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(SlugResolutionError, match="does not exist"):
        resolve_slug(None, outputs_root=missing)


def test_resolve_slug_skips_dirs_without_analyze_json(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-real")
    (tmp_path / "doc-noisy").mkdir()
    assert resolve_slug(None, outputs_root=tmp_path) == "doc-real"


def _els(*ids_and_pages: tuple[str, int]) -> list[DocumentElement]:
    return [
        DocumentElement(
            element_id=id_, page_number=page, element_type="paragraph", content=f"c-{id_}"
        )
        for id_, page in ids_and_pages
    ]


def test_resolve_start_exact_id_wins() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p1-bbbbbbbb", 1), ("p2-aaaaaaaa", 2))
    idx = resolve_start_position(elements, explicit="p1-bbbbbbbb", cached=None)
    assert idx == 1


def test_resolve_start_prefix_match_when_no_exact() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p1-bbbbbbbb", 1))
    idx = resolve_start_position(elements, explicit="p1-bb", cached=None)
    assert idx == 1


def test_resolve_start_unknown_id_errors() -> None:
    elements = _els(("p1-aaaaaaaa", 1))
    with pytest.raises(StartResolutionError, match="nothing"):
        resolve_start_position(elements, explicit="p9-zzzzzzzz", cached=None)


def test_resolve_start_falls_back_to_position_cache() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p2-bbbbbbbb", 2), ("p3-cccccccc", 3))
    idx = resolve_start_position(elements, explicit=None, cached="p2-bbbbbbbb")
    assert idx == 1


def test_resolve_start_falls_back_to_zero_when_cache_misses() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p2-bbbbbbbb", 2))
    idx = resolve_start_position(elements, explicit=None, cached="p9-zzzzzzzz")
    assert idx == 0


def test_resolve_start_falls_back_to_zero_when_cache_absent() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p2-bbbbbbbb", 2))
    idx = resolve_start_position(elements, explicit=None, cached=None)
    assert idx == 0
