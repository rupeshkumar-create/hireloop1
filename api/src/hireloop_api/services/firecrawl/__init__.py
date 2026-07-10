"""Firecrawl web context layer — deep-read URLs Apify discovery cannot fill."""

from hireloop_api.services.firecrawl.company_intel import (
    enqueue_company_intel_if_needed,
    fetch_company_intel,
    get_company_intel_snippet,
)
from hireloop_api.services.firecrawl.jd_fetcher import (
    THIN_JD_MIN_CHARS,
    backfill_job_description,
    enrich_job_record_from_url,
)

__all__ = [
    "THIN_JD_MIN_CHARS",
    "backfill_job_description",
    "enqueue_company_intel_if_needed",
    "enrich_job_record_from_url",
    "fetch_company_intel",
    "get_company_intel_snippet",
]
