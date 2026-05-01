#!/usr/bin/env bash
# Phase A.1.0 end-to-end smoke. Requires: server running on :8001 with
# GOLDENS_API_TOKEN=ADMIN-T and LOCAL_PDF_DATA_ROOT pointing at a clean dir.
set -euo pipefail

ADMIN="ADMIN-T"
BASE="http://127.0.0.1:8001"

echo "[1/8] /api/_features (public)"
curl -fsS "$BASE/api/_features" | grep -q '"admin"'

echo "[2/8] auth check admin"
curl -fsS -X POST "$BASE/api/auth/check" -H 'content-type: application/json' \
  -d '{"token":"'"$ADMIN"'"}' | grep -q '"role":"admin"'

echo "[3/8] legacy /api/docs returns 410"
test "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/docs")" = "410"

echo "[4/8] admin upload PDF"
echo '%PDF-1.4 dummy' > /tmp/smoke.pdf
SLUG=$(curl -fsS -X POST "$BASE/api/admin/docs" -H "X-Auth-Token: $ADMIN" \
  -F "file=@/tmp/smoke.pdf" | python -c 'import sys,json; print(json.load(sys.stdin)["slug"])')
echo "uploaded: $SLUG"

echo "[5/8] admin creates curator"
RAW=$(curl -fsS -X POST "$BASE/api/admin/curators" -H "X-Auth-Token: $ADMIN" \
  -H 'content-type: application/json' -d '{"name":"Dr Smoke"}' | \
  python -c 'import sys,json; print(json.load(sys.stdin)["token"])')

echo "[6/8] admin assigns + publishes (after manually setting state to extracted)"
python -c "
import json, os
from pathlib import Path
root = Path(os.environ['LOCAL_PDF_DATA_ROOT'])
m = json.loads((root / '$SLUG' / 'meta.json').read_text())
m['status'] = 'extracted'
(root / '$SLUG' / 'meta.json').write_text(json.dumps(m, indent=2))
"
CID=$(curl -fsS "$BASE/api/admin/curators" -H "X-Auth-Token: $ADMIN" | \
  python -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')
curl -fsS -X POST "$BASE/api/admin/docs/$SLUG/curators" -H "X-Auth-Token: $ADMIN" \
  -H 'content-type: application/json' -d "{\"curator_id\":\"$CID\"}"
curl -fsS -X POST "$BASE/api/admin/docs/$SLUG/publish" -H "X-Auth-Token: $ADMIN"

echo "[7/8] curator sees the doc"
curl -fsS "$BASE/api/curate/docs" -H "X-Auth-Token: $RAW" | grep -q "$SLUG"

echo "[8/8] curator blocked from /api/admin/*"
test "$(curl -s -o /dev/null -w '%{http_code}' \
  -H "X-Auth-Token: $RAW" "$BASE/api/admin/docs")" = "403"

echo "smoke OK"
