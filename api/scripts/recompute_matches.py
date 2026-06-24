"""
Recompute match scores with the current engine — no token, no running server.

The feed shows stale ~52% scores until this runs (the old engine defaulted to a
flat 0.5). This re-scores with the rebuilt engine (skill-overlap + title-affinity
+ career-path + saved-job signals), so irrelevant roles drop and real fits rise.

Run from the api/ directory:

    uv run python scripts/recompute_matches.py
"""

from __future__ import annotations

import asyncio

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.matching import MatchingEngine


async def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set in api/.env")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        stats = await MatchingEngine(conn).recompute_all()
        print("✅ Match scores recomputed:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        print("\nOpen the candidate feed — scores now spread by real fit.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
