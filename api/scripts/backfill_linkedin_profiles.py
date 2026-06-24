#!/usr/bin/env python3
"""Backfill Apify LinkedIn profile enrichment for candidates missing apify_profile."""

from __future__ import annotations

import argparse
import asyncio
import sys

from hireloop_api.config import get_settings
from hireloop_api.deps import get_db_pool
from hireloop_api.services.linkedin_enrichment import backfill_linkedin_profiles


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=25, help="Max candidates to process")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List pending user IDs without calling Apify",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds between Apify runs",
    )
    args = parser.parse_args()

    settings = get_settings()
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        result = await backfill_linkedin_profiles(
            conn,
            settings,
            limit=args.limit,
            delay_seconds=args.delay,
            dry_run=args.dry_run,
        )

    print(result)
    if result.get("status") == "skipped":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
