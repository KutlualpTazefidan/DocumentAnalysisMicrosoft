"""Tests for query_index_eval.datasets — JSONL I/O with mutation rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _example(qid: str = "g0001", deprecated: bool = False) -> dict:
    return {
        "query_id": qid,
        "query": f"Question {qid}?",
        "expected_chunk_ids": [f"c{qid[1:]}"],
        "source": "curated",
        "chunk_hashes": {f"c{qid[1:]}": f"sha256:hash_{qid}"},
        "filter": None,
        "deprecated": deprecated,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }


def test_load_dataset_returns_empty_list_when_file_missing(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import load_dataset

    assert load_dataset(tmp_dataset_path) == []


def test_load_dataset_parses_jsonl_into_eval_examples(tmp_dataset_path: Path) -> None:
    import json

    from query_index_eval.datasets import load_dataset
    from query_index_eval.schema import EvalExample

    rows = [_example("g0001"), _example("g0002")]
    tmp_dataset_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    result = load_dataset(tmp_dataset_path)
    assert len(result) == 2
    assert all(isinstance(e, EvalExample) for e in result)
    assert {e.query_id for e in result} == {"g0001", "g0002"}


def test_append_example_creates_file_if_missing(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import append_example, load_dataset
    from query_index_eval.schema import EvalExample

    e = EvalExample(**_example("g0001"))
    append_example(tmp_dataset_path, e)
    assert tmp_dataset_path.exists()
    loaded = load_dataset(tmp_dataset_path)
    assert len(loaded) == 1
    assert loaded[0].query_id == "g0001"


def test_append_example_creates_parent_directories_if_missing(tmp_path: Path) -> None:
    """Auto-creates intermediate directories so callers (e.g. the curate CLI)
    can pass a path like outputs/<slug>/datasets/golden_v1.jsonl without
    having to mkdir the chain themselves."""
    from query_index_eval.datasets import append_example, load_dataset
    from query_index_eval.schema import EvalExample

    nested_path = tmp_path / "outputs" / "my-doc" / "datasets" / "golden_v1.jsonl"
    assert not nested_path.parent.exists()  # precondition

    e = EvalExample(**_example("g0001"))
    append_example(nested_path, e)

    assert nested_path.exists()
    assert nested_path.parent.exists()
    loaded = load_dataset(nested_path)
    assert len(loaded) == 1
    assert loaded[0].query_id == "g0001"


def test_append_example_appends_subsequent_rows(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import append_example, load_dataset
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001")))
    append_example(tmp_dataset_path, EvalExample(**_example("g0002")))
    loaded = load_dataset(tmp_dataset_path)
    assert [e.query_id for e in loaded] == ["g0001", "g0002"]


def test_append_example_rejects_duplicate_query_id(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import DatasetMutationError, append_example
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001")))
    with pytest.raises(DatasetMutationError, match="g0001"):
        append_example(tmp_dataset_path, EvalExample(**_example("g0001")))


def test_deprecate_example_flips_flag_in_place(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import (
        append_example,
        deprecate_example,
        load_dataset,
    )
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001")))
    append_example(tmp_dataset_path, EvalExample(**_example("g0002")))

    deprecate_example(tmp_dataset_path, "g0001")
    loaded = load_dataset(tmp_dataset_path)
    by_id = {e.query_id: e for e in loaded}
    assert by_id["g0001"].deprecated is True
    assert by_id["g0002"].deprecated is False


def test_deprecate_example_raises_when_id_missing(tmp_dataset_path: Path) -> None:
    from query_index_eval.datasets import DatasetMutationError, deprecate_example

    tmp_dataset_path.write_text("")
    with pytest.raises(DatasetMutationError, match="not found"):
        deprecate_example(tmp_dataset_path, "g0099")


def test_deprecate_example_refuses_to_undeprecate(tmp_dataset_path: Path) -> None:
    """Once deprecated, an example stays deprecated — calling deprecate_example
    on an already-deprecated id raises."""
    from query_index_eval.datasets import (
        DatasetMutationError,
        append_example,
        deprecate_example,
        load_dataset,
    )
    from query_index_eval.schema import EvalExample

    append_example(tmp_dataset_path, EvalExample(**_example("g0001", deprecated=True)))
    with pytest.raises(DatasetMutationError, match="already deprecated"):
        deprecate_example(tmp_dataset_path, "g0001")
    loaded = load_dataset(tmp_dataset_path)
    assert loaded[0].deprecated is True
