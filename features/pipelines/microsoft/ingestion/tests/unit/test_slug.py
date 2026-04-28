"""Tests for ingestion.slug.slug_from_filename()."""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "filename,want",
    [
        ("GNB B 147_2001 Rev. 1.pdf", "gnb-b-147-2001-rev-1"),
        ("IAEA TS-G-1.1.pdf", "iaea-ts-g-1-1"),
        ("simple.pdf", "simple"),
        ("Simple.pdf", "simple"),
        ("with spaces and dots.pdf", "with-spaces-and-dots"),
        ("Mixed_Case-File.PDF", "mixed-case-file"),
        ("trailing-spaces  .pdf", "trailing-spaces"),
        ("---hyphens---in---name.pdf", "hyphens-in-name"),
        ("file_without_extension", "file-without-extension"),
        ("__leading_underscores.pdf", "leading-underscores"),
    ],
)
def test_slug_from_filename(filename, want) -> None:
    from ingestion.slug import slug_from_filename

    assert slug_from_filename(filename) == want


def test_slug_from_filename_strips_unicode_punct() -> None:
    """Non-ASCII punctuation should be replaced or stripped."""
    from ingestion.slug import slug_from_filename

    assert slug_from_filename("Bericht (Rev. 1).pdf") == "bericht-rev-1"


def test_slug_from_filename_collapses_runs() -> None:
    from ingestion.slug import slug_from_filename

    assert slug_from_filename("a   b___c...d.pdf") == "a-b-c-d"
