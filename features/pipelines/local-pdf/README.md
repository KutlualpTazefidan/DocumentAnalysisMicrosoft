# local-pdf

Phase A.0 — local, free-tools PDF → SourceElement pipeline.

## Quickstart

```bash
source .venv/bin/activate
uv pip install -e features/pipelines/local-pdf
export GOLDENS_API_TOKEN=$(openssl rand -hex 16)
export LOCAL_PDF_DATA_ROOT=$PWD/data/raw-pdfs
query-eval segment serve --port 8001
```

Then open http://127.0.0.1:5173/#/local-pdf/inbox in the dev frontend.

See `docs/superpowers/specs/2026-04-30-local-pdf-pipeline-design.md`.

## Streaming event schema

The `/segment` and `/extract` endpoints stream NDJSON `WorkerEvent` lines
defined in `local_pdf.workers.base`. The seven event types are:

| `type`             | when                                           | key fields                                                  |
|--------------------|-------------------------------------------------|-------------------------------------------------------------|
| `model-loading`    | weights starting to load                       | `source`, `vram_estimate_mb`                                |
| `model-loaded`     | weights resident                                | `vram_actual_mb`, `load_seconds`                            |
| `work-progress`    | one step of work done (page or box)             | `stage`, `current`, `total`, `eta_seconds`, `vram_current_mb` |
| `work-complete`    | run loop finished                               | `items_processed`, `total_seconds`, `output_summary`        |
| `model-unloading`  | starting to free VRAM                          | —                                                           |
| `model-unloaded`   | VRAM freed                                      | `vram_freed_mb`                                             |
| `work-failed`      | uncaught error during load/run/unload           | `stage`, `reason`, `recoverable`, `hint`                    |

Every event also carries `model: str` and `timestamp_ms: int`. The
frontend `streamReducer.ts` folds the stream into a single `StreamState`
rendered by `StageIndicator` (collapsed badge, top-right of segment +
extract pages) and `StageTimeline` (drawer when expanded).
