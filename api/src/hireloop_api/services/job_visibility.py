"""
SQL fragments for jobs that are safe to show on live candidate surfaces.

History intentionally keeps expired/inactive rows; live feed, Aarya search,
and scoring pools must use these filters.
"""

from __future__ import annotations

# Align with api/scripts/expire_stale_jobs.py STALE_DAYS.
STALE_SCRAPE_DAYS = 45


def live_job_visible_sql(*, job_alias: str = "j") -> str:
    """Not expired, and scraped within freshness window (or recruiter / no scrape)."""
    return (
        f"({job_alias}.expires_at IS NULL OR {job_alias}.expires_at > NOW()) "
        f"AND ({job_alias}.scraped_at IS NULL "
        f"OR {job_alias}.scraped_at > NOW() - INTERVAL '{STALE_SCRAPE_DAYS} days')"
    )


# Common alias `j` — used by feed / Aarya / lexical / vector SQL.
LIVE_JOB_VISIBLE_SQL = live_job_visible_sql()

# Expiry-only fragment (kept for callers that compose filters themselves).
ACTIVE_JOB_EXPIRY_SQL = "(j.expires_at IS NULL OR j.expires_at > NOW())"
LIVE_JOB_FRESHNESS_SQL = (
    f"(j.scraped_at IS NULL OR j.scraped_at > NOW() - INTERVAL '{STALE_SCRAPE_DAYS} days')"
)
