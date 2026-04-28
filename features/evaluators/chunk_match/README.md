# query-index-eval

Retrieval-quality evaluation pipeline for the `query-index` search library.

## Public API

```python
from query_index_eval import (
    AggregateMetrics,
    EvalExample,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
    average_precision,
    hit_rate_at_k,
    load_dataset,
    mrr,
    recall_at_k,
    run_eval,
)
```

## CLI

```bash
query-eval eval --top 20                 # run evaluation, write report
query-eval report --compare A.json B.json
query-eval schema-discovery              # dump current index schema
```

## Datasets

Hand-curated golden set lives at `features/evaluators/chunk_match/datasets/golden_v1.jsonl`. Gitignored — your curation work stays local. Format: one `EvalExample` per line, append-only with controlled deprecation.

## Reports

Produced under `features/evaluators/chunk_match/reports/<utc-timestamp>-golden_v1.json`. Gitignored.

## Tests

```bash
pytest features/evaluators/chunk_match/
```

All tests are mocked — `query_index` calls are patched at the import boundary.
