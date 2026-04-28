"""Tests for query_index_eval.runner.run_eval()."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from pathlib import Path


def _write_dataset(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _example_dict(qid: str, expected: list[str], deprecated: bool = False) -> dict:
    return {
        "query_id": qid,
        "query": f"Q? {qid}",
        "expected_chunk_ids": expected,
        "source": "curated",
        "chunk_hashes": {c: f"sha256:hash_{c}" for c in expected},
        "filter": None,
        "deprecated": deprecated,
        "created_at": "2026-04-27T10:00:00Z",
        "notes": None,
    }


def _hit(chunk_id: str, score: float = 0.5):
    """Build a minimal SearchHit-like object."""
    from query_index.types import SearchHit

    return SearchHit(chunk_id=chunk_id, title="t", chunk="x", score=score)


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Same fixture content as in query-index/tests/conftest.py — replicate
    here because conftest scopes don't cross packages."""
    values = {
        "AI_FOUNDRY_KEY": "test-foundry-key",
        "AI_FOUNDRY_ENDPOINT": "https://test-foundry.example.com",
        "AI_SEARCH_KEY": "test-search-key",
        "AI_SEARCH_ENDPOINT": "https://test-search.example.com",
        "AI_SEARCH_INDEX_NAME": "test-index",
        "EMBEDDING_DEPLOYMENT_NAME": "test-embedding-deployment",
        "EMBEDDING_MODEL_VERSION": "1",
        "EMBEDDING_DIMENSIONS": "3072",
        "AZURE_OPENAI_API_VERSION": "2024-02-01",
    }
    for k, v in values.items():
        monkeypatch.setenv(k, v)
    return values


def test_run_eval_skips_deprecated_examples(tmp_dataset_path: Path, env_vars: dict) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [
            _example_dict("g0001", ["c1"]),
            _example_dict("g0002", ["c2"], deprecated=True),
        ],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert len(report.per_query) == 1
    assert report.per_query[0].query_id == "g0001"
    assert report.metadata.dataset_size_active == 1
    assert report.metadata.dataset_size_deprecated == 1


def test_run_eval_records_ranks_and_hits_per_query(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(tmp_dataset_path, [_example_dict("g0001", ["c2", "c4"])])

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3, 4, 5]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    record = report.per_query[0]
    assert record.expected_chunk_ids == ["c2", "c4"]
    assert record.retrieved_chunk_ids == ["c1", "c2", "c3", "c4", "c5"]
    assert record.ranks == [2, 4]
    assert record.hits == [True, True]


def test_run_eval_records_minus_one_rank_when_expected_not_found(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(tmp_dataset_path, [_example_dict("g0001", ["c99"])])

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    record = report.per_query[0]
    assert record.ranks == [-1]
    assert record.hits == [False]


def test_run_eval_aggregates_metrics_across_queries(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [
            _example_dict("g0001", ["c1"]),
            _example_dict("g0002", ["c2"]),
            _example_dict("g0003", ["c99"]),
        ],
    )

    call_to_results = {
        "Q? g0001": [_hit("c1"), _hit("c5"), _hit("c6")],
        "Q? g0002": [_hit("c4"), _hit("c2"), _hit("c6")],
        "Q? g0003": [_hit("c4"), _hit("c5"), _hit("c6")],
    }

    def fake_search(query, top, filter=None, cfg=None):
        return call_to_results[query]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    # Hit rate@1: only g0001 has rank 1 -> 1/3
    assert report.aggregate.hit_rate_at_1 == pytest.approx(1 / 3)
    # MRR: (1 + 1/2 + 0) / 3 = 0.5
    assert report.aggregate.mrr == pytest.approx(0.5)
    # Recall@5: g0001 1.0, g0002 1.0, g0003 0.0; mean = 2/3
    assert report.aggregate.recall_at_5 == pytest.approx(2 / 3)


def test_run_eval_assigns_size_status_indicative_for_small_n(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [_example_dict(f"g{i:04d}", ["c1"]) for i in range(5)],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.size_status == "indicative"


def test_run_eval_assigns_size_status_preliminary_in_30_to_99(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [_example_dict(f"g{i:04d}", ["c1"]) for i in range(50)],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.size_status == "preliminary"


def test_run_eval_assigns_size_status_reportable_at_100(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(
        tmp_dataset_path,
        [_example_dict(f"g{i:04d}", ["c1"]) for i in range(100)],
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.size_status == "reportable"


def test_run_eval_metadata_includes_embedding_and_index_info(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    _write_dataset(tmp_dataset_path, [_example_dict("g0001", ["c1"])])

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    md = report.metadata
    assert md.embedding_deployment_name == env_vars["EMBEDDING_DEPLOYMENT_NAME"]
    assert md.embedding_model_version == env_vars["EMBEDDING_MODEL_VERSION"]
    assert md.azure_openai_api_version == env_vars["AZURE_OPENAI_API_VERSION"]
    assert md.search_index_name == env_vars["AI_SEARCH_INDEX_NAME"]
    assert md.run_timestamp_utc.endswith("Z")


def test_run_eval_passes_filter_per_example_when_set(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    from query_index_eval.runner import run_eval

    rows = [_example_dict("g0001", ["c1"])]
    rows[0]["filter"] = "category eq 'manual'"
    _write_dataset(tmp_dataset_path, rows)

    captured: dict = {}

    def fake_search(query, top, filter=None, cfg=None):
        captured["filter"] = filter
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        run_eval(tmp_dataset_path, top_k_max=20)

    assert captured["filter"] == "category eq 'manual'"


def test_run_eval_detects_hash_drift_when_chunk_content_changed(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    """If an expected chunk's hash no longer matches what is in the index,
    runner records the example's query_id in drifted_query_ids."""
    from query_index_eval.runner import run_eval

    rows = [
        {
            "query_id": "g0001",
            "query": "Q?",
            "expected_chunk_ids": ["c1"],
            "source": "curated",
            "chunk_hashes": {"c1": "sha256:expected-hash-from-curation-time"},
            "filter": None,
            "deprecated": False,
            "created_at": "2026-04-27T10:00:00Z",
            "notes": None,
        }
    ]
    tmp_dataset_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk

        return Chunk(chunk_id="c1", title="T", chunk="DIFFERENT CONTENT NOW")

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert "g0001" in report.metadata.drifted_query_ids


def test_run_eval_no_drift_when_hash_matches(
    tmp_dataset_path: Path,
    env_vars: dict,
) -> None:
    """If the chunk's hash matches, drifted_query_ids stays empty."""
    import hashlib

    from query_index_eval.runner import run_eval

    chunk_text = "exact same content"
    expected_hash = (
        "sha256:" + hashlib.sha256(" ".join(chunk_text.split()).encode("utf-8")).hexdigest()
    )

    rows = [
        {
            "query_id": "g0001",
            "query": "Q?",
            "expected_chunk_ids": ["c1"],
            "source": "curated",
            "chunk_hashes": {"c1": expected_hash},
            "filter": None,
            "deprecated": False,
            "created_at": "2026-04-27T10:00:00Z",
            "notes": None,
        }
    ]
    tmp_dataset_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk

        return Chunk(chunk_id="c1", title="T", chunk=chunk_text)

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(tmp_dataset_path, top_k_max=20)

    assert report.metadata.drifted_query_ids == []
