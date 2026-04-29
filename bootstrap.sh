#!/usr/bin/env bash
# Create the development venv and install the workspace in editable mode.
set -euo pipefail

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements-dev.txt

if [ -f features/core/pyproject.toml ]; then
    pip install -e features/core
fi

if [ -f features/pipelines/microsoft/retrieval/pyproject.toml ]; then
    pip install -e features/pipelines/microsoft/retrieval
fi
if [ -f features/evaluators/chunk_match/pyproject.toml ]; then
    pip install -e features/evaluators/chunk_match
fi
if [ -f features/pipelines/microsoft/ingestion/pyproject.toml ]; then
    pip install -e features/pipelines/microsoft/ingestion
fi

pre-commit install

echo
echo "Bootstrap complete."
echo "Activate with: source .venv/bin/activate"
