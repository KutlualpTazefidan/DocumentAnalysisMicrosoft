"""Tests for ingestion.chunkers.section.SectionChunker."""

from __future__ import annotations


def test_section_chunker_name() -> None:
    from ingestion.chunkers.section import SectionChunker

    assert SectionChunker.name == "section"


def test_section_chunker_produces_chunks_at_section_heading_boundaries(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="gnb-b-147-2001-rev-1",
        source_file="GNB B 147_2001 Rev. 1.pdf",
    )

    # Fixture has: title (no body), pageHeader (skip), 1. Introduction (2 bodies),
    # pageFooter (skip), 2. Methods (1 body), footnote (skip).
    # The chunker treats title as a section start, so:
    #   1. title → empty body
    #   2. 1. Introduction → 2 bodies joined
    #   3. 2. Methods → 1 body
    assert len(chunks) == 3


def test_section_chunker_skips_noise_roles(sample_analyze_result: dict) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="x.pdf",
    )

    all_text = " ".join(c.chunk for c in chunks)
    assert "Page header" not in all_text
    assert "Page 2 / 5" not in all_text
    assert "Footnote text" not in all_text


def test_section_chunker_chunk_id_format(sample_analyze_result: dict) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="my-slug",
        source_file="x.pdf",
    )

    assert chunks[0].chunk_id == "my-slug-001"
    assert chunks[1].chunk_id == "my-slug-002"
    assert chunks[2].chunk_id == "my-slug-003"


def test_section_chunker_carries_title_into_each_chunk(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="x.pdf",
    )

    for c in chunks:
        assert c.title == "Test Document Title"


def test_section_chunker_section_heading_per_chunk(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="x.pdf",
    )

    headings = [c.section_heading for c in chunks]
    assert headings == ["Test Document Title", "1. Introduction", "2. Methods"]


def test_section_chunker_carries_source_file_into_each_chunk(
    sample_analyze_result: dict,
) -> None:
    from ingestion.chunkers.section import SectionChunker

    chunker = SectionChunker()
    chunks = chunker.chunk(
        sample_analyze_result,
        slug="x",
        source_file="my-file.pdf",
    )

    for c in chunks:
        assert c.source_file == "my-file.pdf"


def test_section_chunker_handles_empty_paragraphs() -> None:
    """A document with no paragraphs produces no chunks."""
    from ingestion.chunkers.section import SectionChunker

    empty = {"_ingestion_metadata": {}, "analyzeResult": {"paragraphs": []}}
    chunker = SectionChunker()
    chunks = chunker.chunk(empty, slug="x", source_file="x.pdf")
    assert chunks == []


def test_section_chunker_handles_no_title() -> None:
    """If no paragraph has role='title', title field is empty string."""
    from ingestion.chunkers.section import SectionChunker

    no_title = {
        "_ingestion_metadata": {},
        "analyzeResult": {
            "paragraphs": [
                {"content": "1. Section A", "role": "sectionHeading"},
                {"content": "Body", "role": None},
            ],
        },
    }
    chunker = SectionChunker()
    chunks = chunker.chunk(no_title, slug="x", source_file="x.pdf")
    assert len(chunks) == 1
    assert chunks[0].title == ""
