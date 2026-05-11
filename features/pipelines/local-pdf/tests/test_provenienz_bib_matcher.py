"""Tests for the BibFileMatcher heuristic that resolves a bibliography
citation to a local-corpus slug via token overlap.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

from local_pdf.provenienz.bib_matcher import _tokenize, match_bib_to_corpus


def _seed_doc(data_root: Path, slug: str, filename: str, title: str = "") -> None:
    d = data_root / slug
    d.mkdir(parents=True, exist_ok=True)
    meta = {"slug": slug, "filename": filename, "pages": 1, "status": "raw"}
    if title:
        meta["title"] = title
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_tokenize_folds_umlauts_and_drops_short():
    # NFKD strips diacritics: "Versandstück" → "Versandstuck".
    assert _tokenize("Versandstück") == {"versandstuck"}
    assert _tokenize("GNB B 137/2001") == {"gnb", "137", "2001"}  # "B" dropped (<3)


def test_tokenize_handles_special_chars():
    out = _tokenize("Typ B(U)F-Versandstück (TR K 0152)")
    assert "typ" in out
    assert "versandstuck" in out
    assert "0152" in out


def test_tokenize_folds_ss_explicitly():
    # ß has no NFKD decomposition; we hand-fold to "ss" so "Maße" matches "Masse".
    assert _tokenize("Außenmaß") == {"aussenmass"}


def test_match_bib_to_corpus_finds_obvious_match(tmp_path: Path):
    """Citation 'GNB B 137/2001' resolves to the slug
    'gnb-b-137-2001-rev-2' via filename-token overlap.
    """
    _seed_doc(tmp_path, "gnb-b-137-2001-rev-2", "GNB B 137_2001 Rev. 2.pdf")
    _seed_doc(tmp_path, "gnb-b-147-2001-rev-1", "GNB B 147_2001 Rev. 1.pdf")
    citation = "GNB B 137/2001 (TR K 0152) Typ B(U)F-Versandstück Transport- und Lagerbehälter"
    out = match_bib_to_corpus(citation, tmp_path)
    assert out is not None
    assert out["slug"] == "gnb-b-137-2001-rev-2"
    assert out["score"] >= 2
    assert "gnb" in out["matched_tokens"]
    assert "137" in out["matched_tokens"]


def test_match_bib_to_corpus_returns_none_when_below_threshold(tmp_path: Path):
    """A citation that shares only one token with any doc is NOT
    surfaced — too weak to be useful, likely coincidence.
    """
    _seed_doc(tmp_path, "gnb-b-147-2001-rev-1", "GNB B 147_2001 Rev. 1.pdf")
    # Only "gnb" overlaps — score=1 < threshold (2).
    out = match_bib_to_corpus("Some GNB-style report from elsewhere", tmp_path)
    assert out is None


def test_match_bib_to_corpus_returns_none_when_no_corpus(tmp_path: Path):
    """Empty data_root → None (no docs to match against)."""
    out = match_bib_to_corpus("[3] GNB B 137/2001", tmp_path)
    assert out is None


def test_match_bib_to_corpus_picks_highest_score(tmp_path: Path):
    """Both docs partially match — pick the one with more overlap."""
    _seed_doc(tmp_path, "gnb-b-137-2001-rev-2", "GNB B 137_2001 Rev. 2.pdf")
    _seed_doc(tmp_path, "wti-37-02-rev-0", "WTI 37_02 Rev. 0.pdf")
    citation = "GNB B 137/2001 (TR K 0152) Typ B(U)F-Versandstück"
    out = match_bib_to_corpus(citation, tmp_path)
    assert out is not None
    assert out["slug"] == "gnb-b-137-2001-rev-2"


def test_match_bib_to_corpus_uses_title_when_present(tmp_path: Path):
    """Token overlap also reads the optional ``title`` field of meta.json."""
    _seed_doc(
        tmp_path,
        "doc-a",
        "doc-a.pdf",
        title="Validierung des Finite-Elemente-Programms ANSYS",
    )
    out = match_bib_to_corpus(
        "[8] WTI-Bericht Nr. WTI/37/02, Validierung Finite-Elemente ANSYS",
        tmp_path,
    )
    assert out is not None
    assert out["slug"] == "doc-a"
    assert "validierung" in out["matched_tokens"]


def test_match_bib_to_corpus_skips_non_dirs_and_missing_meta(tmp_path: Path):
    """Stray files at data_root level + dirs without meta.json don't
    crash the walk."""
    (tmp_path / "loose-file.txt").write_text("hi")
    (tmp_path / "no-meta-dir").mkdir()  # dir but no meta.json
    _seed_doc(tmp_path, "real-doc", "real.pdf", title="Vorgehen Berechnung")
    out = match_bib_to_corpus("Vorgehen Berechnung Kontext", tmp_path)
    assert out is not None
    assert out["slug"] == "real-doc"
