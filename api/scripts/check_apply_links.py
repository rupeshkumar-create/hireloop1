"""
Dead apply-link checker (backend plan #28).

HEADs the apply_url of every active job; jobs whose link is definitively gone
(404/410) are deactivated so candidates never click into a dead posting.
Conservative on purpose: timeouts, 403s, bot-blocks etc. are NOT treated as dead
(many job boards block HEAD/bots), so a flaky network can't wipe the feed.

Run:  cd api && uv run python scripts/check_apply_links.py [--dry-run]
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
import httpx

DEAD_STATUSES = {404, 410}
CONCURRENCY = 15
TIMEOUT = 10.0


async def check_one(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, job: asyncpg.Record
) -> tuple[str, bool]:
    """Return (job_id, is_dead). Only definitive 404/410 counts as dead."""
    async with sem:
        try:
            res = await client.head(job["apply_url"], follow_redirects=True)
            if res.status_code == 405:  # board doesn't allow HEAD — try GET cheaply
                res = await client.get(
                    job["apply_url"], follow_redirects=True, headers={"Range": "bytes=0-0"}
                )
            return str(job["id"]), res.status_code in DEAD_STATUSES
        except Exception:
            return str(job["id"]), False  # unreachable ≠ dead (conservative)


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        print("DATABASE_URL not set")
        sys.exit(1)

    conn = await asyncpg.connect(dsn)
    try:
        jobs = await conn.fetch(
            """
            SELECT id, apply_url FROM public.jobs
            WHERE is_active = TRUE AND deleted_at IS NULL
              AND apply_url IS NOT NULL AND apply_url <> ''
            """
        )
        print(f"Checking {len(jobs)} active jobs…")

        sem = asyncio.Semaphore(CONCURRENCY)
        async with httpx.AsyncClient(
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; HireschemaLinkCheck/1.0)"},
        ) as client:
            results = await asyncio.gather(*(check_one(client, sem, j) for j in jobs))

        dead = [job_id for job_id, is_dead in results if is_dead]
        print(f"Dead links (404/410): {len(dead)}")

        if dead and not dry_run:
            await conn.execute(
                "UPDATE public.jobs SET is_active = FALSE, updated_at = NOW() "
                "WHERE id = ANY($1::uuid[])",
                dead,
            )
            print(f"Deactivated {len(dead)} jobs.")
        elif dead:
            print("(dry run — nothing changed)")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
