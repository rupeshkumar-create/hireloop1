#!/usr/bin/env bash
# Deploy the FastAPI backend to Railway (hireschema-api / hireloop1).
# Must run from monorepo root — the service Root Directory is api/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RAILWAY_PROJECT_ID="12e57bc0-382e-4743-8d49-3f764f166dc2"
RAILWAY_ENVIRONMENT_ID="8bf81d4b-026d-4abe-8d8d-c22162ef783c"
RAILWAY_SERVICE_ID="83b20792-09a5-4a7f-9a67-99374d2cf552"
RAILWAY_DASHBOARD_URL="https://railway.com/project/${RAILWAY_PROJECT_ID}/service/${RAILWAY_SERVICE_ID}?environmentId=${RAILWAY_ENVIRONMENT_ID}"

mkdir -p .railway
cat > .railway/config.json <<EOF
{
  "project": "${RAILWAY_PROJECT_ID}",
  "environment": "${RAILWAY_ENVIRONMENT_ID}",
  "service": "${RAILWAY_SERVICE_ID}"
}
EOF

echo "Deploying hireloop-api → hireloop1 (${RAILWAY_SERVICE_ID})"
echo "Dashboard: ${RAILWAY_DASHBOARD_URL}"
echo

railway link \
  -p "${RAILWAY_PROJECT_ID}" \
  -e "${RAILWAY_ENVIRONMENT_ID}" \
  -s "${RAILWAY_SERVICE_ID}"

railway up --detach

echo
echo "Build started. Track deploy:"
echo "  ${RAILWAY_DASHBOARD_URL}"
echo
echo "After deploy finishes, run: ./api/scripts/smoke_railway.sh"
