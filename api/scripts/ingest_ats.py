"""
Ingest jobs from Greenhouse + Lever public boards (backend plan #26).

Reads the allowlists from settings (ATS_GREENHOUSE_BOARDS, ATS_LEVER_COMPANIES),
fetches + normalises + India/remote-filters each posting, and upserts through the
shared JobIngester path (dedup, company-link, cross-source apply_url guard).

Run:  cd api && uv run python scripts/ingest_ats.py
Cron: daily, before recompute_matches.py.
"""

from __future__ import annotations

import asyncio

import structlog

from hireloop_api.config import get_settings
from hireloop_api.deps import get_db_pool
from hireloop_api.services.apify.job_ingester import JobIngester
from hireloop_api.services.ats.ats_source import ATSSource

logger = structlog.get_logger()


async def main() -> None:
    settings = get_settings()
    boards = settings.ats_greenhouse_boards
    companies = settings.ats_lever_companies
    if not boards and not companies:
        print(
            "No ATS sources configured. Set ATS_GREENHOUSE_BOARDS and/or "
            "ATS_LEVER_COMPANIES (comma-separated) in api/.env."
        )
        return

    print(f"Fetching ATS feeds: {len(boards)} Greenhouse board(s), {len(companies)} Lever…")
    records = await ATSSource().fetch_all(boards, companies)
    print(f"Normalised + India/remote-eligible: {len(records)} jobs")
    if not records:
        return

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        ingester = JobIngester(apify_token="", db=conn)
        stats = await ingester.ingest_records(records)
    print(f"Done: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
