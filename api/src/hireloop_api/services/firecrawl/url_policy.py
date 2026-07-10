"""URL allow-list for Firecrawl — block private networks and LinkedIn (R16)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from hireloop_api.services.role_jd_fetch import RoleImportError, _validate_public_url

_LINKEDIN_RE = re.compile(r"(^|\.)linkedin\.com$", re.I)


def validate_firecrawl_url(url: str) -> str:
    """Return a normalised public https URL or raise ValueError."""
    try:
        cleaned = _validate_public_url(url)
    except RoleImportError as exc:
        raise ValueError(str(exc)) from exc
    host = (urlparse(cleaned).hostname or "").lower()
    if _LINKEDIN_RE.search(host):
        raise ValueError("LinkedIn URLs cannot be scraped via Firecrawl (use Apify actors).")
    return cleaned


def is_scrapable_job_url(url: str | None) -> bool:
    if not (url or "").strip():
        return False
    try:
        validate_firecrawl_url(url.strip())
    except ValueError:
        return False
    return True
