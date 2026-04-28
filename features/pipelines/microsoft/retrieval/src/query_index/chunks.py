"""Chunk-fetching helpers used by curation and synthesis flows.

Reads the canonical notebook schema: `id`, `chunk`, `title`, optional
`section_heading`, optional `source_file`.
"""

from __future__ import annotations

import random

from query_index.client import get_search_client
from query_index.config import Config
from query_index.types import Chunk

SAMPLE_WINDOW = 100
"""Default candidate-window size for sample_chunks.

We pull SAMPLE_WINDOW (or n, whichever is larger) candidates from the index,
then shuffle them with a seeded RNG and take the first n. This gives a
meaningfully random sample — pulling exactly n would just return the top-n by
relevance, which defeats the purpose of sampling.
"""


def get_chunk(chunk_id: str, cfg: Config | None = None) -> Chunk:
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_client(cfg)
    doc = client.get_document(key=chunk_id)
    return Chunk(
        chunk_id=doc["id"],
        title=doc["title"],
        chunk=doc["chunk"],
        section_heading=doc.get("section_heading"),
        source_file=doc.get("source_file"),
    )


def sample_chunks(n: int, seed: int, cfg: Config | None = None) -> list[Chunk]:
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if cfg is None:
        cfg = Config.from_env()
    client = get_search_client(cfg)
    window = max(n, SAMPLE_WINDOW)
    raw = list(client.search(search_text="*", top=window))
    rng = random.Random(seed)
    rng.shuffle(raw)
    selected = raw[:n]
    return [
        Chunk(
            chunk_id=d["id"],
            title=d["title"],
            chunk=d["chunk"],
            section_heading=d.get("section_heading"),
            source_file=d.get("source_file"),
        )
        for d in selected
    ]
