from __future__ import annotations

from typing import TYPE_CHECKING

from local_pdf.knowledge.docx_to_text import docx_to_text

if TYPE_CHECKING:
    from pathlib import Path


def _make_docx(path: Path, paragraphs: list[str]) -> None:
    import docx

    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    d.save(str(path))


def test_docx_to_text_reads_paragraphs_hermetically(tmp_path: Path) -> None:
    # Hermetic: generate the .docx in the test (the real interview lives under
    # gitignored data/ and is absent in CI / fresh clones).
    docx_path = tmp_path / "demo.docx"
    _make_docx(
        docx_path,
        ["Bauartprüfung erste Zeile.", "Nachweiskonzept zweite Zeile.", "Dritte Zeile."],
    )
    text = docx_to_text(docx_path)
    assert "Bauartprüfung erste Zeile." in text
    assert "Nachweiskonzept zweite Zeile." in text
    # paragraphs separated by newlines, not collapsed into one blob
    assert text.count("\n") >= 2
