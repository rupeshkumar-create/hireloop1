"""
HM Enrichment service — Apify waterfall for hiring manager contact discovery.

Waterfall (all via Apify actors — no direct LinkedIn scraping):
  Step 1: LinkedIn Company Employees Scraper  → find HM candidates at target company
  Step 2: LinkedIn Profile Scraper            → get full profile (email hints, direct links)
  Step 3: LinkedIn Email Finder               → derive work email from profile data
  Step 4: NeverBounce                         → verify email deliverability

Only step 4 (NeverBounce) calls a non-Apify API.
No LinkedIn cookies are stored or used (R16 §3 compliance).

Called by:
  - Nitya agent `enrich_hiring_manager` tool
  - POST /api/v1/hiring-managers/enrich/{hm_id}   (admin trigger)
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import asyncpg
import httpx
import structlog

logger = structlog.get_logger()

# ── Apify actor IDs ───────────────────────────────────────────────────────────
# These are public no-cookie actors from the Apify Store.
_ACTOR_COMPANY_EMPLOYEES = "2SyF0bVxmgGr8IVCZ"  # LinkedIn Company Employees
_ACTOR_PROFILE_SCRAPER = "2SyF0bVxmgGr8IVCZ"  # LinkedIn Profile Details (same actor, diff input)
_ACTOR_EMAIL_FINDER = "Gt3ebZ0GDsJMkFejr"  # LinkedIn Email Finder

_APIFY_BASE = "https://api.apify.com/v2"
_NEVERBOUNCE_BASE = "https://api.neverbounce.com/v4"
_POLL_INTERVAL = 10  # seconds between run status checks
_TIMEOUT = 300  # max seconds to wait for an actor run


class HMEnricher:
    """
    Enriches a hiring_manager row with verified email + profile data.

    Usage:
        enricher = HMEnricher(apify_token, neverbounce_key, db)
        result = await enricher.enrich(hm_id)
    """

    def __init__(
        self,
        apify_token: str,
        neverbounce_api_key: str,
        db: asyncpg.Connection,
    ) -> None:
        self._apify_token = apify_token
        self._neverbounce_key = neverbounce_api_key
        self._db = db
        self._http = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._http.aclose()

    # ── Top-level entry point ─────────────────────────────────────────────────

    async def enrich(self, hm_id: str) -> dict[str, Any]:
        """
        Full enrichment waterfall for a single hiring_manager.
        Updates the DB row throughout, returns a result summary.
        """
        hm = await self._db.fetchrow(
            "SELECT * FROM public.hiring_managers WHERE id = $1::uuid AND deleted_at IS NULL",
            hm_id,
        )
        if not hm:
            return {"error": "Hiring manager not found"}

        # Mark as in-progress
        await self._set_status(hm_id, "in_progress")

        try:
            enrichment: dict[str, Any] = {}

            # Step 1 — Find HM on LinkedIn via company employees
            if not hm["linkedin_url"]:
                linkedin_url = await self._find_linkedin_url(
                    company_linkedin_url=await self._get_company_linkedin(hm["company_id"]),
                    target_name=hm["full_name"],
                    target_title=hm["title"],
                )
                if linkedin_url:
                    enrichment["linkedin_url"] = linkedin_url
                    await self._db.execute(
                        "UPDATE public.hiring_managers SET linkedin_url = $1, "
                        "updated_at = NOW() WHERE id = $2::uuid",
                        linkedin_url,
                        hm_id,
                    )
            else:
                enrichment["linkedin_url"] = hm["linkedin_url"]

            # Step 2 — Scrape LinkedIn profile
            if enrichment.get("linkedin_url"):
                profile_data = await self._scrape_profile(enrichment["linkedin_url"])
                if profile_data:
                    enrichment["profile"] = profile_data

            # Step 3 — Find work email
            if not hm["email"]:
                email = await self._find_email(
                    linkedin_url=enrichment.get("linkedin_url") or hm.get("linkedin_url"),
                    full_name=hm["full_name"],
                    company_domain=await self._get_company_domain(hm["company_id"]),
                )
                if email:
                    enrichment["email_raw"] = email
            else:
                email = hm["email"]
                enrichment["email_raw"] = email

            # Step 4 — Verify email with NeverBounce
            email_verified = False
            if email:
                email_verified, bounce_result = await self._verify_email(email)
                enrichment["email_verification"] = bounce_result
                if email_verified:
                    await self._db.execute(
                        """
                        UPDATE public.hiring_managers SET
                            email = $1,
                            email_verified = TRUE,
                            updated_at = NOW()
                        WHERE id = $2::uuid
                        """,
                        email,
                        hm_id,
                    )

            # Persist enrichment_data blob
            await self._db.execute(
                """
                UPDATE public.hiring_managers SET
                    enrichment_data = $1::jsonb,
                    enrich_status   = 'done',
                    last_enriched   = NOW(),
                    updated_at      = NOW()
                WHERE id = $2::uuid
                """,
                __import__("json").dumps(enrichment),
                hm_id,
            )

            logger.info(
                "hm_enrichment_done",
                hm_id=hm_id,
                email_found=bool(email),
                email_verified=email_verified,
            )

            return {
                "hm_id": hm_id,
                "email": email if email_verified else None,
                "email_verified": email_verified,
                "linkedin_url": enrichment.get("linkedin_url"),
                "status": "done",
            }

        except Exception as exc:
            logger.error("hm_enrichment_failed", hm_id=hm_id, error=str(exc))
            await self._set_status(hm_id, "failed")
            return {"error": str(exc), "status": "failed"}

    # ── Status helper ─────────────────────────────────────────────────────────

    async def _set_status(self, hm_id: str, status: str) -> None:
        await self._db.execute(
            "UPDATE public.hiring_managers SET enrich_status = $1, "
            "updated_at = NOW() WHERE id = $2::uuid",
            status,
            hm_id,
        )

    # ── DB lookups ────────────────────────────────────────────────────────────

    async def _get_company_linkedin(self, company_id: str | None) -> str | None:
        if not company_id:
            return None
        row = await self._db.fetchrow(
            "SELECT linkedin_url FROM public.companies WHERE id = $1::uuid AND deleted_at IS NULL",
            company_id,
        )
        return row["linkedin_url"] if row else None

    async def _get_company_domain(self, company_id: str | None) -> str | None:
        if not company_id:
            return None
        row = await self._db.fetchrow(
            "SELECT domain FROM public.companies WHERE id = $1::uuid AND deleted_at IS NULL",
            company_id,
        )
        return row["domain"] if row else None

    # ── Apify helpers ─────────────────────────────────────────────────────────

    async def _run_actor(self, actor_id: str, run_input: dict) -> list[dict]:
        """
        Trigger an Apify actor run, wait for completion, return dataset items.
        Returns [] on failure.
        """
        try:
            # Trigger
            trigger_res = await self._http.post(
                f"{_APIFY_BASE}/acts/{actor_id}/runs",
                params={"token": self._apify_token},
                json={"input": run_input},
                timeout=30.0,
            )
            trigger_res.raise_for_status()
            run_id = trigger_res.json()["data"]["id"]

            # Poll
            elapsed = 0
            while elapsed < _TIMEOUT:
                await asyncio.sleep(_POLL_INTERVAL)
                elapsed += _POLL_INTERVAL

                status_res = await self._http.get(
                    f"{_APIFY_BASE}/actor-runs/{run_id}",
                    params={"token": self._apify_token},
                    timeout=30.0,
                )
                status_res.raise_for_status()
                run_data = status_res.json()["data"]
                status = run_data["status"]

                if status == "SUCCEEDED":
                    dataset_id = run_data["defaultDatasetId"]
                    items_res = await self._http.get(
                        f"{_APIFY_BASE}/datasets/{dataset_id}/items",
                        params={"token": self._apify_token, "format": "json"},
                        timeout=60.0,
                    )
                    items_res.raise_for_status()
                    return items_res.json()

                if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
                    logger.warning("apify_actor_failed", actor=actor_id, status=status)
                    return []

            logger.warning("apify_actor_timeout", actor=actor_id, run_id=run_id)
            return []

        except Exception as exc:
            logger.error("apify_run_error", actor=actor_id, error=str(exc))
            return []

    # ── Step 1: Find LinkedIn URL ─────────────────────────────────────────────

    async def _find_linkedin_url(
        self,
        company_linkedin_url: str | None,
        target_name: str,
        target_title: str | None,
    ) -> str | None:
        """
        Use LinkedIn Company Employees actor to find HM's profile URL.
        """
        if not company_linkedin_url:
            return None

        items = await self._run_actor(
            _ACTOR_COMPANY_EMPLOYEES,
            {
                "startUrls": [{"url": company_linkedin_url}],
                "count": 50,
                "scrapeType": "employees",
            },
        )

        # Find the best match by name similarity
        name_lower = target_name.lower()
        title_lower = (target_title or "").lower()

        for item in items:
            item_name = (item.get("fullName") or item.get("name") or "").lower()
            item_title = (item.get("headline") or item.get("title") or "").lower()

            # Simple substring match — good enough for HM discovery
            if _name_matches(name_lower, item_name):
                if not target_title or any(w in item_title for w in title_lower.split()):
                    url = item.get("profileUrl") or item.get("url") or item.get("linkedinUrl")
                    if url and "linkedin.com" in url:
                        return url

        return None

    # ── Step 2: Scrape LinkedIn profile ───────────────────────────────────────

    async def _scrape_profile(self, linkedin_url: str) -> dict[str, Any] | None:
        """
        Scrape a LinkedIn profile via Apify.
        Returns structured profile data or None on failure.
        """
        items = await self._run_actor(
            _ACTOR_PROFILE_SCRAPER,
            {
                "startUrls": [{"url": linkedin_url}],
                "scrapeType": "profile",
            },
        )

        if not items:
            return None

        raw = items[0]
        return {
            "full_name": raw.get("fullName"),
            "headline": raw.get("headline"),
            "location": raw.get("location"),
            "summary": raw.get("summary"),
            "current_company": raw.get("currentCompany"),
            "current_title": raw.get("currentTitle") or raw.get("headline"),
            "email_hints": _extract_email_hints(raw),
        }

    # ── Step 3: Find work email ───────────────────────────────────────────────

    async def _find_email(
        self,
        linkedin_url: str | None,
        full_name: str,
        company_domain: str | None,
    ) -> str | None:
        """
        Attempt email discovery via Apify Email Finder actor.
        Falls back to pattern-guessing if actor returns nothing.
        """
        if linkedin_url:
            items = await self._run_actor(
                _ACTOR_EMAIL_FINDER,
                {
                    "profileUrls": [linkedin_url],
                    "companyDomain": company_domain or "",
                },
            )
            for item in items:
                email = item.get("email")
                if email and _looks_like_email(email):
                    return email

        # Fallback — pattern guess from name + domain
        if company_domain and full_name:
            guessed = _guess_email(full_name, company_domain)
            if guessed:
                return guessed

        return None

    # ── Step 4: NeverBounce verification ─────────────────────────────────────

    async def _verify_email(self, email: str) -> tuple[bool, dict]:
        """
        Verify email deliverability via NeverBounce single-check API.
        Returns (is_valid, raw_result_dict).
        """
        if not self._neverbounce_key:
            # No API key — do not treat unverified emails as deliverable.
            return False, {"status": "skipped", "note": "NeverBounce key not configured"}

        try:
            res = await self._http.get(
                f"{_NEVERBOUNCE_BASE}/single/check",
                params={
                    "key": self._neverbounce_key,
                    "email": email,
                    "credits_info": 0,
                    "timeout": 10,
                },
                timeout=20.0,
            )
            res.raise_for_status()
            data = res.json()
            result_code = data.get("result", "unknown")

            # NeverBounce result codes: valid, invalid, disposable, catchall, unknown
            is_valid = result_code in {"valid", "catchall"}
            return is_valid, {"result": result_code, "flags": data.get("flags", [])}

        except Exception as exc:
            logger.warning("neverbounce_check_failed", email=email, error=str(exc))
            # Treat as unverified but don't block the pipeline
            return False, {"error": str(exc)}


# ── Pure helpers ──────────────────────────────────────────────────────────────


def _name_matches(needle: str, haystack: str) -> bool:
    """True if needle appears as a substring or if first+last both appear."""
    if needle in haystack:
        return True
    parts = needle.split()
    if len(parts) >= 2:
        return parts[0] in haystack and parts[-1] in haystack
    return False


_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _looks_like_email(s: str) -> bool:
    return bool(_EMAIL_RE.fullmatch(s.strip()))


def _extract_email_hints(profile: dict) -> list[str]:
    """Extract any email addresses mentioned in raw profile data."""
    text = str(profile)
    return _EMAIL_RE.findall(text)


_COMMON_PATTERNS = [
    "{first}.{last}",
    "{first}{last}",
    "{f}{last}",
    "{first}",
]


def _guess_email(full_name: str, domain: str) -> str | None:
    """Generate the most common work email pattern from name + domain."""
    parts = full_name.lower().split()
    if not parts:
        return None
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""

    if not last:
        return f"{first}@{domain}"

    # Use the first pattern: first.last@domain
    return f"{first}.{last}@{domain}"
