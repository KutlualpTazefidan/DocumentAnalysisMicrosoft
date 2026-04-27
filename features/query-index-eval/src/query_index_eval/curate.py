"""Interactive curation CLI helpers.

Two mechanical safeties for the curation flow:
1. require_interactive_tty() — refuses to run if stdin is not a tty.
   Prevents accidental invocation through a non-interactive shell, in
   particular an LLM agent's Bash tool which has no tty.
2. query_substring_overlap() — heuristic detection of accidental copy-paste
   of chunk text into the user-written query.

The full interactive loop is implemented in `interactive_curate()`; it is
exercised by the user manually rather than by unit tests, because its body
is mostly `input()` and `print()` calls that depend on a real terminal.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from query_index import Config, get_chunk, hybrid_search, sample_chunks

from query_index_eval.datasets import append_example
from query_index_eval.schema import EvalExample

if TYPE_CHECKING:
    from pathlib import Path


SUBSTRING_OVERLAP_THRESHOLD = 30
"""If a user-written query shares a contiguous substring of this many
characters or more with the chunk text, warn before saving — that's almost
certainly accidental copy-paste rather than a real user query."""


def require_interactive_tty() -> None:
    """Exit with code 1 if stdin is not an interactive TTY."""
    try:
        fd = sys.stdin.fileno()
    except (AttributeError, OSError, ValueError):
        # stdin has no real file descriptor (e.g. StringIO in tests);
        # fall back to the raw stdin fd (0) so that os.isatty can still
        # be monkeypatched in tests.
        fd = 0
    is_tty = os.isatty(fd)
    if not is_tty:
        print(
            "ERROR: query-eval curate requires an interactive TTY. "
            "Run it in a regular terminal — not through a non-interactive shell, "
            "subprocess, or LLM agent tool.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def query_substring_overlap(query: str, chunk_text: str) -> int:
    """Return the length of the longest contiguous substring of `query` that
    also appears in `chunk_text`. Used as a copy-paste heuristic.

    Single-character matches are noise for this heuristic and are ignored;
    the function returns 0 if no substring of length ≥ 2 is shared.
    """
    if not query or not chunk_text:
        return 0
    longest = 1  # start at 1 so we only track substrings longer than 1 char
    n = len(query)
    found = False
    for start in range(n):
        end = start + longest + 1
        while end <= n and query[start:end] in chunk_text:
            longest = end - start
            found = True
            end += 1
    return longest if found else 0


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()


def _next_query_id(existing_ids: set[str]) -> str:
    n = 1
    while f"g{n:04d}" in existing_ids:
        n += 1
    return f"g{n:04d}"


def interactive_curate(
    dataset_path: Path,
    chunk_id: str | None = None,
    seed: int | None = None,
    cfg: Config | None = None,
) -> None:
    require_interactive_tty()
    if cfg is None:
        cfg = Config.from_env()

    print(
        "REMINDER: never paste chunk text into Claude or any other shared chat. "
        "Reference chunks only by chunk_id.\n"
    )

    if chunk_id is not None:
        chunk = get_chunk(chunk_id, cfg)
    else:
        seed_val = seed if seed is not None else int(datetime.now(UTC).timestamp())
        [chunk] = sample_chunks(1, seed=seed_val, cfg=cfg)

    print("=" * 70)
    print(f"chunk_id: {chunk.chunk_id}")
    print(f"title:    {chunk.title}")
    print("-" * 70)
    print(chunk.chunk)
    print("=" * 70)

    query = input("Write a query this chunk should answer:\n> ").strip()

    overlap = query_substring_overlap(query, chunk.chunk)
    if overlap >= SUBSTRING_OVERLAP_THRESHOLD:
        print(
            f"WARNING: your query shares a {overlap}-char substring with the chunk "
            "— this looks like accidental copy-paste."
        )
        if input("Save anyway? [y/N] ").strip().lower() != "y":
            print("Aborted; nothing saved.")
            return

    show_search = input("Run hybrid_search on this query to preview top-5? [y/N] ").strip().lower()
    if show_search == "y":
        hits = hybrid_search(query, top=5, cfg=cfg)
        print("Top 5 retrieved:")
        for i, h in enumerate(hits, start=1):
            print(f"  {i}. {h.chunk_id}  (score {h.score:.3f})")

    if input(f"Add example to {dataset_path}? [y/N] ").strip().lower() != "y":
        print("Aborted; nothing saved.")
        return

    existing_ids: set[str] = set()
    if dataset_path.exists():
        from query_index_eval.datasets import load_dataset

        existing_ids = {e.query_id for e in load_dataset(dataset_path)}

    example = EvalExample(
        query_id=_next_query_id(existing_ids),
        query=query,
        expected_chunk_ids=[chunk.chunk_id],
        source="curated",
        chunk_hashes={chunk.chunk_id: _hash(chunk.chunk)},
        filter=None,
        deprecated=False,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        notes=None,
    )
    append_example(dataset_path, example)
    print(f"Saved {example.query_id} to {dataset_path}")
    print(
        "\nREMINDER: never paste chunk text into Claude or any other shared chat. "
        "Reference chunks only by chunk_id."
    )
