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

if [ -f features/query-index/pyproject.toml ]; then
    pip install -e features/query-index
fi
if [ -f features/query-index-eval/pyproject.toml ]; then
    pip install -e features/query-index-eval
fi

pre-commit install

echo
echo "Bootstrap complete."
echo "Activate with: source .venv/bin/activate"
