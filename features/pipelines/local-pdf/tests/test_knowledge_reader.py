from __future__ import annotations

from pathlib import Path

import pytest
from local_pdf.knowledge.reader import (
    list_bases,
    list_concepts,
    read_concept,
    search_concepts,
)


def _make_base(root: Path) -> None:
    b = root / "demo"
    (b / "behoerden").mkdir(parents=True)
    (b / "index.md").write_text(
        "---\ntype: Index\ntitle: Demo\n---\nEinstieg: [BAM](/behoerden/bam.md).\n",
        encoding="utf-8",
    )
    (b / "behoerden" / "bam.md").write_text(
        "---\ntype: Behörde\ntitle: BAM\ntags: [behoerde]\n---\n"
        "Siehe [Fehlt](/behoerden/missing.md) und [Index](/index.md).\n",
        encoding="utf-8",
    )
    (b / "broken.md").write_text("kein frontmatter hier\n", encoding="utf-8")


def test_list_bases_counts_concepts(tmp_path: Path) -> None:
    _make_base(tmp_path)
    bases = list_bases(tmp_path)
    assert len(bases) == 1
    assert bases[0].name == "demo"
    assert bases[0].title == "Demo"
    assert bases[0].concept_count == 3


def test_list_concepts_returns_type_and_title(tmp_path: Path) -> None:
    _make_base(tmp_path)
    concepts = {c.path: c for c in list_concepts(tmp_path, "demo")}
    assert concepts["behoerden/bam.md"].type == "Behörde"
    assert concepts["behoerden/bam.md"].title == "BAM"
    assert concepts["behoerden/bam.md"].tags == ["behoerde"]


def test_read_concept_extracts_links_and_resolution(tmp_path: Path) -> None:
    _make_base(tmp_path)
    c = read_concept(tmp_path, "demo", "behoerden/bam.md")
    assert c.type == "Behörde"
    assert c.malformed is False
    by_path = {ln.path: ln for ln in c.links}
    assert by_path["index.md"].resolved is True
    assert by_path["behoerden/missing.md"].resolved is False


def test_read_concept_flags_malformed(tmp_path: Path) -> None:
    _make_base(tmp_path)
    c = read_concept(tmp_path, "demo", "broken.md")
    assert c.malformed is True
    assert c.type == ""


def test_read_concept_rejects_traversal(tmp_path: Path) -> None:
    _make_base(tmp_path)
    with pytest.raises(ValueError):
        read_concept(tmp_path, "demo", "../../etc/passwd")


def test_read_concept_missing_raises(tmp_path: Path) -> None:
    _make_base(tmp_path)
    with pytest.raises(FileNotFoundError):
        read_concept(tmp_path, "demo", "behoerden/nope.md")


def test_search_concepts_matches_title_and_body(tmp_path: Path) -> None:
    _make_base(tmp_path)
    hits = {c.path for c in search_concepts(tmp_path, "demo", "bam")}
    assert "behoerden/bam.md" in hits


def test_read_concept_with_relative_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_base(tmp_path)
    monkeypatch.chdir(tmp_path)
    c = read_concept(Path("."), "demo", "behoerden/bam.md")
    assert c.type == "Behörde"
    assert c.path == "behoerden/bam.md"
