"""CLI-stage handler for the embed pipeline step.

Reads a chunks JSONL (text only), embeds each chunk via query_index's
`get_embedding`, writes an embedded JSONL with a `vector` field added.

Token truncation: each chunk's embed input (`{section_heading} {chunk}`)
is truncated to 8191 tokens — the hard limit of the text-embedding-3-large
model. Without truncation, very long sections (appendices, bibliographies)
cause API errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import tiktoken
from query_index import get_embedding

from ingestion.timestamp import now_compact_utc

if TYPE_CHECKING:
    from query_index import Config

_MAX_TOKENS = 8191
_ENC = tiktoken.get_encoding("cl100k_base")


def _truncate_for_embedding(text: str) -> str:
    tokens = _ENC.encode(text)
    if len(tokens) <= _MAX_TOKENS:
        return text
    return str(_ENC.decode(tokens[:_MAX_TOKENS]))


def _outputs_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "features").is_dir():
            return parent / "outputs"
    return Path.cwd() / "outputs"


def _derive_out_path(in_path: Path) -> Path:
    """Auto-derive: outputs/<slug>/embed/<ts>-<strategy>.jsonl

    The strategy is taken from the input filename (e.g. '...-section.jsonl').
    The slug is taken from the parent-of-parent directory name (chunk/).
    """
    slug = in_path.parent.parent.name
    stem = in_path.stem  # e.g. '20260427T143100-section'
    parts = stem.split("-", 1)
    strategy = parts[1] if len(parts) > 1 else "unknown"
    ts = now_compact_utc()
    return _outputs_root() / slug / "embed" / f"{ts}-{strategy}.jsonl"


def embed_chunks(
    in_path: Path,
    out_path: Path | None = None,
    cfg: Config | None = None,
) -> Path:
    """Embed each chunk in `in_path`; write an embedded JSONL to `out_path`."""
    if cfg is None:
        from query_index import Config as _Cfg

        cfg = _Cfg.from_env()

    if out_path is None:
        out_path = _derive_out_path(in_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with in_path.open("r", encoding="utf-8") as src, out_path.open("w", encoding="utf-8") as dst:
        for raw_line in src:
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            embed_text = _truncate_for_embedding(f"{record['section_heading']} {record['chunk']}")
            record["vector"] = get_embedding(embed_text, cfg)
            dst.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1

    print(f"Embedded {n} chunks → {out_path}")
    return out_path
