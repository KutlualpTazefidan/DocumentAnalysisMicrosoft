"""Frozen dataclasses for the eval pipeline.

Designed so that `dataclasses.asdict` produces a JSON-serialisable structure.
The metric/report dataclasses compose into a single MetricsReport that the CLI
serialises to disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AggregateMetrics:
    recall_at_5: float
    recall_at_10: float
    recall_at_20: float
    map_score: float
    hit_rate_at_1: float
    mrr: float


@dataclass(frozen=True)
class OperationalMetrics:
    mean_latency_ms: float
    p95_latency_ms: float
    total_queries: int
    total_embedding_calls: int
    failure_count: int


@dataclass(frozen=True)
class RunMetadata:
    dataset_path: str
    dataset_size_active: int
    dataset_size_deprecated: int
    embedding_deployment_name: str
    embedding_model_version: str
    azure_openai_api_version: str
    search_index_name: str
    run_timestamp_utc: str
    size_status: str
    drifted_entry_ids: list[str] = field(default_factory=list)
    drift_warning: bool = False


@dataclass(frozen=True)
class QueryRecord:
    entry_id: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    ranks: list[int]
    hits: list[bool]
    latency_ms: float


@dataclass(frozen=True)
class MetricsReport:
    aggregate: AggregateMetrics
    operational: OperationalMetrics
    metadata: RunMetadata
    per_query: list[QueryRecord] = field(default_factory=list)
