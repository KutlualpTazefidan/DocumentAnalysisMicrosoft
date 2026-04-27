"""JSONL load/save for EvalExamples with controlled-mutation rules.

Public API:
- `load_dataset(path)` reads JSONL into a list of EvalExample (empty if file missing).
- `append_example(path, example)` appends one row; raises on duplicate query_id.
- `deprecate_example(path, query_id)` flips the example's `deprecated` flag to
  True. Refuses to operate on an already-deprecated row (the rule is "deprecate
  is one-way"); raises if the id is not found.

Direct file edits are not protected. The convention is: only these three
functions touch the JSONL file in process. The rules implement the
"controlled mutation" contract from the design spec.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from query_index_eval.schema import EvalExample

if TYPE_CHECKING:
    from pathlib import Path


class DatasetMutationError(Exception):
    """Raised when a mutation violates the controlled-mutation rules."""


def load_dataset(path: Path) -> list[EvalExample]:
    if not path.exists():
        return []
    examples: list[EvalExample] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            examples.append(EvalExample(**json.loads(line)))
    return examples


def append_example(path: Path, example: EvalExample) -> None:
    existing = load_dataset(path)
    if any(e.query_id == example.query_id for e in existing):
        raise DatasetMutationError(
            f"query_id {example.query_id!r} already exists in {path}; "
            f"deprecate-and-append-new instead of editing in place"
        )
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(example), ensure_ascii=False) + "\n")


def deprecate_example(path: Path, query_id: str) -> None:
    existing = load_dataset(path)
    found = False
    new_rows: list[EvalExample] = []
    for e in existing:
        if e.query_id == query_id:
            found = True
            if e.deprecated:
                raise DatasetMutationError(
                    f"query_id {query_id!r} is already deprecated; "
                    f"deprecation is one-way (no un-deprecate in v1)"
                )
            new_rows.append(
                EvalExample(
                    query_id=e.query_id,
                    query=e.query,
                    expected_chunk_ids=e.expected_chunk_ids,
                    source=e.source,
                    chunk_hashes=e.chunk_hashes,
                    filter=e.filter,
                    deprecated=True,
                    created_at=e.created_at,
                    notes=e.notes,
                )
            )
        else:
            new_rows.append(e)
    if not found:
        raise DatasetMutationError(f"query_id {query_id!r} not found in {path}; cannot deprecate")
    with path.open("w", encoding="utf-8") as f:
        for e in new_rows:
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
