#!/usr/bin/env bash
# Smoke-test the production Railway API (truthful-forgiveness / hireloop1).
# Service: https://railway.com/project/12e57bc0-382e-4743-8d49-3f764f166dc2/service/83b20792-09a5-4a7f-9a67-99374d2cf552?environmentId=8bf81d4b-026d-4abe-8d8d-c22162ef783c
# Usage: ./scripts/smoke_railway.sh [RAILWAY_URL] [VERCEL_APP_URL]
set -euo pipefail

RAILWAY_HOST="${RAILWAY_HOST:-hireloop1-production-b8f8.up.railway.app}"
RAILWAY_URL="${1:-https://${RAILWAY_HOST}}"
VERCEL_URL="${2:-https://www.hireschema.com}"

pass() { echo "  OK  $1"; }
fail() { echo "  FAIL $1"; exit 1; }

railway_curl() {
  local path="$1"
  if curl -fsS --max-time 15 "${RAILWAY_URL}${path}" 2>/dev/null; then
    return 0
  fi
  local ip
  ip=$(dig +short "@8.8.8.8" "${RAILWAY_HOST}" 2>/dev/null | head -1)
  if [[ -n "$ip" ]]; then
    curl -fsS --max-time 15 --resolve "${RAILWAY_HOST}:443:${ip}" "https://${RAILWAY_HOST}${path}"
    return $?
  fi
  return 1
}

echo "Railway API smoke test"
echo "  Railway: ${RAILWAY_URL}"
echo "  Vercel proxy: ${VERCEL_URL}/hireloop-api"
echo

body=$(railway_curl "/api/v1/health") || fail "Railway /api/v1/health unreachable"
echo "$body" | grep -q '"status":"ok"' || fail "Railway health body"
echo "$body" | grep -q '"environment":"production"' || fail "Railway not in production"
pass "Railway GET /api/v1/health"

# Vercel proxy health
body=$(curl -fsS "${VERCEL_URL}/hireloop-api/api/v1/health") || fail "Vercel proxy health unreachable"
echo "$body" | grep -q '"status":"ok"' || fail "Vercel proxy health body"
pass "Vercel GET /hireloop-api/api/v1/health"

# Auth endpoints require token
code=$(curl -sS -o /dev/null -w "%{http_code}" "${VERCEL_URL}/hireloop-api/api/v1/auth/me")
[[ "$code" == "401" ]] || fail "auth/me should 401 without token (got ${code})"
pass "auth/me returns 401 without token"

code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
  "${VERCEL_URL}/hireloop-api/api/v1/auth/bootstrap" \
  -H "Content-Type: application/json" \
  -d '{"role":"candidate"}')
[[ "$code" == "401" ]] || fail "auth/bootstrap should 401 without token (got ${code})"
pass "auth/bootstrap returns 401 without token"

echo
echo "All smoke checks passed."
