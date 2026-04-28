"""Tests for ingestion.chunk.chunk()."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _write_analyze_json(path: Path, slug: str, source_file: str) -> None:
    body = {
        "_ingestion_metadata": {
            "source_file": source_file,
            "slug": slug,
            "timestamp_utc": "20260427T143000",
        },
        "analyzeResult": {
            "paragraphs": [
                {"content": "Title", "role": "title"},
                {"content": "1. Intro", "role": "sectionHeading"},
                {"content": "Body.", "role": None},
            ],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")


def test_chunk_writes_jsonl_to_auto_derived_path(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "src" / "analyze.json"
    _write_analyze_json(in_path, slug="my-doc", source_file="my-doc.pdf")

    outputs_root = tmp_path / "outputs-root"
    with (
        patch("ingestion.chunk._outputs_root", return_value=outputs_root),
        patch("ingestion.chunk.now_compact_utc", return_value="20260427T143100"),
    ):
        out_path = chunk(in_path, strategy="section")

    expected = outputs_root / "my-doc" / "chunk" / "20260427T143100-section.jsonl"
    assert out_path == expected
    assert out_path.exists()


def test_chunk_writes_one_jsonl_line_per_chunk(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="x", source_file="x.pdf")
    out_path = tmp_path / "out.jsonl"

    chunk(in_path, strategy="section", out_path=out_path)

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2  # title (empty body) + 1. Intro section
    for line in lines:
        record = json.loads(line)
        assert "chunk_id" in record
        assert record["source_file"] == "x.pdf"


def test_chunk_uses_explicit_out_path_when_given(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="x", source_file="x.pdf")
    explicit = tmp_path / "explicit_dir" / "result.jsonl"

    out = chunk(in_path, strategy="section", out_path=explicit)

    assert out == explicit
    assert explicit.exists()


def test_chunk_raises_on_unknown_strategy(tmp_path: Path) -> None:
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="x", source_file="x.pdf")

    with pytest.raises(ValueError, match="Unknown chunker strategy"):
        chunk(in_path, strategy="bogus", out_path=tmp_path / "out.jsonl")


def test_chunk_reads_slug_and_source_file_from_metadata(tmp_path: Path) -> None:
    """The user does not need to re-supply slug/source_file at chunk stage."""
    from ingestion.chunk import chunk

    in_path = tmp_path / "analyze.json"
    _write_analyze_json(in_path, slug="from-meta", source_file="meta-file.pdf")
    out_path = tmp_path / "out.jsonl"

    chunk(in_path, strategy="section", out_path=out_path)
    line = json.loads(out_path.read_text(encoding="utf-8").strip().split("\n")[0])
    assert line["chunk_id"].startswith("from-meta-")
    assert line["source_file"] == "meta-file.pdf"
