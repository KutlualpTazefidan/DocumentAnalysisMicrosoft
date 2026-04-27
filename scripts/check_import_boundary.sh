#!/usr/bin/env bash
# Enforce: only features/query-index/ may import azure.* or openai.
# Exits non-zero with the offending lines if a violation is found.
set -euo pipefail

if [ ! -d features ]; then
    exit 0
fi

violations="$(grep -rEn '^(import|from)[[:space:]]+(azure|openai)' \
    --include='*.py' \
    features/ \
    | grep -v '^features/query-index/' \
    || true)"

if [ -n "$violations" ]; then
    echo "BOUNDARY VIOLATION: azure/openai imports are only allowed inside features/query-index/"
    echo "$violations"
    exit 1
fi
exit 0
