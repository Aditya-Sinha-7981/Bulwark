#!/usr/bin/env bash
# Quick CLI sanity pass before opening Thunder Client -- no jq required beyond
# what's already used for pretty-printing (falls back to raw if jq missing).
# Usage: ./api_testing/smoke_test.sh [base_url]
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000/api/v1}"

pp() {
  if command -v jq >/dev/null 2>&1; then jq .; else cat; fi
}

echo "== Health =="
curl -sf "$BASE_URL/health" | pp
echo
echo "== Network status (should show external_connections_detected: false) =="
curl -sf "$BASE_URL/network-status" | pp
echo
echo "== Create conversation =="
CONV=$(curl -sf -X POST "$BASE_URL/conversations")
echo "$CONV" | pp
CONV_ID=$(echo "$CONV" | python3 -c "import sys,json; print(json.load(sys.stdin)['conversation_id'])")
echo "conversation_id=$CONV_ID"
echo
echo "== List knowledge base documents =="
curl -sf "$BASE_URL/knowledge-base" | pp
echo
echo "Smoke test passed. Backend is reachable and the core routes respond."
echo "Next: seed the KB (see api_testing/README.md) and drive real jobs from Thunder Client."
