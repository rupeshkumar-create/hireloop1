#!/usr/bin/env bash
# Deploy the FastAPI backend to Railway (truthful-forgiveness / hireloop1).
# Must run from monorepo root — the service Root Directory is api/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RAILWAY_PROJECT_ID="7f42f8d6-2192-4a15-912e-3d79a1869885"
RAILWAY_ENVIRONMENT_ID="38fa0ffc-f032-4ed0-8ef8-1be3e7fee969"
RAILWAY_SERVICE_ID="3e2955b3-628f-4855-8462-ccb93a258dc4"
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
