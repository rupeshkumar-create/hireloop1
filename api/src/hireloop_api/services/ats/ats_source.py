"""
ATS feed ingestion (backend plan #26) — Greenhouse + Lever public job boards.

Why: these are FREE, first-party feeds straight from company career pages with
real, verified apply URLs — higher trust than scraped listings and no Apify
spend. We pull them first; Apify stays as backfill.

India-first + remote-region eligibility (borrowed idea #2): ATS boards are
global, so each posting is filtered to keep only India-located roles OR genuinely
global-remote ones, dropping geo-restricted remotes ("Remote - US only") that an
India-based candidate can't take.

Normalised output reuses `JobRecord` and is persisted via
`JobIngester.ingest_records`, so dedup, company-linking, and the cross-source
apply_url guard are shared with the scraper path.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from hireloop_api.services.apify.jobs_scraper import JobRecord

logger = structlog.get_logger()

_GREENHOUSE_BOARD = "https://boards-api.greenhouse.io/v1/boards/{token}"
_LEVER_POSTINGS = "https://api.lever.co/v0/postings/{company}?mode=json"

# India signals in a free-text location string.
_INDIA_TOKENS = (
    "india",
    "bengaluru",
    "bangalore",
    "mumbai",
    "delhi",
    "new delhi",
    "gurgaon",
    "gurugram",
    "noida",
    "hyderabad",
    "pune",
    "chennai",
    "kolkata",
    "ahmedabad",
    "remote - india",
    "remote, india",
)

# Geo-restricted remote phrasing that excludes an India-based candidate.
_NON_INDIA_REMOTE = (
    "us only",
    "u.s. only",
    "united states only",
    "us-based",
    "usa only",
    "north america only",
    "eu only",
    "emea only",
    "uk only",
    "united kingdom only",
    "canada only",
    "us remote",
    "remote (us",
    "remote - us",
    "remote, us",
    "authorized to work in the united states",
)

_REMOTE_TOKENS = ("remote", "anywhere", "work from home", "wfh", "distributed")
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str | None) -> str | None:
    if not text:
        return None
    out = html.unescape(_TAG_RE.sub(" ", text))
    out = re.sub(r"\s+", " ", out).strip()
    return out or None


def assess_location(location: str | None, text: str | None) -> tuple[bool, bool]:
    """
    Decide whether a posting is eligible for an India-based candidate.

    Returns (keep, is_remote). Keep when the role is in India, or remote and not
    restricted to a non-India region. The remote-region check is the borrowed
    eligibility filter — it reads BOTH the location and the description, since
    "US-only" often hides in the body.
    """
    loc = (location or "").lower()
    body = (text or "").lower()
    haystack = f"{loc} {body}"

    is_remote = any(t in loc for t in _REMOTE_TOKENS)

    if any(t in loc for t in _INDIA_TOKENS):
        return True, is_remote
    if is_remote and not any(p in haystack for p in _NON_INDIA_REMOTE):
        # Global-remote with no geo restriction → an India candidate can take it.
        return True, True
    return False, is_remote


def _india_city(location: str | None) -> str | None:
    loc = (location or "").lower()
    for tok in _INDIA_TOKENS:
        if tok in loc and tok not in ("india", "remote - india", "remote, india"):
            return tok.title()
    return None


def parse_greenhouse(payload: dict, *, token: str, company_name: str) -> list[JobRecord]:
    """Normalise a Greenhouse `/jobs?content=true` payload into JobRecords."""
    records: list[JobRecord] = []
    for job in payload.get("jobs", []):
        title = (job.get("title") or "").strip()
        if not title:
            continue
        location = (job.get("location") or {}).get("name")
        description = _clean_html(job.get("content"))
        keep, is_remote = assess_location(location, description)
        if not keep:
            continue
        records.append(
            JobRecord(
                apify_job_id=f"greenhouse:{token}:{job.get('id')}",
                title=title,
                description=description,
                company_name=company_name,
                location_city=_india_city(location),
                is_remote=is_remote,
                apply_url=job.get("absolute_url"),
                source="greenhouse",
                expires_at=datetime.now(UTC) + timedelta(days=30),
                raw_data={"location": location, "updated_at": job.get("updated_at")},
            )
        )
    return records


def parse_lever(payload: list, *, company: str) -> list[JobRecord]:
    """Normalise a Lever `/postings?mode=json` payload into JobRecords."""
    records: list[JobRecord] = []
    company_name = company.replace("-", " ").title()
    for job in payload:
        title = (job.get("text") or "").strip()
        if not title:
            continue
        cats = job.get("categories") or {}
        location = cats.get("location")
        workplace = (job.get("workplaceType") or "").lower()
        description = _clean_html(job.get("descriptionPlain") or job.get("description"))
        keep, is_remote = assess_location(location, description)
        if workplace == "remote":
            is_remote = True
        if not keep:
            continue
        records.append(
            JobRecord(
                apify_job_id=f"lever:{company}:{job.get('id')}",
                title=title,
                description=description,
                company_name=company_name,
                location_city=_india_city(location),
                is_remote=is_remote,
                apply_url=job.get("hostedUrl") or job.get("applyUrl"),
                source="lever",
                expires_at=datetime.now(UTC) + timedelta(days=30),
                raw_data={"location": location, "team": cats.get("team")},
            )
        )
    return records


class ATSSource:
    """Fetches Greenhouse + Lever public boards and returns normalised JobRecords."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def fetch_all(
        self, greenhouse_tokens: list[str], lever_companies: list[str]
    ) -> list[JobRecord]:
        records: list[JobRecord] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for token in greenhouse_tokens:
                records.extend(await self._fetch_greenhouse(client, token))
            for company in lever_companies:
                records.extend(await self._fetch_lever(client, company))
        logger.info(
            "ats_fetch_done",
            greenhouse=len(greenhouse_tokens),
            lever=len(lever_companies),
            records=len(records),
        )
        return records

    async def _fetch_greenhouse(self, client: httpx.AsyncClient, token: str) -> list[JobRecord]:
        try:
            meta = await client.get(_GREENHOUSE_BOARD.format(token=token))
            company_name = meta.json().get("name", token) if meta.is_success else token
            res = await client.get(
                f"{_GREENHOUSE_BOARD.format(token=token)}/jobs", params={"content": "true"}
            )
            if not res.is_success:
                logger.warning("greenhouse_fetch_failed", token=token, status=res.status_code)
                return []
            return parse_greenhouse(res.json(), token=token, company_name=company_name)
        except Exception as exc:
            logger.warning("greenhouse_fetch_error", token=token, error=str(exc)[:200])
            return []

    async def _fetch_lever(self, client: httpx.AsyncClient, company: str) -> list[JobRecord]:
        try:
            res = await client.get(_LEVER_POSTINGS.format(company=company))
            if not res.is_success:
                logger.warning("lever_fetch_failed", company=company, status=res.status_code)
                return []
            return parse_lever(res.json(), company=company)
        except Exception as exc:
            logger.warning("lever_fetch_error", company=company, error=str(exc)[:200])
            return []
