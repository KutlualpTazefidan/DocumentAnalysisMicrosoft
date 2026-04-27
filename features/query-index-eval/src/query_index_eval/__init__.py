"""Public API for the query_index_eval package."""

from query_index_eval.datasets import load_dataset
from query_index_eval.metrics import (
    average_precision,
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
)
from query_index_eval.runner import run_eval
from query_index_eval.schema import (
    AggregateMetrics,
    EvalExample,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
)

__all__ = [
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
]
