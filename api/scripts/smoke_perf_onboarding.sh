#!/usr/bin/env bash
# Smoke test: north-star perf path (health, warmup jobs, instant shelf contract).
# Usage: API_BASE=https://www.hireschema.com/hireloop-api ./api/scripts/smoke_perf_onboarding.sh
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
API_BASE="${API_BASE%/}"

echo "==> Health"
curl -fsS "${API_BASE}/api/v1/health" | head -c 200
echo ""

echo "==> Chat warmup contract (include_jobs query param)"
# Unauthenticated warmup should 401 — confirms route exists
code="$(curl -s -o /dev/null -w '%{http_code}' "${API_BASE}/api/v1/chat/warmup?include_jobs=true")"
if [[ "${code}" != "401" && "${code}" != "403" ]]; then
  echo "Expected 401/403 for unauthenticated warmup, got ${code}"
  exit 1
fi
echo "warmup auth gate OK (${code})"

echo "==> Complete-onboarding response shape (docs only)"
echo "POST /api/v1/me/complete-onboarding returns starter_jobs[] when authenticated."

echo "OK — perf smoke checks passed"
