#!/usr/bin/env bash
# Smoke-test Firecrawl JD fetch (optional — needs FIRECRAWL_API_KEY in api/.env).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${FIRECRAWL_API_KEY:-}" ]]; then
  echo "SKIP: FIRECRAWL_API_KEY not set"
  exit 0
fi

URL="${1:-https://boards.greenhouse.io/embed/job_app?token=4397024101}"

uv run python - <<'PY'
import asyncio
import os
import sys

from hireloop_api.config import Settings
from hireloop_api.services.firecrawl.jd_fetcher import fetch_full_jd_text


async def main() -> None:
    settings = Settings(firecrawl_api_key=os.environ["FIRECRAWL_API_KEY"], firecrawl_enabled=True)
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SMOKE_URL", "")
    result = await fetch_full_jd_text(url, settings, allow_firecrawl=True)
    text = result.get("text") or ""
    print(f"source={result.get('source')} chars={len(text)}")
    print(text[:500])
    if len(text) < 200:
        raise SystemExit("JD text too short — Firecrawl smoke failed")


asyncio.run(main())
PY

echo "Firecrawl smoke OK"
