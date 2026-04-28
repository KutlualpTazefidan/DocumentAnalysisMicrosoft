"""CLI-stage handler for the chunk pipeline step.

Reads an analyze JSON (with `_ingestion_metadata` sidecar), runs the named
chunker strategy, writes a JSONL where each line is one RawChunk.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ingestion.chunkers.registry import get_chunker
from ingestion.timestamp import now_compact_utc


def _outputs_root() -> Path:
    """Return the repository's outputs root.

    Matches the discovery in analyze.py for consistency.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "features").is_dir():
            return parent / "outputs"
    return Path.cwd() / "outputs"


def chunk(
    in_path: Path,
    strategy: str,
    out_path: Path | None = None,
) -> Path:
    """Read an analyze JSON; run a chunker strategy; write chunks JSONL.

    Auto-derived `out_path` (if None): `<outputs_root>/<slug>/chunk/<ts>-<strategy>.jsonl`.

    Slug and source_file are read from the analyze JSON's `_ingestion_metadata`.
    """
    analyze_blob = json.loads(in_path.read_text(encoding="utf-8"))
    metadata = analyze_blob.get("_ingestion_metadata", {})
    slug = metadata.get("slug", "")
    source_file = metadata.get("source_file", "")

    chunker = get_chunker(strategy)  # raises ValueError on unknown name
    raw_chunks = chunker.chunk(analyze_blob, slug=slug, source_file=source_file)

    if out_path is None:
        ts = now_compact_utc()
        out_path = _outputs_root() / slug / "chunk" / f"{ts}-{strategy}.jsonl"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rc in raw_chunks:
            f.write(json.dumps(asdict(rc), ensure_ascii=False) + "\n")

    print(f"Wrote {len(raw_chunks)} chunks → {out_path}")
    return out_path
