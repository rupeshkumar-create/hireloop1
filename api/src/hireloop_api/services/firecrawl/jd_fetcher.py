"""
Job description backfill from public apply URLs.

Pipeline:
  1. Free path: ``fetch_role_from_url`` (Greenhouse/Lever API + JSON-LD + httpx HTML)
  2. Firecrawl path: markdown scrape when still thin and API key is configured
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.apify.jobs_scraper import JobRecord
from hireloop_api.services.firecrawl.client import (
    FirecrawlClient,
    FirecrawlError,
    client_from_settings,
)
from hireloop_api.services.firecrawl.url_policy import is_scrapable_job_url
from hireloop_api.services.role_jd_fetch import RoleImportError, fetch_role_from_url

logger = structlog.get_logger()

THIN_JD_MIN_CHARS = 400
_MAX_MARKDOWN_CHARS = 12_000
_JD_CACHE_TTL_HOURS = 72


def _description_len(text: str | None) -> int:
    return len((text or "").strip())


def is_thin_description(text: str | None) -> bool:
    return _description_len(text) < THIN_JD_MIN_CHARS


def _cache_key(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


async def _read_url_cache(db: asyncpg.Connection, url: str) -> str | None:
    try:
        row = await db.fetchrow(
            """
            SELECT markdown FROM public.firecrawl_url_cache
            WHERE url_hash = $1 AND expires_at > NOW()
            """,
            _cache_key(url),
        )
    except Exception:
        return None
    if not row:
        return None
    text = str(row["markdown"] or "").strip()
    return text or None


async def _write_url_cache(db: asyncpg.Connection, url: str, markdown: str) -> None:
    expires = datetime.now(UTC) + timedelta(hours=_JD_CACHE_TTL_HOURS)
    try:
        await db.execute(
            """
            INSERT INTO public.firecrawl_url_cache (url_hash, url, kind, markdown, fetched_at, expires_at)
            VALUES ($1, $2, 'jd', $3, NOW(), $4)
            ON CONFLICT (url_hash) DO UPDATE SET
              markdown = EXCLUDED.markdown,
              fetched_at = NOW(),
              expires_at = EXCLUDED.expires_at
            """,
            _cache_key(url),
            url.strip(),
            markdown[:_MAX_MARKDOWN_CHARS],
            expires,
        )
    except Exception as exc:
        logger.debug("firecrawl_cache_write_skipped", error=str(exc)[:120])


async def _fetch_via_free_path(url: str) -> str | None:
    try:
        payload = await fetch_role_from_url(url)
    except RoleImportError as exc:
        logger.info("jd_free_fetch_failed", url=url[:120], error=str(exc)[:120])
        return None
    text = str(payload.get("jd_text") or "").strip()
    return text if len(text) >= THIN_JD_MIN_CHARS else text or None


async def _fetch_via_firecrawl(
    client: FirecrawlClient,
    url: str,
    *,
    db: asyncpg.Connection | None = None,
) -> str | None:
    if db is not None:
        cached = await _read_url_cache(db, url)
        if cached and len(cached) >= THIN_JD_MIN_CHARS:
            return cached

    try:
        result = await client.scrape_markdown(url)
    except FirecrawlError as exc:
        logger.warning("firecrawl_jd_scrape_failed", url=url[:120], error=str(exc)[:200])
        return None

    markdown = str(result.get("markdown") or "").strip()
    if not markdown:
        return None
    if len(markdown) > _MAX_MARKDOWN_CHARS:
        markdown = markdown[:_MAX_MARKDOWN_CHARS].rsplit(" ", 1)[0] + "…"

    if db is not None and len(markdown) >= THIN_JD_MIN_CHARS:
        try:
            await _write_url_cache(db, url, markdown)
        except Exception as exc:
            logger.debug("firecrawl_cache_write_skipped", error=str(exc)[:120])

    return markdown


async def fetch_full_jd_text(
    url: str,
    settings: Settings,
    *,
    db: asyncpg.Connection | None = None,
    prefer_firecrawl: bool = False,
    allow_firecrawl: bool = True,
) -> dict[str, Any]:
    """
    Resolve a job posting URL to full text.

    Returns ``{"text": str|None, "source": "cache"|"free"|"firecrawl"|None}``.
    """
    if not is_scrapable_job_url(url):
        return {"text": None, "source": None}

    if db is not None:
        cached = await _read_url_cache(db, url)
        if cached and len(cached) >= THIN_JD_MIN_CHARS:
            return {"text": cached, "source": "cache"}

    free_text: str | None = None
    if not prefer_firecrawl:
        free_text = await _fetch_via_free_path(url)
        if free_text and len(free_text) >= THIN_JD_MIN_CHARS:
            if db is not None:
                try:
                    await _write_url_cache(db, url, free_text)
                except Exception as exc:
                    logger.debug("firecrawl_cache_write_skipped", error=str(exc)[:120])
            return {"text": free_text, "source": "free"}

    client = client_from_settings(settings)
    if client is None or not allow_firecrawl:
        if free_text:
            return {"text": free_text, "source": "free"}
        return {"text": None, "source": None}

    try:
        fc_text = await _fetch_via_firecrawl(client, url, db=db)
    finally:
        await client.close()

    if fc_text and len(fc_text) >= THIN_JD_MIN_CHARS:
        return {"text": fc_text, "source": "firecrawl"}

    if free_text:
        return {"text": free_text, "source": "free"}
    return {"text": fc_text, "source": "firecrawl" if fc_text else None}


async def enrich_job_record_from_url(
    rec: JobRecord,
    settings: Settings,
    *,
    db: asyncpg.Connection | None = None,
    allow_firecrawl: bool = True,
) -> bool:
    """Backfill ``rec.description`` from ``rec.apply_url`` when thin. Returns True if updated."""
    if not is_thin_description(rec.description):
        return False
    if not is_scrapable_job_url(rec.apply_url):
        return False

    result = await fetch_full_jd_text(
        rec.apply_url or "",
        settings,
        db=db,
        allow_firecrawl=allow_firecrawl,
    )
    text = result.get("text")
    if not text or not isinstance(text, str):
        return False

    rec.description = text
    if isinstance(rec.raw_data, dict):
        rec.raw_data["jd_backfill"] = {
            "source": result.get("source"),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
    else:
        rec.raw_data = {
            "jd_backfill": {
                "source": result.get("source"),
                "fetched_at": datetime.now(UTC).isoformat(),
            }
        }
    return True


async def _enqueue_jd_backfill_job(
    db: asyncpg.Connection,
    *,
    job_id: str,
    settings: Settings,
) -> None:
    from hireloop_api.services.background_jobs import enqueue_job
    from hireloop_api.services.firecrawl.client import firecrawl_enabled

    if not firecrawl_enabled(settings):
        return
    from hireloop_api.services.firecrawl.company_intel import FIRECRAWL_JD_BACKFILL

    try:
        await enqueue_job(
            db,
            kind=FIRECRAWL_JD_BACKFILL,
            payload={"job_id": job_id},
            idempotency_key=f"firecrawl_jd:{job_id}",
        )
    except Exception as exc:
        logger.debug("firecrawl_jd_enqueue_skipped", job_id=job_id, error=str(exc)[:120])


async def run_jd_backfill_for_job(
    db: asyncpg.Connection,
    *,
    job_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Background handler: Firecrawl backfill + optional JD enrichment."""
    row = await db.fetchrow(
        """
        SELECT id, title, description, apply_url, skills_required, seniority, ctc_min, ctc_max
        FROM public.jobs
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(job_id),
    )
    if not row:
        return {"ok": False, "reason": "not_found"}

    job = dict(row)
    job["id"] = str(job["id"])
    before = _description_len(job.get("description"))
    await backfill_job_description(db, job, settings, persist=True)
    after = _description_len(job.get("description"))

    enriched = False
    if after >= THIN_JD_MIN_CHARS and (not job.get("skills_required") or len(job["skills_required"]) < 2):
        from hireloop_api.services.jd_enrichment import enrich_job_description

        payload = await enrich_job_description(
            str(job.get("title") or ""),
            str(job.get("description") or ""),
            settings,
        )
        if payload:
            skills = payload.get("skills_required") or []
            await db.execute(
                """
                UPDATE public.jobs SET
                  skills_required = CASE WHEN cardinality(skills_required) < 2
                    THEN $2::text[] ELSE skills_required END,
                  seniority = COALESCE(seniority, $3),
                  ctc_min = COALESCE(ctc_min, $4),
                  ctc_max = COALESCE(ctc_max, $5),
                  updated_at = NOW()
                WHERE id = $1::uuid
                """,
                job["id"],
                skills,
                payload.get("seniority"),
                payload.get("ctc_min"),
                payload.get("ctc_max"),
            )
            enriched = bool(skills or payload.get("seniority"))

    return {
        "ok": True,
        "description_chars_before": before,
        "description_chars_after": after,
        "jd_enriched": enriched,
    }


async def backfill_job_description(
    db: asyncpg.Connection,
    job: dict[str, Any],
    settings: Settings,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Ensure ``job["description"]`` is populated for kit/matching flows.

    Mutates ``job`` in place when text is found; optionally persists to ``jobs`` row.
    """
    if not is_thin_description(str(job.get("description") or "")):
        return job

    apply_url = str(job.get("apply_url") or "").strip()
    if not apply_url:
        return job

    result = await fetch_full_jd_text(apply_url, settings, db=db)
    text = result.get("text")
    if not text or not isinstance(text, str):
        return job

    job["description"] = text
    if persist and job.get("id"):
        try:
            await db.execute(
                """
                UPDATE public.jobs
                SET description = COALESCE(NULLIF(TRIM(description), ''), $2),
                    raw_data = COALESCE(raw_data, '{}'::jsonb) || $3::jsonb,
                    updated_at = NOW()
                WHERE id = $1::uuid
                  AND (description IS NULL OR LENGTH(TRIM(description)) < $4)
                """,
                job["id"],
                text,
                json.dumps(
                    {
                        "jd_backfill": {
                            "source": result.get("source"),
                            "fetched_at": datetime.now(UTC).isoformat(),
                        }
                    }
                ),
                THIN_JD_MIN_CHARS,
            )
        except Exception as exc:
            logger.warning("jd_backfill_persist_failed", job_id=job.get("id"), error=str(exc)[:120])

    return job
