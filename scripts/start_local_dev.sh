#!/usr/bin/env bash
# Install deps, seed demo users, and start API + app for manual QA.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Killing stale dev servers on :8000 and :3001"
for port in 8000 3001; do
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
    echo "    freed port $port"
  fi
done

echo "==> Installing JS dependencies"
if command -v pnpm >/dev/null 2>&1; then
  corepack enable 2>/dev/null || true
  pnpm install
else
  echo "    pnpm not found — using npm in app/"
  (cd "$ROOT/app" && npm install --ignore-scripts 2>/dev/null || true)
fi

echo "==> Ensuring Python venv + API deps"
if [ ! -d "$ROOT/api/.venv" ]; then
  python3 -m venv "$ROOT/api/.venv"
fi
"$ROOT/api/.venv/bin/pip" install -q -e "$ROOT/api[dev]"

echo "==> Seeding demo test users (dev/staging only)"
"$ROOT/api/.venv/bin/python" "$ROOT/api/scripts/seed_test_users.py" || true

echo "==> Smoke checks"
curl -sf "http://127.0.0.1:8000/api/v1/health" >/dev/null 2>&1 || API_NEEDED=1
if [ "${API_NEEDED:-0}" = "1" ]; then
  echo "    API not up yet (will start below)"
fi

echo "==> Starting API on http://127.0.0.1:8000"
cd "$ROOT/api"
nohup .venv/bin/uvicorn hireloop_api.main:app --reload --host 127.0.0.1 --port 8000 \
  >"$ROOT/.local-dev-api.log" 2>&1 &
echo $! >"$ROOT/.local-dev-api.pid"

echo "==> Starting app on http://127.0.0.1:3001"
cd "$ROOT/app"
nohup npm run dev:clean >"$ROOT/.local-dev-app.log" 2>&1 &
echo $! >"$ROOT/.local-dev-app.pid"

echo "==> Waiting for services"
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/api/v1/health" >/dev/null && \
     curl -sf "http://127.0.0.1:3001/" >/dev/null; then
    break
  fi
  sleep 1
done

echo ""
echo "Ready for manual testing:"
echo "  App:  http://localhost:3001"
echo "  API:  http://localhost:8000/api/v1/health"
echo ""
echo "Demo sign-in (dev email login):"
echo "  priya.candidate@hireschema.com / DemoCandidate26!"
echo "  arun.recruiter@hireschema.com  / DemoRecruiter26!"
echo ""
echo "Logs: .local-dev-api.log  .local-dev-app.log"
echo "Stop: kill \$(cat .local-dev-api.pid .local-dev-app.pid)"
