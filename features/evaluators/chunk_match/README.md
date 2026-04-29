# query-index-eval

Retrieval-quality evaluation pipeline for the `query-index` search library.
Consumes `RetrievalEntry` projections from `goldens/storage/`.

## Public API

```python
from query_index_eval import (
    AggregateMetrics,
    MetricsReport,
    OperationalMetrics,
    QueryRecord,
    RunMetadata,
    average_precision,
    hit_rate_at_k,
    mean_average_precision,
    mrr,
    recall_at_k,
    run_eval,
)

# Goldens are loaded from the event-sourced store:
from pathlib import Path

from goldens import iter_active_retrieval_entries

dataset = Path("outputs/<doc>/datasets/golden_events_v1.jsonl")
entries = iter_active_retrieval_entries(dataset)
report = run_eval(entries=entries, dataset_path=str(dataset))
```

## CLI

```bash
query-eval eval --top 20                 # run evaluation, write report
query-eval eval --doc <doc-slug>         # uses outputs/<slug>/datasets/golden_events_v1.jsonl
query-eval report --compare A.json B.json
query-eval schema-discovery              # dump current index schema
```

## Datasets

Golden retrieval entries live in `outputs/<doc-slug>/datasets/golden_events_v1.jsonl`
as an append-only event log written by `goldens` curation tools (Phase A.4 +).
This package is a read-only consumer of that log.

## Reports

Produced under `outputs/<doc-slug>/reports/<utc-timestamp>-<strategy>.json`
(or `outputs/reports/...` if `--doc` is not given). Gitignored.

## Tests

```bash
pytest features/evaluators/chunk_match/
```

All tests are mocked — `query_index` calls are patched at the import boundary;
`goldens` data is constructed in-memory via the `make_entry` fixture.
