"""Live job visibility SQL — expiry + stale scrape cutoff for candidate surfaces."""

from __future__ import annotations

from hireloop_api.routes import matches
from hireloop_api.services.job_visibility import (
    LIVE_JOB_VISIBLE_SQL,
    STALE_SCRAPE_DAYS,
    live_job_visible_sql,
)


def test_live_job_visible_sql_includes_expiry_and_45d_scrape_freshness() -> None:
    assert STALE_SCRAPE_DAYS == 45
    sql = LIVE_JOB_VISIBLE_SQL
    assert "expires_at" in sql
    assert "scraped_at" in sql
    assert "45 days" in sql
    assert matches._LIVE_JOB_VISIBLE_SQL == LIVE_JOB_VISIBLE_SQL


def test_live_job_visible_sql_supports_job_alias() -> None:
    sql = live_job_visible_sql(job_alias="jobs")
    assert "jobs.expires_at" in sql
    assert "jobs.scraped_at" in sql
    assert "j.expires_at" not in sql
