# DocumentAnalysisMicrosoft

A retrieval-quality evaluation harness for an Azure AI Search index, structured as a small monorepo of feature packages.

## Workspace separation pattern

This repository follows a workspace separation pattern:

- **This workspace** is for development. Sample / non-sensitive data lives in `data/`; tests and lint pass without touching real Azure services.
- **Production runs** happen in a separate cloned workspace maintained by the user, with real data in `data/` and real credentials in `.env`.

The following are gitignored so each cloned workspace has its own copy:

- `data/`, `data_dummy/`
- `.env`
- `features/*/datasets/golden_*.jsonl`
- `features/*/reports/`, `features/*/logs/`
- `.venv/` and Python build/cache artefacts

## Layout

```
features/
  pipelines/
    microsoft/
      ingestion/        # PDF -> JSON -> chunks -> embeddings -> Azure index
      retrieval/        # Azure AI Search wrapper (only package importing azure.search/openai)
  evaluators/
    chunk_match/        # retrieval-quality evaluation pipeline
archive/
  query_index_v0.py     # original prototype, preserved unchanged
  semantic_chunking.ipynb
  llm_query_index.ipynb
docs/
  superpowers/
    specs/
    plans/
  evaluation/
    metrics-rationale.md
```

## Setup

```bash
./bootstrap.sh
source .venv/bin/activate
make test
```

`bootstrap.sh` creates a single root venv, installs all feature packages in editable mode, and installs the pre-commit hooks (including the boundary check that confines `azure.*` and `openai` imports to `features/pipelines/microsoft/retrieval/`).

## Development workflow

```bash
make test       # unit tests (mocked, offline)
make lint       # ruff + mypy
make fmt        # auto-fix
make clean      # remove caches and venv
```

## Production workflow (user's separate clone)

```bash
# Set up a fresh production workspace:
git clone <this repo> ~/code/DocumentAnalysisMicrosoft-real
cd ~/code/DocumentAnalysisMicrosoft-real
cp .env.example .env  # and fill in real keys
mkdir data && cp <real PDFs> data/
./bootstrap.sh
source .venv/bin/activate

# Ingest a PDF and immediately measure retrieval quality:
make ingest-and-eval DOC=gnb-b-147-2001-rev-1 STRATEGY=section PDF="data/GNB B 147_2001 Rev. 1.pdf"

# Or stage by stage:
ingest analyze --in data/foo.pdf                                      # PDF -> outputs/foo/analyze/<ts>.json
ingest chunk --in outputs/foo/analyze/<ts>.json --strategy section    # -> outputs/foo/chunk/<ts>-section.jsonl
ingest embed --in outputs/foo/chunk/<ts>-section.jsonl                # -> outputs/foo/embed/<ts>-section.jsonl
ingest upload --in outputs/foo/embed/<ts>-section.jsonl               # -> Azure AI Search index
query-eval eval --doc foo --strategy section                           # -> outputs/foo/reports/<ts>-section.json
```

## Local PDF pipeline (Phase A.0)

A lightweight, offline-first document analysis and review workflow:

```bash
# 1. Prepare PDFs in a local directory
mkdir -p data/raw-pdfs/my-doc
cp my-document.pdf data/raw-pdfs/my-doc/

# 2. Start the backend + frontend dev servers
query-eval segment serve     # FastAPI at localhost:8001
# in another terminal:
cd frontend && npm run dev   # Vite at localhost:5173

# 3. Open the UI
# http://localhost:5173/local-pdf/inbox

# 4. Upload or drag the PDF into the inbox, then:
# - Segment: use DocLayout-YOLO to detect page layout (boxes, tables, reading order)
# - Extract: use MinerU 3 to extract text + semantic annotations
# - Review: 2-pane WYSIWYG editor (PDF on left, Tiptap rich-text on right)
# - Export: generates sourceelements.json (canonical format, drop-in for goldens)
```

**Output**: `data/raw-pdfs/<slug>/sourceelements.json` — a JSON array of `SourceElement` objects with pipeline metadata (`source_pipeline: "local-pdf"`), fully compatible with the existing goldens evaluation system.

**Features**:
- **Segmentation UI**: 2-pane PDF viewer + interactive box overlay; hotkeys for element type (h=heading, p=paragraph, t=table, f=figure, c=caption, q=quote, l=list, x=discard) + multiselect (m/n) + undo (Backspace).
- **Extraction UI**: concurrent region-level re-extract; WYSIWYG with CodeMirror raw-mode toggle; click to link source box.
- **Streaming**: long-running segment/extract operations emit NDJSON progress; sidecar JSON locked with fcntl for safe concurrent writes.
- **API**: 14 endpoints (upload, inbox, segment, extract, region, html, export, etc.).

## Documents

- Design spec: [`docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md`](docs/superpowers/specs/2026-04-27-query-index-evaluation-design.md)
- Metric rationale: [`docs/evaluation/metrics-rationale.md`](docs/evaluation/metrics-rationale.md)
- Implementation plan: [`docs/superpowers/plans/2026-04-27-query-index-evaluation.md`](docs/superpowers/plans/2026-04-27-query-index-evaluation.md)
