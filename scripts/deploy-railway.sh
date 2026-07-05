#!/usr/bin/env bash
# Deploy the FastAPI backend to Railway (truthful-forgiveness / hireloop1).
# Must run from monorepo root — the service Root Directory is api/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Deploying hireloop-api from monorepo root (service root: api/)..."
railway link -p 7f42f8d6-2192-4a15-912e-3d79a1869885 -s hireloop1 -e production
railway up --detach
echo
echo "Build started. Dashboard:"
echo "  https://railway.com/project/7f42f8d6-2192-4a15-912e-3d79a1869885"
echo
echo "After deploy finishes, run: ./api/scripts/smoke_railway.sh"
