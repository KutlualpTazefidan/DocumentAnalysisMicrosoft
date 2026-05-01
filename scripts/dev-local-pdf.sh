#!/usr/bin/env bash
# scripts/dev-local-pdf.sh — one-shot dev launcher for the local-pdf pipeline.
#
# Reads .env.local-pdf-test (gitignored) for project-specific env, sources the
# venv, then runs the backend on 127.0.0.1:8000. Frontend you start separately
# with `cd frontend && npm run dev` (uses the Vite proxy automatically).
#
# Usage:
#   bash scripts/dev-local-pdf.sh
#
# First-time setup (~/.gitignore handles the .env file):
#   1. cp .env.local-pdf-test.example .env.local-pdf-test
#   2. edit .env.local-pdf-test with your token + data dir + yolo weights path
#   3. download yolo weights (see README) if not already
#   4. bash scripts/dev-local-pdf.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE=".env.local-pdf-test"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.local-pdf-test.example and fill in values." >&2
  exit 2
fi

# Load env (set -a auto-exports every assignment until set +a).
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Activate venv.
# shellcheck disable=SC1091
source .venv/bin/activate

# Sanity-check required vars.
: "${GOLDENS_API_TOKEN:?must be set in $ENV_FILE}"
: "${LOCAL_PDF_DATA_ROOT:?must be set in $ENV_FILE}"
: "${LOCAL_PDF_YOLO_WEIGHTS:?must be set in $ENV_FILE}"

mkdir -p "$LOCAL_PDF_DATA_ROOT"

if [ ! -f "$LOCAL_PDF_YOLO_WEIGHTS" ]; then
  echo "ERROR: weights file not found at $LOCAL_PDF_YOLO_WEIGHTS" >&2
  echo "Download with:" >&2
  echo "  source .venv/bin/activate && huggingface-cli download juliozhao/DocLayout-YOLO-DocStructBench doclayout_yolo_docstructbench_imgsz1024.pt --local-dir ~/models/doclayout-yolo" >&2
  exit 3
fi

echo "==> launching backend on 127.0.0.1:8000"
echo "    GOLDENS_API_TOKEN     = ${GOLDENS_API_TOKEN}"
echo "    LOCAL_PDF_DATA_ROOT   = ${LOCAL_PDF_DATA_ROOT}"
echo "    LOCAL_PDF_YOLO_WEIGHTS= ${LOCAL_PDF_YOLO_WEIGHTS}"
echo

exec query-eval segment serve --port 8000 --host 127.0.0.1
