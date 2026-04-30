from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def test_slugify_filename_basic() -> None:
    from local_pdf.storage.slug import slugify_filename

    assert slugify_filename("BAM Tragkorb 2024.pdf") == "bam-tragkorb-2024"
    assert slugify_filename("DIN_EN_12100.pdf") == "din-en-12100"
    assert slugify_filename("normative.PDF") == "normative"


def test_slugify_strips_non_ascii() -> None:
    from local_pdf.storage.slug import slugify_filename

    assert slugify_filename("Prüfverfahren.pdf") == "prufverfahren"


def test_unique_slug_appends_counter_when_collision(tmp_path: Path) -> None:
    from local_pdf.storage.slug import unique_slug

    (tmp_path / "report").mkdir()
    (tmp_path / "report-2").mkdir()
    out = unique_slug(tmp_path, "Report.pdf")
    assert out == "report-3"


def test_unique_slug_no_collision_returns_base(tmp_path: Path) -> None:
    from local_pdf.storage.slug import unique_slug

    out = unique_slug(tmp_path, "Spec.pdf")
    assert out == "spec"
