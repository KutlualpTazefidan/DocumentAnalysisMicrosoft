"""Evaluation orchestration.

Loads a dataset, runs each non-deprecated example through query_index's
hybrid search, computes per-query records and aggregate metrics, and returns
a MetricsReport ready for serialization.
"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from query_index import Config, hybrid_search

from query_index_eval.datasets import load_dataset
from query_index_eval.metrics import (
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
)
from query_index_eval.schema import (
    AggregateMetrics,
    EvalExample,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


SIZE_THRESHOLD_INDICATIVE = 30
SIZE_THRESHOLD_REPORTABLE = 100


def _size_status(n: int) -> str:
    if n < SIZE_THRESHOLD_INDICATIVE:
        return "indicative"
    if n < SIZE_THRESHOLD_REPORTABLE:
        return "preliminary"
    return "reportable"


def _ranks_and_hits(expected: list[str], retrieved: list[str]) -> tuple[list[int], list[bool]]:
    """For each expected chunk_id, the 1-based rank in retrieved (or -1 if absent),
    and a parallel hits list."""
    ranks: list[int] = []
    hits: list[bool] = []
    for chunk_id in expected:
        if chunk_id in retrieved:
            ranks.append(retrieved.index(chunk_id) + 1)
            hits.append(True)
        else:
            ranks.append(-1)
            hits.append(False)
    return ranks, hits


def _mean(values: Iterable[float]) -> float:
    vs = list(values)
    return sum(vs) / len(vs) if vs else 0.0


def _p95(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    sorted_l = sorted(latencies)
    idx = int(0.95 * (len(sorted_l) - 1))
    return sorted_l[idx]


def run_eval(
    dataset_path: Path,
    top_k_max: int = 20,
    filter_default: str | None = None,
    cfg: Config | None = None,
) -> MetricsReport:
    if cfg is None:
        cfg = Config.from_env()

    all_examples = load_dataset(dataset_path)
    deprecated_count = sum(1 for e in all_examples if e.deprecated)
    active: list[EvalExample] = [e for e in all_examples if not e.deprecated]

    per_query: list[QueryRecord] = []
    latencies: list[float] = []
    failures = 0

    for example in active:
        try:
            t0 = time.perf_counter()
            hits = hybrid_search(
                example.query,
                top=top_k_max,
                filter=example.filter or filter_default,
                cfg=cfg,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            retrieved_ids = [h.chunk_id for h in hits]
            ranks, hit_flags = _ranks_and_hits(example.expected_chunk_ids, retrieved_ids)
            per_query.append(
                QueryRecord(
                    query_id=example.query_id,
                    expected_chunk_ids=list(example.expected_chunk_ids),
                    retrieved_chunk_ids=retrieved_ids,
                    ranks=ranks,
                    hits=hit_flags,
                    latency_ms=latency_ms,
                )
            )
            latencies.append(latency_ms)
        except Exception:
            failures += 1

    pairs = [(set(r.expected_chunk_ids), r.retrieved_chunk_ids) for r in per_query]
    aggregate = AggregateMetrics(
        recall_at_5=_mean(
            recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 5) for r in per_query
        ),
        recall_at_10=_mean(
            recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 10) for r in per_query
        ),
        recall_at_20=_mean(
            recall_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 20) for r in per_query
        ),
        map_score=mean_average_precision(pairs),
        hit_rate_at_1=_mean(
            hit_rate_at_k(set(r.expected_chunk_ids), r.retrieved_chunk_ids, 1) for r in per_query
        ),
        mrr=_mean(mrr(set(r.expected_chunk_ids), r.retrieved_chunk_ids) for r in per_query),
    )

    operational = OperationalMetrics(
        mean_latency_ms=statistics.fmean(latencies) if latencies else 0.0,
        p95_latency_ms=_p95(latencies),
        total_queries=len(per_query),
        total_embedding_calls=len(per_query),
        failure_count=failures,
    )

    metadata = RunMetadata(
        dataset_path=str(dataset_path),
        dataset_size_active=len(active),
        dataset_size_deprecated=deprecated_count,
        embedding_deployment_name=cfg.embedding_deployment_name,
        embedding_model_version=cfg.embedding_model_version,
        azure_openai_api_version=cfg.azure_openai_api_version,
        search_index_name=cfg.ai_search_index_name,
        run_timestamp_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        size_status=_size_status(len(active)),
    )

    return MetricsReport(
        aggregate=aggregate,
        operational=operational,
        metadata=metadata,
        per_query=per_query,
    )
