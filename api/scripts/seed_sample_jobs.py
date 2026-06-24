"""
Seed sample India jobs into the database — no Apify token / network needed.

Lights up the match feed and Aarya's job recommendations end-to-end so you can
test the whole downstream before the live Apify scrape (P09 / S07) is wired.

Run from the `api/` directory:

    uv run python scripts/seed_sample_jobs.py

Then recompute match scores (see HIR-19) and open the candidate feed.
"""

from __future__ import annotations

import asyncio

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.apify.job_ingester import JobIngester


async def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set in api/.env")

    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        ingester = JobIngester(apify_token="", db=conn)
        stats = await ingester.ingest_sample()
        print("✅ Sample jobs seeded:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        print(
            "\nNext: trigger POST /api/v1/matches/recompute (HIR-19), "
            "then open the candidate match feed."
        )
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
