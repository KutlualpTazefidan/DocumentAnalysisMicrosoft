"""Tests for query_index_eval.schema dataclasses."""

from __future__ import annotations


def test_aggregate_metrics_holds_all_metric_fields() -> None:
    from query_index_eval.schema import AggregateMetrics

    m = AggregateMetrics(
        recall_at_5=0.7,
        recall_at_10=0.85,
        recall_at_20=0.95,
        map_score=0.65,
        hit_rate_at_1=0.8,
        mrr=0.72,
    )
    assert m.recall_at_10 == 0.85
    assert m.mrr == 0.72


def test_operational_metrics_holds_counts_and_latency() -> None:
    from query_index_eval.schema import OperationalMetrics

    m = OperationalMetrics(
        mean_latency_ms=120.0,
        p95_latency_ms=350.0,
        total_queries=42,
        total_embedding_calls=42,
        failure_count=1,
    )
    assert m.total_queries == 42


def test_query_record_holds_per_query_data() -> None:
    from query_index_eval.schema import QueryRecord

    r = QueryRecord(
        entry_id="g0001",
        expected_chunk_ids=["c42"],
        retrieved_chunk_ids=["c10", "c42", "c7"],
        ranks=[2],
        hits=[True],
        latency_ms=110.0,
    )
    assert r.ranks == [2]
    assert r.hits == [True]
    assert r.entry_id == "g0001"


def test_run_metadata_includes_embedding_and_size_status() -> None:
    from query_index_eval.schema import RunMetadata

    md = RunMetadata(
        dataset_path="outputs/test/datasets/golden_events_v1.jsonl",
        dataset_size_active=42,
        dataset_size_deprecated=3,
        embedding_deployment_name="text-embedding-3-large",
        embedding_model_version="1",
        azure_openai_api_version="2024-02-01",
        search_index_name="wizard-1",
        run_timestamp_utc="2026-04-27T10:00:00Z",
        size_status="preliminary",
    )
    assert md.size_status == "preliminary"
    assert md.drifted_entry_ids == []


def test_metrics_report_composes_all_subobjects() -> None:
    from query_index_eval.schema import (
        AggregateMetrics,
        MetricsReport,
        OperationalMetrics,
        QueryRecord,
        RunMetadata,
    )

    aggregate = AggregateMetrics(0.7, 0.85, 0.95, 0.65, 0.8, 0.72)
    operational = OperationalMetrics(120.0, 350.0, 42, 42, 1)
    metadata = RunMetadata(
        "outputs/test/datasets/golden_events_v1.jsonl",
        42,
        3,
        "text-embedding-3-large",
        "1",
        "2024-02-01",
        "wizard-1",
        "2026-04-27T10:00:00Z",
        "preliminary",
    )
    record = QueryRecord("g0001", ["c42"], ["c42"], [1], [True], 110.0)
    report = MetricsReport(
        aggregate=aggregate,
        operational=operational,
        metadata=metadata,
        per_query=[record],
    )
    assert report.aggregate is aggregate
    assert len(report.per_query) == 1
