"""Tests for ingestion.embed.embed_chunks()."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path


def _write_chunks_jsonl(path, n: int = 2, *, slug: str = "x", chunk_text: str = "body") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(
                json.dumps(
                    {
                        "chunk_id": f"{slug}-{i + 1:03d}",
                        "title": "T",
                        "section_heading": f"Section {i + 1}",
                        "chunk": chunk_text,
                        "source_file": "x.pdf",
                    }
                )
                + "\n"
            )


def test_embed_chunks_adds_vector_field_to_each_line(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_chunks_jsonl(in_path, n=3)

    fake_vec = [0.0] * 3072
    with patch("ingestion.embed.get_embedding", return_value=fake_vec):
        result_path = embed_chunks(in_path, out_path=out_path)

    assert result_path == out_path
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    for line in lines:
        record = json.loads(line)
        assert record["vector"] == fake_vec
        assert "chunk_id" in record  # other fields preserved


def test_embed_chunks_passes_section_heading_plus_chunk_to_embedder(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Embed input is `{section_heading} {chunk}` per the notebook convention."""
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    _write_chunks_jsonl(in_path, n=1, chunk_text="some body content")

    captured: dict = {}

    def fake_embed(text, cfg=None):
        captured["text"] = text
        return [0.0] * 3072

    with patch("ingestion.embed.get_embedding", side_effect=fake_embed):
        embed_chunks(in_path, out_path=out_path)

    assert "Section 1" in captured["text"]
    assert "some body content" in captured["text"]


def test_embed_chunks_truncates_long_text_to_8191_tokens(
    env_vars: dict[str, str], tmp_path: Path
) -> None:
    """Texts longer than 8191 tokens are truncated before embedding."""
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    huge = "word " * 50000  # ~50k tokens easily
    _write_chunks_jsonl(in_path, n=1, chunk_text=huge)

    captured: dict = {}

    def fake_embed(text, cfg=None):
        captured["text"] = text
        return [0.0] * 3072

    with patch("ingestion.embed.get_embedding", side_effect=fake_embed):
        embed_chunks(in_path, out_path=out_path)

    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    assert len(enc.encode(captured["text"])) <= 8191


def test_embed_chunks_auto_derives_out_path(env_vars: dict[str, str], tmp_path: Path) -> None:
    from ingestion.embed import embed_chunks

    chunk_dir = tmp_path / "outputs-root" / "myslug" / "chunk"
    chunk_dir.mkdir(parents=True)
    in_path = chunk_dir / "20260427T143100-section.jsonl"
    _write_chunks_jsonl(in_path, n=1)

    with (
        patch("ingestion.embed.get_embedding", return_value=[0.0] * 3072),
        patch("ingestion.embed._outputs_root", return_value=tmp_path / "outputs-root"),
        patch("ingestion.embed.now_compact_utc", return_value="20260427T143200"),
    ):
        out = embed_chunks(in_path)

    expected = tmp_path / "outputs-root" / "myslug" / "embed" / "20260427T143200-section.jsonl"
    assert out == expected
    assert out.exists()


def test_embed_chunks_skips_blank_lines(env_vars: dict[str, str], tmp_path: Path) -> None:
    from ingestion.embed import embed_chunks

    in_path = tmp_path / "chunks.jsonl"
    out_path = tmp_path / "out.jsonl"
    in_path.write_text(
        "\n"  # leading blank
        + json.dumps(
            {
                "chunk_id": "x-001",
                "title": "T",
                "section_heading": "S",
                "chunk": "body",
                "source_file": "x.pdf",
            }
        )
        + "\n"
        + "   \n"  # whitespace-only
        + "\n",  # trailing blank
        encoding="utf-8",
    )

    with patch("ingestion.embed.get_embedding", return_value=[0.0] * 3072):
        embed_chunks(in_path, out_path=out_path)

    lines = [ln for ln in out_path.read_text(encoding="utf-8").split("\n") if ln.strip()]
    assert len(lines) == 1
