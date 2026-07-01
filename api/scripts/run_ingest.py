"""
Manually trigger a REAL Apify job ingestion (P09 / S07) — cost-controlled.

⚠️ This spends Apify credits (you're on the FREE plan). Defaults are deliberately
tiny. Start with --dry-run (scrapes + normalises, prints, NO DB write).

From the api/ directory:

    # smallest possible validation — no DB write:
    uv run python scripts/run_ingest.py --dry-run --max 3

    # full run that upserts into the DB:
    uv run python scripts/run_ingest.py --max 10 --locations "Bengaluru,Mumbai"

Flags:
    --dry-run            scrape + normalise + print only; never touches the DB
    --max N              max results per query x location (default 5)
    --queries "a,b"      comma-separated search queries (default "backend engineer")
    --locations "a,b"    comma-separated India cities (default "Bengaluru")
    --time-range         24h | 7d | 30d (default 7d)
    --source             linkedin | fantastic | both   (default both)
"""

from __future__ import annotations

import argparse
import asyncio
import json

import asyncpg

from hireloop_api.config import get_settings
from hireloop_api.services.apify.job_ingester import JobIngester
from hireloop_api.services.apify.jobs_scraper import ApifyJobsScraper


async def _dry_run(settings, queries, locations, max_results, time_range) -> None:
    scraper = ApifyJobsScraper(settings.apify_token, actor=settings.apify_linkedin_jobs_actor)
    raw, records, stats = await scraper.scrape(
        queries=queries,
        locations=locations,
        max_results_per_query=max_results,
        time_range=time_range,
    )
    print("scrape stats:", json.dumps(stats, default=str))
    print(f"raw items: {len(raw)} | normalised India records: {len(records)}")
    for r in records[:8]:
        print(
            f"  - {r.title} @ {r.company_name or '?'} | "
            f"{r.location_city or '?'} | {r.seniority or '?'} | "
            f"skills={r.skills_required[:6]} | {r.apify_job_id}"
        )


async def _live_run(settings, queries, locations, max_results, time_range, source) -> None:
    use_career_site = source in ("fantastic", "both")
    use_linkedin = source in ("linkedin", "both")
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        ingester = JobIngester(
            settings.apify_token,
            conn,
            linkedin_actor=settings.apify_linkedin_jobs_actor,
            career_site_actor=settings.apify_career_site_actor,
            enable_career_site=use_career_site,
        )
        stats = await ingester.ingest(
            queries=queries,
            locations=locations,
            max_results_per_query=max_results,
            time_range=time_range,
            use_career_site=use_career_site,
            use_linkedin=use_linkedin,
        )
        print("ingest stats:", json.dumps(stats, default=str, indent=2))
    finally:
        await conn.close()


async def _candidate_run(settings, candidate, max_results, time_range, source) -> None:
    """Scrape scoped to ONE candidate's career-path target roles."""
    use_career_site = source in ("fantastic", "both")
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn)
    try:
        cand_id = candidate
        if "@" in candidate:  # resolve email → candidate id
            row = await conn.fetchrow(
                "SELECT c.id FROM public.candidates c "
                "JOIN public.users u ON u.id = c.user_id "
                "WHERE u.email = $1 AND c.deleted_at IS NULL",
                candidate,
            )
            if not row:
                raise SystemExit(f"No candidate found for email {candidate}")
            cand_id = str(row["id"])
        ingester = JobIngester(
            settings.apify_token,
            conn,
            linkedin_actor=settings.apify_linkedin_jobs_actor,
            career_site_actor=settings.apify_career_site_actor,
            enable_career_site=use_career_site,
        )
        stats = await ingester.ingest_for_candidate(
            cand_id, max_results_per_query=max_results, time_range=time_range
        )
        print("candidate ingest stats:", json.dumps(stats, default=str, indent=2))
    finally:
        await conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a real Apify job ingestion (cost-controlled).")
    ap.add_argument("--dry-run", action="store_true", help="scrape+normalise only, no DB write")
    ap.add_argument("--max", type=int, default=5, help="max results per query x location")
    ap.add_argument("--queries", default="backend engineer")
    ap.add_argument("--locations", default="Bengaluru")
    ap.add_argument("--time-range", default="7d")
    ap.add_argument("--source", choices=["linkedin", "fantastic", "both"], default="both")
    ap.add_argument(
        "--candidate",
        help="candidate id or email — scrape jobs scoped to THEIR career-path target roles",
    )
    args = ap.parse_args()

    settings = get_settings()
    if not settings.apify_token:
        raise SystemExit("APIFY_TOKEN not set in api/.env")

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    locations = [loc.strip() for loc in args.locations.split(",") if loc.strip()]

    try:
        if args.candidate:
            asyncio.run(
                _candidate_run(settings, args.candidate, args.max, args.time_range, args.source)
            )
        elif args.dry_run:
            asyncio.run(_dry_run(settings, queries, locations, args.max, args.time_range))
        else:
            asyncio.run(
                _live_run(settings, queries, locations, args.max, args.time_range, args.source)
            )
    except Exception as exc:  # surface Apify rental/credit errors clearly
        print(f"❌ Ingestion failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
