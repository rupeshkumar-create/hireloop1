"""
Stale-job expiry sweep (backend plan #27).

Deactivates jobs that are past their expires_at OR were scraped more than
STALE_DAYS ago and never refreshed — keeps the feed honest without waiting for
serve-time filters. Recruiter-posted jobs (scraped_at IS NULL) are exempt from
the staleness rule and only expire via expires_at.

Run:  cd api && uv run python scripts/expire_stale_jobs.py [--dry-run]
Cron: nightly, alongside check_apply_links.py.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

STALE_DAYS = 45


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("DATABASE_URL not set")
        sys.exit(1)

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            f"""
            SELECT id FROM public.jobs
            WHERE is_active = TRUE AND deleted_at IS NULL
              AND (
                    expires_at <= NOW()
                 OR (scraped_at IS NOT NULL
                     AND scraped_at < NOW() - INTERVAL '{STALE_DAYS} days')
              )
            """  # noqa: S608 — STALE_DAYS is a module constant, not user input
        )
        print(f"Stale/expired active jobs: {len(rows)}")
        if rows and not dry_run:
            await conn.execute(
                "UPDATE public.jobs SET is_active = FALSE, updated_at = NOW() "
                "WHERE id = ANY($1::uuid[])",
                [r["id"] for r in rows],
            )
            print(f"Deactivated {len(rows)} jobs.")
        elif rows:
            print("(dry run — nothing changed)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
