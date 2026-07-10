"""
Company web context for personalised intro emails (Nitya).

Scrapes public company pages (never LinkedIn) and caches snippets on ``companies.apify_data``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.firecrawl.client import (
    FirecrawlError,
    client_from_settings,
)
from hireloop_api.services.firecrawl.url_policy import validate_firecrawl_url

logger = structlog.get_logger()

_COMPANY_INTEL_TTL_DAYS = 14
_MAX_SNIPPET_CHARS = 2_500

FIRECRAWL_COMPANY_INTEL = "firecrawl_company_intel"
FIRECRAWL_JD_BACKFILL = "firecrawl_jd_backfill"


def _domain_homepage(domain: str) -> str:
    d = domain.strip().lower()
    if d.startswith("http"):
        return validate_firecrawl_url(d)
    return validate_firecrawl_url(f"https://{d}")


def _guess_company_urls(domain: str | None, company_name: str | None) -> list[str]:
    urls: list[str] = []
    if domain:
        try:
            base = _domain_homepage(domain)
            urls.append(base)
            parsed = urlparse(base)
            root = f"{parsed.scheme}://{parsed.netloc}"
            for path in ("/about", "/about-us", "/company", "/careers", "/jobs"):
                urls.append(f"{root}{path}")
        except ValueError:
            pass
    # De-dupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:5]


def _intel_from_apify_data(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    block = raw.get("firecrawl_intel")
    return block if isinstance(block, dict) else None


def _is_fresh(intel: dict[str, Any]) -> bool:
    fetched = intel.get("fetched_at")
    if not fetched:
        return False
    try:
        ts = datetime.fromisoformat(str(fetched).replace("Z", "+00:00"))
    except ValueError:
        return False
    return ts > datetime.now(UTC) - timedelta(days=_COMPANY_INTEL_TTL_DAYS)


def get_company_intel_snippet(apify_data: Any, *, max_chars: int = 900) -> str:
    """Plain-text snippet for LLM prompts."""
    intel = _intel_from_apify_data(apify_data)
    if not intel:
        return ""
    parts: list[str] = []
    for key in ("about", "careers", "homepage"):
        val = str(intel.get(key) or "").strip()
        if val:
            parts.append(val)
    text = "\n\n".join(parts).strip()
    if len(text) > max_chars:
        return text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


async def fetch_company_intel(
    db: asyncpg.Connection,
    *,
    company_id: str | uuid.UUID,
    settings: Settings,
) -> dict[str, Any] | None:
    """Fetch and persist company intel. Returns stored block or None."""
    row = await db.fetchrow(
        """
        SELECT id, name, domain, apify_data
        FROM public.companies
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(str(company_id)),
    )
    if not row:
        return None

    existing = _intel_from_apify_data(row["apify_data"])
    if existing and _is_fresh(existing):
        return existing

    client = client_from_settings(settings)
    if client is None:
        return existing

    urls = _guess_company_urls(row["domain"], row["name"])
    if not urls:
        await client.close()
        return existing

    snippets: dict[str, str] = {}
    try:
        for url in urls:
            label = "homepage"
            if "/about" in url or "/company" in url:
                label = "about"
            elif "/career" in url or "/jobs" in url:
                label = "careers"
            if label in snippets:
                continue
            try:
                result = await client.scrape_markdown(url)
            except FirecrawlError as exc:
                logger.info("firecrawl_company_page_failed", url=url[:100], error=str(exc)[:120])
                continue
            md = str(result.get("markdown") or "").strip()
            if md:
                snippets[label] = md[:_MAX_SNIPPET_CHARS]
    finally:
        await client.close()

    if not snippets:
        return existing

    block = {
        "fetched_at": datetime.now(UTC).isoformat(),
        "source": "firecrawl",
        **snippets,
    }
    merged = dict(row["apify_data"] or {}) if isinstance(row["apify_data"], dict) else {}
    merged["firecrawl_intel"] = block
    await db.execute(
        """
        UPDATE public.companies
        SET apify_data = $2::jsonb, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        row["id"],
        json.dumps(merged),
    )
    return block


async def enqueue_company_intel_if_needed(
    db: asyncpg.Connection,
    *,
    company_id: str | uuid.UUID | None,
    settings: Settings,
) -> uuid.UUID | None:
    if company_id is None:
        return None
    from hireloop_api.services.background_jobs import enqueue_job
    from hireloop_api.services.firecrawl.client import firecrawl_enabled

    if not firecrawl_enabled(settings):
        return None

    cid = str(company_id)
    return await enqueue_job(
        db,
        kind=FIRECRAWL_COMPANY_INTEL,
        payload={"company_id": cid},
        idempotency_key=f"firecrawl_company:{cid}",
    )
