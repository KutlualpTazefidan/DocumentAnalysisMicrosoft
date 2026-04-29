"""Tests for the re-exported public API at query_index_eval.__init__."""

from __future__ import annotations


def test_public_api_exports_expected_names() -> None:
    import query_index_eval

    expected = {
        "AggregateMetrics",
        "MetricsReport",
        "OperationalMetrics",
        "QueryRecord",
        "RunMetadata",
        "average_precision",
        "hit_rate_at_k",
        "mean_average_precision",
        "mrr",
        "recall_at_k",
        "run_eval",
    }
    missing = expected - set(dir(query_index_eval))
    assert not missing, f"Missing public exports: {missing}"


def test_public_api_does_not_re_export_load_dataset() -> None:
    """A.7 deleted load_dataset along with the EvalExample-JSONL read path;
    the public API now reads only via goldens.iter_active_retrieval_entries.
    This guards against a refactor accidentally re-exporting the old name
    and silently restoring two read paths."""
    import query_index_eval

    assert "load_dataset" not in dir(query_index_eval)


def test_public_api_does_not_re_export_eval_example() -> None:
    """A.7 deleted the EvalExample dataclass entirely. This guards against
    a refactor accidentally re-introducing it and reviving the old shape."""
    import query_index_eval

    assert "EvalExample" not in dir(query_index_eval)
