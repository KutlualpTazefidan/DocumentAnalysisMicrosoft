#!/usr/bin/env bash
# Enforce: only features/query-index/ may import azure.* or openai.
# Exits non-zero with the offending lines if a violation is found.

# Regex constraints:
#  - Matches at any indentation level (catches `if TYPE_CHECKING:` blocks
#    and lazy/conditional imports inside functions).
#  - Anchors the package name so `import openai_async` and similar prefix-
#    collisions are NOT flagged.
#  - Allows submodule imports (`import azure.search.documents`) and
#    plain-top-level (`from azure import X`).
set -euo pipefail

if [ ! -d features ]; then
    exit 0
fi

violations="$(grep -rEn '[[:space:]]*(import|from)[[:space:]]+(azure|openai)([.[:space:]]|$)' \
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
