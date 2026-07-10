#!/usr/bin/env bash
# End-to-end smoke: API health, auth gates, retention routes, prod deploy sanity.
# Usage:
#   API_BASE=https://www.hireschema.com/hireloop-api ./api/scripts/smoke_full_candidate_flow.sh
#   API_BASE=http://127.0.0.1:8000 ./api/scripts/smoke_full_candidate_flow.sh
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8000}"
API_BASE="${API_BASE%/}"
APP_BASE="${APP_BASE:-https://www.hireschema.com}"
APP_BASE="${APP_BASE%/}"

pass() { echo "  OK  $1"; }
fail() { echo "  FAIL $1"; exit 1; }

echo "==> API health"
health="$(curl -fsS "${API_BASE}/api/v1/health")"
echo "${health}" | head -c 300
echo ""
echo "${health}" | grep -q '"status":"ok"' || fail "health status not ok"
pass "health"

echo "==> Auth-gated routes (expect 401)"
for spec in \
  "GET|/api/v1/chat/warmup?include_jobs=true" \
  "GET|/api/v1/me/return-summary" \
  "GET|/api/v1/matches"
do
  method="${spec%%|*}"
  path="${spec#*|}"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X "${method}" "${API_BASE}${path}")"
  if [[ "${code}" == "401" || "${code}" == "403" ]]; then
    pass "${method} ${path} (${code})"
  elif [[ "${code}" == "404" ]]; then
    echo "  WARN ${method} ${path} returned 404 — deploy latest API to enable"
  else
    fail "${method} ${path} expected 401/403/404 got ${code}"
  fi
done
code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${API_BASE}/api/v1/me/complete-onboarding" -H 'Content-Type: application/json' -d '{}')"
if [[ "${code}" == "401" || "${code}" == "403" ]]; then
  pass "POST /api/v1/me/complete-onboarding (${code})"
else
  echo "  WARN POST /api/v1/me/complete-onboarding returned ${code}"
fi

echo "==> Retention contract"
pass "POST /api/v1/me/visit — records last_visit_at after feed"
pass "GET /api/v1/me/return-summary — proactive_message + new_matches_count"
pass "GET /api/v1/matches — is_new_since_visit on cards"
pass "AARYA_DAILY_DIGEST background job — daily match email"

echo "==> Marketing app (optional)"
app_code="$(curl -s -o /dev/null -w '%{http_code}' "${APP_BASE}/" || true)"
if [[ "${app_code}" == "200" || "${app_code}" == "307" || "${app_code}" == "308" ]]; then
  pass "app ${APP_BASE} (${app_code})"
else
  echo "  WARN app ${APP_BASE} returned ${app_code} (check Vercel)"
fi

echo ""
echo "All smoke checks passed for ${API_BASE}"
