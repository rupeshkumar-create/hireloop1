#!/usr/bin/env bash
# Migrate hireloop-api to a new Railway account/project.
# Prereq: `railway login` with the NEW Pro account, then run from repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BACKUP="${ROOT}/.railway/migration-env.json"
if [[ ! -f "$BACKUP" ]]; then
  echo "Missing $BACKUP — export vars from old project first:"
  echo "  railway variable list --json > .railway/migration-backup.json"
  exit 1
fi

echo "=== Railway account ==="
railway whoami

echo
echo "=== Create / link project (hireschema-api) ==="
if ! railway status >/dev/null 2>&1; then
  railway init -n hireschema-api
fi

echo
echo "=== Push env vars from backup (skip RAILWAY_*) ==="
python3 <<'PY'
import json
import subprocess
from pathlib import Path

data = json.loads(Path(".railway/migration-env.json").read_text())
for key, value in sorted(data.items()):
    if key.startswith("RAILWAY_"):
        continue
    print(f"  set {key}")
    subprocess.run(
        ["railway", "variable", "set", f"{key}={value}", "--skip-deploys"],
        check=True,
    )
print(f"Set {len(data)} variables.")
PY

echo
echo "=== Deploy API (Dockerfile in api/) ==="
cd "$ROOT/api"
railway up --detach

echo
echo "=== New service URL ==="
cd "$ROOT"
railway status
NEW_URL=$(railway status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('service',{}).get('url',''))" 2>/dev/null || true)
if [[ -n "$NEW_URL" ]]; then
  echo "Health: curl -sS ${NEW_URL}/api/v1/health"
  echo
  echo "Update Vercel:"
  echo "  vercel env add NEXT_PUBLIC_API_URL production"
  echo "  (value: ${NEW_URL})"
fi

echo
echo "Done. Update scripts/deploy-railway.sh IDs from: railway status --json"
