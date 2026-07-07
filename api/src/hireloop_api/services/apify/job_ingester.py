"""
Job ingestion service — orchestrates Apify scrape → normalise → upsert to DB.

Called by:
  - pg_cron (nightly at 2am IST via pg_net HTTP call to /api/v1/jobs/ingest)
  - Manual trigger via POST /api/v1/jobs/ingest (admin only)
  - Background task on first startup (seeds initial dataset)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.markets import MARKET_SCRAPE_LOCATIONS, SUPPORTED_MARKETS
from hireloop_api.services.apify.jobs_scraper import (
    DEFAULT_GOOGLE_JOBS_ACTOR,
    ApifyJobsScraper,
    JobRecord,
)
from hireloop_api.services.job_validator import validate_job_record

logger = structlog.get_logger()

# A query+location scraped within this window returns a near-identical result
# set — skip it instead of burning another Google Jobs/Apify run. The nightly
# cron (24h cadence) is unaffected; on-demand triggers (kickoff, empty search,
# pool top-up) are the ones that hammered the same query repeatedly.
INGEST_DEDUPE_HOURS = 24


def _norm_key(value: str | None) -> str:
    return " ".join((value or "").lower().split())


_MAX_JD_ENRICH_PER_INGEST = 20


def _failed_source_stats(exc: Exception) -> dict:
    """Per-source stats placeholder when a job source is unavailable."""
    return {"error": str(exc), "raw_items": 0, "normalised": 0}


def _source_errors(source_stats: dict[str, dict]) -> dict[str, str]:
    """Map of source → error message for every source that failed."""
    return {src: s["error"] for src, s in source_stats.items() if s.get("error")}


def _all_sources_failed(source_stats: dict[str, dict]) -> bool:
    """True when every attempted source errored (→ raise, don't ship empty)."""
    return bool(source_stats) and set(_source_errors(source_stats)) == set(source_stats)


# Niche / hybrid career-path titles barely exist on Indian job boards
# ("Growth Designer", "AI Automation Specialist"), so a literal search returns
# nothing. Map their keywords to board-real adjacent titles so the scrape still
# pulls relevant openings. Keyword (substring, lower-cased) → adjacent titles.
_TITLE_EXPANSIONS: dict[str, tuple[str, ...]] = {
    # Generalist / operations titles
    "assistant manager": (
        "Operations Manager",
        "Customer Success Manager",
        "Customer Support Manager",
        "Team Lead",
    ),
    "senior executive": ("Assistant Manager", "Team Lead", "Operations Executive"),
    "executive": ("Operations Executive", "Customer Support Executive"),
    "operations": ("Operations Manager", "Operations Executive", "Program Manager"),
    "admin": ("Administration Manager", "Operations Executive"),
    "office": ("Office Administrator", "Administration Manager"),
    # Customer-facing roles
    "customer success": (
        "Customer Success Manager",
        "Customer Success Associate",
        "Client Success Manager",
    ),
    "customer support": (
        "Customer Support Executive",
        "Customer Support Manager",
        "Support Manager",
    ),
    "client success": ("Client Success Manager", "Customer Success Manager"),
    "client consultation": ("Client Success Manager", "Relationship Manager"),
    "relationship": ("Relationship Manager", "Account Manager", "Client Success Manager"),
    "account manager": ("Account Manager", "Key Account Manager"),
    "call quality": ("Quality Analyst", "Customer Support Quality Analyst"),
    "quality monitoring": ("Quality Analyst", "Customer Support Quality Analyst"),
    # Fashion / retail / merchandising
    "category planner": ("Category Manager", "Merchandiser", "Retail Planner"),
    "category": ("Category Manager", "Category Planner"),
    "merchandising": ("Merchandiser", "Merchandising Manager", "Category Manager"),
    "merchandiser": ("Merchandiser", "Merchandising Manager"),
    "fashion": ("Fashion Buyer", "Fashion Merchandiser", "Category Manager"),
    "buying": ("Buyer", "Fashion Buyer", "Category Manager"),
    "buyer": ("Buyer", "Category Manager"),
    "retail": ("Retail Manager", "Store Manager", "Category Manager"),
    "store": ("Store Manager", "Retail Manager"),
    "inventory": ("Inventory Planner", "Supply Planner", "Merchandiser"),
    # HR / people
    "recruitment": ("Recruiter", "Talent Acquisition Specialist", "HR Executive"),
    "recruiter": ("Recruiter", "Talent Acquisition Specialist"),
    "talent acquisition": ("Talent Acquisition Specialist", "Recruiter"),
    "payroll": ("Payroll Executive", "HR Executive"),
    "employee relations": ("HR Executive", "HR Business Partner"),
    "human resources": ("HR Executive", "HR Manager", "HR Business Partner"),
    "hr": ("HR Executive", "HR Manager", "Talent Acquisition Specialist"),
    # Finance / accounting
    "finance": ("Finance Executive", "Financial Analyst", "Finance Manager"),
    "accounting": ("Accountant", "Accounts Executive", "Finance Executive"),
    "accounts": ("Accounts Executive", "Accountant"),
    "tax": ("Tax Analyst", "Tax Consultant"),
    "audit": ("Audit Associate", "Internal Auditor"),
    # Sales / GTM
    "sales": ("Sales Manager", "Business Development Manager", "Account Manager"),
    "business development": ("Business Development Manager", "Sales Manager"),
    "bd": ("Business Development Executive", "Business Development Manager"),
    "inside sales": ("Inside Sales Representative", "Sales Development Representative"),
    "growth designer": ("Product Designer", "Growth Manager"),
    "product design": ("Product Designer",),
    "ux": ("UX Designer", "Product Designer"),
    "ui": ("UI/UX Designer",),
    "designer": ("Product Designer",),
    "growth": ("Growth Manager", "Product Manager"),
    "automation": ("Automation Engineer", "Solutions Engineer"),
    "ai engineer": ("Machine Learning Engineer", "AI Engineer"),
    "full stack": ("Full Stack Engineer",),
    "frontend": ("Frontend Engineer",),
    "backend": ("Backend Engineer",),
    "data": ("Data Analyst", "Data Engineer"),
    "it": ("IT Support Engineer", "System Administrator", "Network Engineer"),
    "information technology": ("IT Support Engineer", "System Administrator"),
    "system administrator": ("System Administrator", "IT Administrator"),
    "network": ("Network Engineer", "System Administrator"),
    "support engineer": ("Technical Support Engineer", "IT Support Engineer"),
    "marketing": ("Marketing Manager", "Performance Marketing Manager"),
    "digital marketing": ("Digital Marketing Manager", "Performance Marketing Manager"),
    "seo": ("SEO Specialist", "Digital Marketing Manager"),
    "social media": ("Social Media Manager", "Digital Marketing Manager"),
    "content": ("Content Marketing Manager", "Content Writer"),
    "brand": ("Brand Manager", "Marketing Manager"),
    "product manager": ("Product Manager",),
}


def _ingest_locations(settings: Settings | None, locations: list[str] | None) -> list[str]:
    if locations:
        return locations
    enabled = {m.upper() for m in (settings.enabled_markets if settings else ["IN"])}
    out: list[str] = []
    for market in SUPPORTED_MARKETS:
        if market in enabled:
            out.extend(MARKET_SCRAPE_LOCATIONS[market][:5])
    return out or MARKET_SCRAPE_LOCATIONS["IN"]


def _expand_title(title: str) -> list[str]:
    """Board-real adjacent titles for a (possibly niche) target title."""
    low = (title or "").lower()
    extras: list[str] = []
    for keyword, adjacents in _TITLE_EXPANSIONS.items():
        if keyword in low:
            extras.extend(adjacents)
    return extras


def _expand_skills(skills: list[str] | None) -> list[str]:
    """Board-real search titles inferred from resume skills/domain signals."""
    text = " ".join(str(skill or "") for skill in (skills or [])).lower()
    extras: list[str] = []
    seen: set[str] = set()
    for keyword, adjacents in _TITLE_EXPANSIONS.items():
        if keyword in text:
            for adjacent in adjacents:
                key = adjacent.lower()
                if key not in seen:
                    seen.add(key)
                    extras.append(adjacent)
    return extras


def derive_ingest_queries(
    *,
    target_titles: list[str] | None,
    current_title: str | None,
    skills: list[str] | None,
    max_queries: int = 8,
    expand: bool = True,
) -> list[str]:
    """
    Pick the search queries for a candidate-scoped scrape.

    Prefers the candidate's **career-path target titles** (where they want to go),
    then their current title, then top skills. With `expand=True`, each title also
    contributes board-real **adjacent titles** (e.g. "Growth Designer" →
    "Product Designer", "Growth Manager") so niche/hybrid roles still return live
    openings instead of an empty index. Original titles come first (highest
    intent); deduplicated (case-insensitive), order-preserving, capped.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(q: str | None) -> None:
        cleaned = (q or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)

    for title in target_titles or []:
        _add(title)
        if expand:
            for adjacent in _expand_title(title):
                _add(adjacent)
    _add(current_title)
    if current_title and expand:
        for adjacent in _expand_title(current_title):
            _add(adjacent)
    if expand:
        for adjacent in _expand_skills(skills):
            _add(adjacent)
    if len(out) < 2:  # thin path/title → seed from a few concrete skills
        for skill in (skills or [])[:3]:
            _add(skill)
    return out[:max_queries]


class JobIngester:
    def __init__(
        self,
        apify_token: str,
        db: asyncpg.Connection,
        *,
        settings: Settings | None = None,
        jobs_actor: str = DEFAULT_GOOGLE_JOBS_ACTOR,
        linkedin_actor: str | None = None,
        career_site_actor: str | None = None,
        enable_career_site: bool | None = None,
    ) -> None:
        self._apify_token = apify_token
        self._settings = settings
        # Legacy kwargs are accepted so older callers/tests do not break, but
        # job ingestion is Google Jobs only.
        self._scraper = ApifyJobsScraper(apify_token, actor=jobs_actor)
        self._db = db

    async def ingest(
        self,
        queries: list[str] | None = None,
        locations: list[str] | None = None,
        max_results_per_query: int = 25,
        time_range: str | None = None,
        *,
        use_career_site: bool | None = None,
        use_linkedin: bool = False,
        description_search: list[str] | None = None,
    ) -> dict:
        """
        Full ingestion pipeline:
        1. Trigger Apify run
        2. Wait for completion
        3. Fetch dataset
        4. Normalise
        5. Upsert to DB (dedup on apify_job_id)
        6. Return stats

        `time_range` controls how far back to look (e.g. "24h" for the nightly
        cron, "7d" for on-demand searches where niche/senior roles are sparse
        within any single day).
        """
        start = datetime.now(UTC)
        logger.info("job_ingestion_started")
        scrape_locations = _ingest_locations(self._settings, locations)
        effective_time_range = time_range or (
            self._settings.google_jobs_time_range if self._settings else "24h"
        )

        # Recency gate: drop queries already scraped for this location inside
        # the dedupe window; if nothing is left, skip the run entirely.
        loc_key = _norm_key(scrape_locations[0] if scrape_locations else "")
        if queries:
            try:
                recent_rows = await self._db.fetch(
                    f"""
                    SELECT query_norm FROM public.job_ingest_runs
                    WHERE query_norm = ANY($1::text[])
                      AND location_norm = $2
                      AND source = 'google_jobs'
                      AND last_run_at > NOW() - INTERVAL '{INGEST_DEDUPE_HOURS} hours'
                    """,
                    [_norm_key(q) for q in queries],
                    loc_key,
                )
                recent = {r["query_norm"] for r in recent_rows}
                kept = [q for q in queries if _norm_key(q) not in recent]
                if len(kept) < len(queries):
                    logger.info(
                        "ingest_queries_deduped",
                        skipped=len(queries) - len(kept),
                        kept=len(kept),
                    )
                queries = kept
            except Exception as exc:  # gate is an optimisation, never a blocker
                logger.warning("ingest_dedupe_check_failed", error=str(exc)[:200])
            if not queries:
                logger.info("job_ingestion_skipped_recent")
                return {
                    "run_id": None,
                    "dataset_id": None,
                    "raw_items": 0,
                    "normalised": 0,
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "elapsed_seconds": 0.0,
                    "sources": {},
                    "ok": True,
                    "degraded": False,
                    "errors": {},
                    "deduped": True,
                }

        all_records: list[JobRecord] = []
        source_stats: dict[str, dict] = {}
        # Single source: johnvc/Google-Jobs-Scraper. The legacy source flags are
        # intentionally ignored so no old actor can run from stale call sites.
        try:
            _, records, google_stats = await self._scraper.scrape(
                queries=queries,
                locations=scrape_locations,
                max_results_per_query=max_results_per_query,
                time_range=effective_time_range,
            )
            all_records.extend(records)
            source_stats["google_jobs"] = google_stats
        except Exception as exc:
            logger.error("job_source_failed", source="google_jobs", error=str(exc))
            source_stats["google_jobs"] = _failed_source_stats(exc)

        # Fail loud, not silent: if every source we attempted errored out (e.g.
        # an Apify actor whose rental lapsed → 403), there are no records and the
        # caller must know the source is broken — otherwise a new profile just
        # gets a silently-empty feed. A source that ran fine but returned zero
        # jobs is NOT a failure.
        errors = _source_errors(source_stats)
        if _all_sources_failed(source_stats):
            raise RuntimeError(
                "All job sources failed: "
                + "; ".join(f"{src}: {msg}" for src, msg in errors.items())
            )

        # 5. Upsert
        inserted, updated, skipped = await self._upsert_jobs(all_records)

        # 6. Ensure companies exist for all scraped jobs
        await self._ensure_companies(all_records)

        # Prefer whichever source actually ran for the top-level run/dataset ids.
        primary = source_stats.get("google_jobs") or {}
        elapsed = (datetime.now(UTC) - start).total_seconds()
        stats = {
            "run_id": primary.get("run_id"),
            "dataset_id": primary.get("dataset_id"),
            "raw_items": sum(s["raw_items"] for s in source_stats.values()) if source_stats else 0,
            "normalised": (
                sum(s["normalised"] for s in source_stats.values()) if source_stats else 0
            ),
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "elapsed_seconds": round(elapsed, 1),
            "sources": source_stats,
            # Health signals so callers can surface a degraded source instead of
            # silently shipping a thin feed.
            "ok": not errors,
            "degraded": bool(errors),
            "errors": errors,
        }
        # Record the run so the dedupe gate can skip identical queries for the
        # next INGEST_DEDUPE_HOURS. Best-effort.
        # Zero-result runs are NOT recorded: an empty answer (too-narrow
        # window, thin function) must not block a retry for 24h.
        if queries and not errors and (inserted + updated) > 0:
            try:
                total = inserted + updated
                for q in queries:
                    await self._db.execute(
                        """
                        INSERT INTO public.job_ingest_runs
                          (query_norm, location_norm, source, last_run_at, jobs_found)
                        VALUES ($1, $2, 'google_jobs', NOW(), $3)
                        ON CONFLICT (query_norm, location_norm, source)
                        DO UPDATE SET last_run_at = NOW(), jobs_found = $3
                        """,
                        _norm_key(q),
                        loc_key,
                        total,
                    )
            except Exception as exc:
                logger.warning("ingest_run_record_failed", error=str(exc)[:200])

        logger.info("job_ingestion_completed", **stats)
        return stats

    async def ingest_sample(self) -> dict:
        """
        Seed the DB with built-in sample India jobs — no Apify token, no network.

        Runs the same normalise → upsert → company-link path as a live scrape, so
        it's a faithful way to exercise matching, the feed, and Aarya's job
        recommendations end-to-end before the Apify token is configured.
        """
        from hireloop_api.services.apify.sample_jobs import sample_job_records

        start = datetime.now(UTC)
        records = sample_job_records()
        inserted, updated, skipped = await self._upsert_jobs(records)
        await self._ensure_companies(records)
        stats = {
            "source": "sample",
            "raw_items": len(records),
            "normalised": len(records),
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "elapsed_seconds": round((datetime.now(UTC) - start).total_seconds(), 1),
        }
        logger.info("job_ingestion_sample_completed", **stats)
        return stats

    async def ingest_for_candidate(
        self,
        candidate_id: str,
        *,
        max_results_per_query: int = 20,
        time_range: str = "7d",
    ) -> dict:
        """
        Scrape jobs scoped to ONE candidate's career path — their target titles
        (where they want to go), falling back to current title / skills — and the
        path's target locations. This is the live counterpart of the on-demand
        "find jobs for my path" flow, so a designer's scrape pulls design roles
        rather than generic defaults.
        """
        row = await self._db.fetchrow(
            """
            SELECT
                c.current_title,
                c.location_city,
                c.location_state,
                c.skills,
                c.looking_for,
                (
                    SELECT cp.prioritized_title FROM public.career_paths cp
                    WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                    ORDER BY cp.created_at DESC LIMIT 1
                ) AS prioritized_title,
                (
                    SELECT cp.target_titles FROM public.career_paths cp
                    WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                    ORDER BY cp.created_at DESC LIMIT 1
                ) AS target_titles,
                (
                    SELECT cp.target_locations FROM public.career_paths cp
                    WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                    ORDER BY cp.created_at DESC LIMIT 1
                ) AS target_locations
            FROM public.candidates c
            WHERE c.id = $1::uuid AND c.deleted_at IS NULL
            """,
            uuid.UUID(candidate_id),
        )
        if not row:
            return {"error": "candidate not found", "candidate_id": candidate_id}

        search_titles: list[str] = []
        seen_titles: set[str] = set()

        def _add_title(raw: str | None) -> None:
            title = (raw or "").strip()
            if not title:
                return
            key = title.lower()
            if key in seen_titles:
                return
            seen_titles.add(key)
            search_titles.append(title)

        _add_title(row.get("prioritized_title"))
        _add_title(row.get("looking_for"))
        for title in list(row["target_titles"] or []):
            _add_title(str(title))

        queries = derive_ingest_queries(
            target_titles=search_titles,
            current_title=row["current_title"],
            skills=list(row["skills"] or []),
        )
        locations = list(row["target_locations"] or []) or (
            [p for p in [row["location_city"], row["location_state"]] if p] or None
        )
        candidate_time_range = time_range or (
            self._settings.google_jobs_candidate_time_range if self._settings else "7d"
        )
        logger.info(
            "job_ingestion_for_candidate_started",
            candidate_id=candidate_id,
            queries=queries,
            locations=locations,
        )
        return await self.ingest(
            queries=queries or None,
            locations=locations,
            max_results_per_query=max_results_per_query,
            time_range=candidate_time_range,
        )

    async def ingest_records(self, records: list[JobRecord]) -> dict:
        """
        Persist pre-normalised JobRecords (e.g. from the ATS source) through the
        same upsert + company-link path as scraped jobs. Public so non-Apify
        sources can reuse the dedup/company logic without duplicating SQL.

        Runs the ingest-time hard validator first (#3) so structurally unusable
        postings (no apply URL, expired, untitled) never reach the DB.
        """
        valid: list[JobRecord] = []
        dropped: dict[str, int] = {}
        for rec in records:
            ok, reason = validate_job_record(rec)
            if ok:
                valid.append(rec)
            else:
                dropped[reason] = dropped.get(reason, 0) + 1
        inserted, updated, skipped = await self._upsert_jobs(valid)
        await self._ensure_companies(valid)
        stats = {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "rejected": sum(dropped.values()),
            "rejected_by": dropped,
        }
        logger.info("ats_records_ingested", **stats)
        return stats

    async def _upsert_jobs(self, records: list[JobRecord]) -> tuple[int, int, int]:
        """
        Upsert job records. Dedup key: apify_job_id.
        Returns (inserted, updated, skipped).
        """
        inserted = updated = skipped = 0
        enriched = 0

        for rec in records:
            try:
                if enriched < _MAX_JD_ENRICH_PER_INGEST:
                    did = await self._maybe_enrich_record(rec)
                    if did:
                        enriched += 1

                existing = await self._db.fetchrow(
                    "SELECT id, updated_at FROM public.jobs WHERE apify_job_id = $1",
                    rec.apify_job_id,
                )

                # Cross-source / re-scrape dedup: the same posting surfaced under a
                # different apify_job_id (e.g. another run or source) but the same
                # apply_url must NOT create a duplicate row daily/weekly.
                if existing is None and rec.apply_url:
                    dup = await self._db.fetchrow(
                        "SELECT id FROM public.jobs "
                        "WHERE apply_url = $1 AND deleted_at IS NULL "
                        "LIMIT 1",
                        rec.apply_url,
                    )
                    if dup is not None:
                        skipped += 1
                        continue

                if existing is None:
                    # INSERT new job
                    await self._db.execute(
                        """
                        INSERT INTO public.jobs (
                            id, title, description, requirements,
                            location_city, location_state, country_code,
                            salary_currency, allowed_regions,
                            is_remote, employment_type, seniority,
                            ctc_min, ctc_max, skills_required,
                            apify_job_id, apply_url, source,
                            is_active, scraped_at, expires_at, raw_data
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                            $13, $14, $15, $16, $17, $18, TRUE, $19, $20, $21::jsonb
                        )
                        """,
                        uuid.uuid4(),
                        rec.title,
                        rec.description,
                        rec.requirements,
                        rec.location_city,
                        rec.location_state,
                        rec.country_code,
                        rec.salary_currency,
                        rec.allowed_regions,
                        rec.is_remote,
                        rec.employment_type,
                        rec.seniority,
                        rec.ctc_min,
                        rec.ctc_max,
                        rec.skills_required,
                        rec.apify_job_id,
                        rec.apply_url,
                        rec.source,
                        datetime.now(UTC),
                        rec.expires_at or datetime.now(UTC) + timedelta(days=30),
                        json.dumps(rec.raw_data),
                    )
                    inserted += 1
                else:
                    # UPDATE if re-scraped (refreshes skills, description, active status)
                    await self._db.execute(
                        """
                        UPDATE public.jobs SET
                            title = $2,
                            description = COALESCE($3, description),
                            skills_required = $4,
                            apply_url = COALESCE($5, apply_url),
                            is_active = TRUE,
                            scraped_at = $6,
                            expires_at = $7,
                            updated_at = NOW()
                        WHERE apify_job_id = $1
                        """,
                        rec.apify_job_id,
                        rec.title,
                        rec.description,
                        rec.skills_required,
                        rec.apply_url,
                        datetime.now(UTC),
                        rec.expires_at or datetime.now(UTC) + timedelta(days=30),
                    )
                    updated += 1

            except Exception as exc:
                logger.warning("job_upsert_failed", apify_id=rec.apify_job_id, error=str(exc))
                skipped += 1

        return inserted, updated, skipped

    async def _maybe_enrich_record(self, rec: JobRecord) -> bool:
        """Fill missing skills/seniority from JD via LLM (ingest-time, capped)."""
        if not self._settings or not self._settings.openrouter_api_key:
            return False
        if rec.skills_required and len(rec.skills_required) >= 2:
            return False
        if not (rec.description or "").strip():
            return False
        from hireloop_api.services.jd_enrichment import enrich_job_description

        payload = await enrich_job_description(rec.title, rec.description or "", self._settings)
        if not payload:
            return False
        skills = payload.get("skills_required") or []
        if skills:
            rec.skills_required = skills
        if payload.get("seniority") and not rec.seniority:
            rec.seniority = payload["seniority"]
        if payload.get("ctc_min") and not rec.ctc_min:
            rec.ctc_min = payload["ctc_min"]
        if payload.get("ctc_max") and not rec.ctc_max:
            rec.ctc_max = payload["ctc_max"]
        return bool(skills or payload.get("seniority"))

    async def _ensure_companies(self, records: list[JobRecord]) -> None:
        """
        Upsert company records for scraped jobs.
        Dedup key: normalised company name.
        """
        seen: set[str] = set()
        for rec in records:
            if not rec.company_name:
                continue
            key = rec.company_name.lower().strip()
            if key in seen:
                continue
            seen.add(key)

            existing = await self._db.fetchrow(
                "SELECT id FROM public.companies WHERE LOWER(name) = $1 AND deleted_at IS NULL",
                key,
            )
            if not existing:
                try:
                    await self._db.execute(
                        """
                        INSERT INTO public.companies (id, name, linkedin_url, country_code)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT DO NOTHING
                        """,
                        uuid.uuid4(),
                        rec.company_name,
                        rec.company_linkedin_url,
                        rec.country_code,
                    )
                except Exception as exc:
                    # Duplicate/constraint races are expected when two jobs from
                    # the same company are processed concurrently — log at debug.
                    logger.debug(
                        "company_insert_skipped",
                        company=rec.company_name,
                        error=str(exc),
                    )

            # Link job to company
            if existing or True:
                company = await self._db.fetchrow(
                    "SELECT id FROM public.companies WHERE LOWER(name) = $1 LIMIT 1",
                    key,
                )
                if company:
                    await self._db.execute(
                        """
                        UPDATE public.jobs
                        SET company_id = $1
                        WHERE apify_job_id = ANY($2::text[])
                          AND company_id IS NULL
                        """,
                        company["id"],
                        [
                            r.apify_job_id
                            for r in records
                            if (r.company_name or "").lower().strip() == key
                        ],
                    )
