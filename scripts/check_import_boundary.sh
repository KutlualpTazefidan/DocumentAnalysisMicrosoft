#!/usr/bin/env bash
# Enforce per-package import boundaries:
#  1. Search & OpenAI imports (azure.search.*, azure.identity.*, openai.*)
#     — only features/query-index/.
#  2. Document Intelligence imports (azure.ai.documentintelligence.*)
#     — only features/query-index/ OR features/ingestion/.
#
# Note: azure.core.credentials.AzureKeyCredential is treated as a generic
# credential primitive and is allowed everywhere within features/.
#
# Both checks share these regex constraints:
#  - Match imports at any indentation level (catches TYPE_CHECKING blocks
#    and lazy/conditional imports inside functions).
#  - Anchor the package name so prefix-collisions (e.g. import openai_async)
#    are NOT flagged.
#  - Allow submodule imports and plain top-level forms.

set -euo pipefail

if [ ! -d features ]; then
    exit 0
fi

# --- Check 1: search/openai imports — only query-index ---
violations_search="$(grep -rEn '[[:space:]]*(import|from)[[:space:]]+(azure\.search|azure\.identity|openai)([.[:space:]]|$)' \
    --include='*.py' \
    features/ \
    | grep -v '^features/query-index/' \
    || true)"

if [ -n "$violations_search" ]; then
    echo "BOUNDARY VIOLATION: azure.search.*, azure.identity.*, and openai.* imports are only allowed inside features/query-index/"
    echo "$violations_search"
    exit 1
fi

# --- Check 2: documentintelligence imports — only query-index OR ingestion ---
violations_docintel="$(grep -rEn '[[:space:]]*(import|from)[[:space:]]+azure\.ai\.documentintelligence([.[:space:]]|$)' \
    --include='*.py' \
    features/ \
    | grep -v -E '^features/(query-index|ingestion)/' \
    || true)"

if [ -n "$violations_docintel" ]; then
    echo "BOUNDARY VIOLATION: azure.ai.documentintelligence imports are only allowed inside features/query-index/ or features/ingestion/"
    echo "$violations_docintel"
    exit 1
fi

exit 0
