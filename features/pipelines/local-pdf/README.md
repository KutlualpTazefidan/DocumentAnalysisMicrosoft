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
