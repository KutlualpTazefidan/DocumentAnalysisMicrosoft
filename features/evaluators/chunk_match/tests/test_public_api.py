"""Tests for the re-exported public API at query_index_eval.__init__."""

from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index_eval

    expected = {
        "AggregateMetrics",
        "EvalExample",
        "MetricsReport",
        "OperationalMetrics",
        "QueryRecord",
        "RunMetadata",
        "average_precision",
        "hit_rate_at_k",
        "load_dataset",
        "mean_average_precision",
        "mrr",
        "recall_at_k",
        "run_eval",
    }
    missing = expected - set(dir(query_index_eval))
    assert not missing, f"Missing public exports: {missing}"
