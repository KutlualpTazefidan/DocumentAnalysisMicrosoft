"""Shared fixtures for query_index_eval tests.

The `query_index` package is patched at module level so that no test in this
suite ever touches Azure. Fixtures expose: a temporary JSONL path, sample
EvalExample objects, and a sample MetricsReport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tmp_dataset_path(tmp_path: Path) -> Path:
    return tmp_path / "golden_v1.jsonl"


@pytest.fixture
def sample_example_dict() -> dict:
    return {
        "query_id": "g0001",
        "query": "Wo ist die Änderung des Tragkorbdurchmessers aufgeführt?",
        "expected_chunk_ids": ["c42"],
        "source": "curated",
        "chunk_hashes": {"c42": "sha256:abc"},
        "filter": None,
        "deprecated": False,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }
