"""Tests for query_index_eval.runner.run_eval()."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from goldens import RetrievalEntry


def _hit(chunk_id: str, score: float = 0.5):
    """Build a minimal SearchHit-like object."""
    from query_index.types import SearchHit

    return SearchHit(chunk_id=chunk_id, title="t", chunk="x", score=score)


@pytest.fixture
def env_vars(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replicate query-index env-var fixture (conftest scopes don't cross packages)."""
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


def test_run_eval_records_entry_id_in_per_query(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entry = make_entry(query="What is X?", expected=("c1",))

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=[entry], dataset_path="test")

    assert len(report.per_query) == 1
    assert report.per_query[0].entry_id == entry.entry_id


def test_run_eval_records_ranks_and_hits_per_query(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entry = make_entry(expected=("c2", "c4"))

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3, 4, 5]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=[entry], dataset_path="test")

    record = report.per_query[0]
    assert record.expected_chunk_ids == ["c2", "c4"]
    assert record.retrieved_chunk_ids == ["c1", "c2", "c3", "c4", "c5"]
    assert record.ranks == [2, 4]
    assert record.hits == [True, True]


def test_run_eval_records_minus_one_rank_when_expected_not_found(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entry = make_entry(expected=("c99",))

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit(f"c{i}") for i in [1, 2, 3]]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=[entry], dataset_path="test")

    record = report.per_query[0]
    assert record.ranks == [-1]
    assert record.hits == [False]


def test_run_eval_aggregates_metrics_across_queries(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [
        make_entry(entry_id="e1", query="Q1", expected=("c1",)),
        make_entry(entry_id="e2", query="Q2", expected=("c2",)),
        make_entry(entry_id="e3", query="Q3", expected=("c99",)),
    ]
    call_to_results = {
        "Q1": [_hit("c1"), _hit("c5"), _hit("c6")],
        "Q2": [_hit("c4"), _hit("c2"), _hit("c6")],
        "Q3": [_hit("c4"), _hit("c5"), _hit("c6")],
    }

    def fake_search(query, top, filter=None, cfg=None):
        return call_to_results[query]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    # Hit rate@1: only e1 has rank 1 -> 1/3
    assert report.aggregate.hit_rate_at_1 == pytest.approx(1 / 3)
    # MRR: (1 + 1/2 + 0) / 3 = 0.5
    assert report.aggregate.mrr == pytest.approx(0.5)
    # Recall@5: e1 1.0, e2 1.0, e3 0.0; mean = 2/3
    assert report.aggregate.recall_at_5 == pytest.approx(2 / 3)


def test_run_eval_assigns_size_status_indicative_for_small_n(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [make_entry() for _ in range(5)]

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    assert report.metadata.size_status == "indicative"


def test_run_eval_assigns_size_status_preliminary_in_30_to_99(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [make_entry() for _ in range(50)]

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    assert report.metadata.size_status == "preliminary"


def test_run_eval_assigns_size_status_reportable_at_100(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    entries = [make_entry() for _ in range(100)]

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(entries=entries, dataset_path="test")

    assert report.metadata.size_status == "reportable"


def test_run_eval_metadata_includes_embedding_index_and_dataset_path(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    from query_index_eval.runner import run_eval

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(
            entries=[make_entry()],
            dataset_path="outputs/test/datasets/golden_events_v1.jsonl",
        )

    md = report.metadata
    assert md.dataset_path == "outputs/test/datasets/golden_events_v1.jsonl"
    assert md.embedding_deployment_name == env_vars["EMBEDDING_DEPLOYMENT_NAME"]
    assert md.embedding_model_version == env_vars["EMBEDDING_MODEL_VERSION"]
    assert md.azure_openai_api_version == env_vars["AZURE_OPENAI_API_VERSION"]
    assert md.search_index_name == env_vars["AI_SEARCH_INDEX_NAME"]
    assert md.run_timestamp_utc.endswith("Z")


def test_run_eval_passes_filter_default_to_hybrid_search(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """Per-example filter is gone (Microsoft-OData-coupled); per-run
    filter via filter_default still passes through to hybrid_search."""
    from query_index_eval.runner import run_eval

    captured: dict = {}

    def fake_search(query, top, filter=None, cfg=None):
        captured["filter"] = filter
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        run_eval(
            entries=[make_entry()],
            dataset_path="test",
            filter_default="category eq 'manual'",
        )

    assert captured["filter"] == "category eq 'manual'"


def test_run_eval_detects_hash_drift_when_chunk_content_changed(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """If an expected chunk's hash no longer matches what is in the index,
    runner records the entry's entry_id in drifted_entry_ids."""
    from query_index_eval.runner import run_eval

    entry = make_entry(
        entry_id="e1",
        expected=("c1",),
        chunk_hashes={"c1": "sha256:expected-hash-from-curation-time"},
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk

        return Chunk(chunk_id="c1", title="T", chunk="DIFFERENT CONTENT NOW")

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(entries=[entry], dataset_path="test")

    assert "e1" in report.metadata.drifted_entry_ids


def test_run_eval_no_drift_when_hash_matches(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """If the chunk's hash matches, drifted_entry_ids stays empty."""
    import hashlib

    from query_index_eval.runner import run_eval

    chunk_text = "exact same content"
    expected_hash = (
        "sha256:" + hashlib.sha256(" ".join(chunk_text.split()).encode("utf-8")).hexdigest()
    )

    entry = make_entry(
        entry_id="e1",
        expected=("c1",),
        chunk_hashes={"c1": expected_hash},
    )

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    def fake_get_chunk(chunk_id, cfg=None):
        from query_index.types import Chunk

        return Chunk(chunk_id="c1", title="T", chunk=chunk_text)

    with (
        patch("query_index_eval.runner.hybrid_search", side_effect=fake_search),
        patch("query_index_eval.runner.get_chunk", side_effect=fake_get_chunk),
    ):
        report = run_eval(entries=[entry], dataset_path="test")

    assert report.metadata.drifted_entry_ids == []


def test_run_eval_accepts_iterator_input_and_materializes_internally(
    env_vars: dict,
    make_entry: Callable[..., RetrievalEntry],
) -> None:
    """run_eval accepts any Iterable[RetrievalEntry], including a single-use
    iterator. Internal `list(entries)` enables drift-then-eval multi-pass."""
    from query_index_eval.runner import run_eval

    def fake_search(query, top, filter=None, cfg=None):
        return [_hit("c1")]

    with patch("query_index_eval.runner.hybrid_search", side_effect=fake_search):
        report = run_eval(
            entries=iter([make_entry(), make_entry()]),
            dataset_path="test",
        )

    assert len(report.per_query) == 2
