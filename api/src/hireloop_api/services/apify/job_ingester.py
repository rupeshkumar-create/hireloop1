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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.markets import (
    MARKET_LABELS,
    MARKET_SCRAPE_LOCATIONS,
    SUPPORTED_MARKETS,
    resolve_country_from_location,
)
from hireloop_api.services.apify.candidate_job_query_plan import (
    CandidateJobTitleVariant,
    build_candidate_job_ingest_plan,
    build_title_query_variants,
)
from hireloop_api.services.apify.jobs_scraper import (
    DEFAULT_GOOGLE_JOBS_ACTOR,
    ApifyJobsScraper,
    JobRecord,
)
from hireloop_api.services.candidate_intelligence import load_candidate_intelligence
from hireloop_api.services.job_validator import validate_job_record

logger = structlog.get_logger()
IngestProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

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
    "customer experience": (
        "Customer Experience Manager",
        "Customer Success Manager",
        "CX Operations Manager",
    ),
    "cx operations": (
        "CX Operations Manager",
        "Customer Success Operations Manager",
        "Customer Support Operations Manager",
    ),
    "implementation": (
        "Implementation Manager",
        "Customer Onboarding Manager",
        "Customer Success Manager",
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
    # Community / hospitality operations (common India hospitality titles)
    "community associate": (
        "Community Manager",
        "Community Associate",
        "Guest Relations Executive",
        "Front Office Executive",
    ),
    "community manager": (
        "Community Manager",
        "Resident Manager",
        "Guest Relations Manager",
    ),
    "industrial trainee": ("Management Trainee", "Operations Executive", "Graduate Trainee"),
    "management trainee": ("Management Trainee", "Operations Executive", "Graduate Trainee"),
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
    "gtm": (
        "GTM Lead",
        "Lead GTM",
        "Head of GTM",
        "GTM Manager",
        "Go-to-Market Manager",
        "Revenue Operations Manager",
        "Growth Lead",
    ),
    "go-to-market": (
        "GTM Lead",
        "Lead GTM",
        "Head of GTM",
        "GTM Manager",
        "Go-to-Market Manager",
        "Revenue Operations Manager",
        "Growth Lead",
    ),
    "go to market": (
        "GTM Lead",
        "Lead GTM",
        "Head of GTM",
        "GTM Manager",
        "Go-to-Market Manager",
        "Revenue Operations Manager",
        "Growth Lead",
    ),
    "revenue": ("Revenue Operations Manager", "GTM Lead", "Growth Lead"),
    "sales": ("Sales Manager", "Business Development Manager", "Account Manager"),
    "business development": ("Business Development Manager", "Sales Manager"),
    "bd": ("Business Development Executive", "Business Development Manager"),
    "inside sales": ("Inside Sales Representative", "Sales Development Representative"),
    # Founder / operator
    "founder": (
        "Founder",
        "Co-Founder",
        "Entrepreneur in Residence",
        "Startup Founder",
        "Founding Product Manager",
        "Founding GTM Lead",
    ),
    "co-founder": (
        "Co-Founder",
        "Founder",
        "Entrepreneur in Residence",
        "Startup Founder",
        "Founding Product Manager",
        "Founding GTM Lead",
    ),
    "cofounder": (
        "Co-Founder",
        "Founder",
        "Entrepreneur in Residence",
        "Startup Founder",
        "Founding Product Manager",
        "Founding GTM Lead",
    ),
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


_LOCATION_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "bengaluru": ("Bengaluru, Karnataka, India",),
    "bangalore": ("Bengaluru, Karnataka, India",),
    "karnataka": ("Karnataka, India",),
    "maharashtra": ("Maharashtra, India",),
    "telangana": ("Telangana, India",),
    "tamil nadu": ("Tamil Nadu, India",),
    "haryana": ("Haryana, India",),
    "uttar pradesh": ("Uttar Pradesh, India",),
    "brooklyn": (
        "New York, New York, United States",
        "Brooklyn, New York, United States",
    ),
    "nyc": ("New York, New York, United States",),
    "new york city": ("New York, New York, United States",),
    "manhattan": ("New York, New York, United States",),
    "queens": ("New York, New York, United States",),
    "london": ("London, England, United Kingdom",),
    "manchester": ("Manchester, England, United Kingdom",),
    "england": ("England, United Kingdom",),
}


def derive_ingest_locations(
    locations: list[str] | None,
    settings: Settings | None,
    *,
    max_locations: int = 5,
) -> list[str]:
    """
    Normalize candidate-supplied search locations for the Google Jobs actor.

    Candidate profiles often store neighborhoods ("Brooklyn") while Google Jobs
    returns stronger volume for metro queries ("New York"). Keep the metro first
    and preserve the original as a fallback run.
    """
    if not locations:
        enabled = {m.upper() for m in (settings.enabled_markets if settings else ["IN"])}
        out: list[str] = []
        for market in SUPPORTED_MARKETS:
            if market in enabled:
                out.extend(MARKET_SCRAPE_LOCATIONS[market][:5])
        return out[:max_locations] or MARKET_SCRAPE_LOCATIONS["IN"][:max_locations]

    out: list[str] = []
    seen: set[str] = set()
    # When candidate stores a non-location string (e.g. "Upselling") but still
    # includes the market ("India"), falling back to safe metro cities avoids
    # empty Google Jobs results.
    fallback_added_markets: set[str] = set()

    def _add(raw: str | None) -> None:
        loc = (raw or "").strip()
        if not loc:
            return
        key = _norm_key(loc)
        if key not in seen:
            seen.add(key)
            out.append(loc)

    for loc in locations:
        low = _norm_key(loc)
        expanded = False
        for keyword, expansions in _LOCATION_EXPANSIONS.items():
            if keyword in low:
                for expanded_loc in expansions:
                    _add(expanded_loc)
                expanded = True
                break
        if not expanded:
            market = resolve_country_from_location(loc)
            if market:
                city = low.split(",", 1)[0]
                canonical = next(
                    (
                        candidate
                        for candidate in MARKET_SCRAPE_LOCATIONS.get(market, [])
                        if _norm_key(candidate).startswith(city)
                    ),
                    None,
                )
                if canonical:
                    _add(canonical)
                else:
                    # Unknown city/state inside a resolved market → ignore it and
                    # inject safe market metros once.
                    if market not in fallback_added_markets:
                        fallback_added_markets.add(market)
                        for default_loc in MARKET_SCRAPE_LOCATIONS.get(market, [])[
                            :max_locations
                        ]:
                            _add(default_loc)
                    # Otherwise: ignore this invalid location string.
            else:
                _add(loc)

    return out[:max_locations]


def _ingest_locations(settings: Settings | None, locations: list[str] | None) -> list[str]:
    return derive_ingest_locations(locations, settings)


def _title_lookup_text(title: str) -> str:
    low = (title or "").lower()
    return f"{low} {low.replace('-', ' ')}"


_GENERIC_SEARCH_TITLES = frozenset({"team lead", "team leader"})


def _is_generic_search_title(title: str | None) -> bool:
    low = _norm_key(title)
    return low in _GENERIC_SEARCH_TITLES


def _has_customer_ops_context(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "customer",
            "client",
            "cx",
            "support",
            "success",
            "experience",
            "implementation",
            "onboarding",
        )
    )


def _should_skip_expansion_keyword(text: str, keyword: str) -> bool:
    # "CX Operations Lead" should search customer/onboarding ops roles, not broad
    # Operations Manager / Program Manager roles.
    return keyword == "operations" and _has_customer_ops_context(text)


def _expand_title(title: str) -> list[str]:
    """Board-real adjacent titles for a (possibly niche) target title."""
    low = _title_lookup_text(title)
    extras: list[str] = []
    for keyword, adjacents in _TITLE_EXPANSIONS.items():
        if _should_skip_expansion_keyword(low, keyword):
            continue
        if keyword in low:
            extras.extend(adjacents)
    return extras


def _expand_skills(skills: list[str] | None) -> list[str]:
    """Board-real search titles inferred from resume skills/domain signals."""
    text = " ".join(str(skill or "") for skill in (skills or [])).lower()
    extras: list[str] = []
    seen: set[str] = set()
    for keyword, adjacents in _TITLE_EXPANSIONS.items():
        if _should_skip_expansion_keyword(text, keyword):
            continue
        if keyword in text:
            for adjacent in adjacents:
                key = adjacent.lower()
                if key not in seen:
                    seen.add(key)
                    extras.append(adjacent)
    return extras


def _title_function_tokens(title: str | None) -> set[str]:
    """Role/function words used to avoid cross-function query pollution."""
    from hireloop_api.services.titles import canonical_title_tokens

    generic = {
        "assistant",
        "associate",
        "executive",
        "head",
        "lead",
        "leader",
        "manager",
        "management",
        "senior",
        "sr",
        "junior",
        "jr",
        "director",
        "vp",
        "chief",
        "officer",
        "specialist",
    }
    return set(canonical_title_tokens(title) - generic)


_COMPATIBLE_QUERY_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset(
        {
            "category",
            "planner",
            "planning",
            "merchandiser",
            "merchandising",
            "buyer",
            "buying",
            "fashion",
            "retail",
        }
    ),
    frozenset({"customer", "success", "client", "support", "relationship", "account"}),
    frozenset({"data", "analyst", "analytics", "engineer", "scientist", "reporting", "sql"}),
    frozenset({"growth", "gtm", "gotomarket", "revenue", "sales"}),
    frozenset({"product", "design", "designer", "ux", "ui"}),
    frozenset({"recruitment", "recruiter", "talent", "hr", "payroll", "employee"}),
    frozenset({"founder", "cofounder", "entrepreneur", "founding", "startup"}),
)


def _same_query_family(candidate_tokens: set[str], target_tokens: set[str]) -> bool:
    return any(
        candidate_tokens & family and target_tokens & family
        for family in _COMPATIBLE_QUERY_FAMILIES
    )


def _fits_selected_target(candidate_title: str, selected_targets: list[str]) -> bool:
    """True when an adjacent query belongs to the selected career direction."""
    if not selected_targets:
        return True
    candidate_tokens = _title_function_tokens(candidate_title)
    if not candidate_tokens:
        return False
    for target in selected_targets:
        target_tokens = _title_function_tokens(target)
        if candidate_tokens & target_tokens:
            return True
        if _same_query_family(candidate_tokens, target_tokens):
            return True
    return False


def _looks_like_searchable_job_title(query: str | None) -> bool:
    """Reject bare skills/keywords that burn Apify credits and return 0 jobs.

    Google Jobs expects role titles ("Customer Success Manager"), not resume
    fragments ("Upselling", "python", "Communication"). Heuristic is
    conservative: keep known expansions + multi-word role-ish phrases.
    """
    cleaned = (query or "").strip()
    if not cleaned or _is_generic_search_title(cleaned):
        return False
    # Already in our board-real adjacent list → always searchable.
    known_adjacents = {t.lower() for adjacents in _TITLE_EXPANSIONS.values() for t in adjacents}
    if cleaned.lower() in known_adjacents:
        return True
    words = cleaned.split()
    if len(words) == 1:
        # Single token is almost always a skill ("python", "react", "sql").
        return False
    if len(cleaned) > 80:
        return False
    # Drop obvious skill / soft-skill blobs even if multi-word.
    low = cleaned.lower()
    skillish = (
        "skills",
        "communication",
        "upselling",
        "cross-selling",
        "microsoft office",
        "ms office",
        "excel",
        "powerpoint",
        "google sheets",
    )
    if any(marker == low or marker in low for marker in skillish) and len(words) <= 3:
        # Allow through if it still looks like a role ("Communication Manager").
        role_markers = (
            "manager",
            "lead",
            "director",
            "head",
            "engineer",
            "analyst",
            "specialist",
            "executive",
            "associate",
            "officer",
            "designer",
            "recruiter",
            "consultant",
        )
        if not any(m in low for m in role_markers):
            return False
    return True


def derive_ingest_queries(
    *,
    target_titles: list[str] | None,
    current_title: str | None,
    skills: list[str] | None,
    max_queries: int = 10,
    expand: bool = True,
) -> list[str]:
    """
    Pick the search queries for a candidate-scoped scrape.

    Prefers the candidate's **career-path target titles** (where they want to go),
    then their current title. With `expand=True`, each title also contributes
    board-real **adjacent titles** (e.g. "Growth Designer" → "Product Designer",
    "Growth Manager") and skill-domain expansions mapped to real job titles —
    never raw skill keywords. Original titles come first (highest intent);
    deduplicated (case-insensitive), order-preserving, capped.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(q: str | None) -> None:
        cleaned = (q or "").strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            return
        if not _looks_like_searchable_job_title(cleaned):
            return
        seen.add(key)
        out.append(cleaned)

    selected_targets = [
        t for t in (target_titles or []) if (t or "").strip() and not _is_generic_search_title(t)
    ]

    for title in selected_targets:
        _add(title)
        if expand:
            for adjacent in _expand_title(title):
                _add(adjacent)
    _add(current_title)
    if current_title and expand and not selected_targets:
        for adjacent in _expand_title(current_title):
            _add(adjacent)
    if expand:
        for adjacent in _expand_skills(skills):
            if _fits_selected_target(adjacent, selected_targets):
                _add(adjacent)
    # Never seed Apify with raw skill tokens — they return empty Google Jobs
    # results and waste actor runs. Thin profiles rely on title expansions above.
    return out[:max_queries]


async def _emit_ingest_progress(
    callback: IngestProgressCallback | None,
    event: dict[str, Any],
) -> None:
    if callback is None:
        return
    await callback(event)


def _empty_candidate_ingest_stats() -> dict[str, Any]:
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
        "variant_runs": [],
    }


def _merge_candidate_ingest_stats(
    aggregate: dict[str, Any],
    *,
    variant: CandidateJobTitleVariant,
    stats: dict[str, Any],
) -> None:
    for key in ("raw_items", "normalised", "inserted", "updated", "skipped"):
        aggregate[key] = int(aggregate.get(key) or 0) + int(stats.get(key) or 0)
    aggregate["elapsed_seconds"] = round(
        float(aggregate.get("elapsed_seconds") or 0.0) + float(stats.get("elapsed_seconds") or 0.0),
        1,
    )
    aggregate["ok"] = bool(aggregate.get("ok", True)) and bool(stats.get("ok", True))
    aggregate["degraded"] = bool(aggregate.get("degraded")) or bool(stats.get("degraded"))
    aggregate["errors"].update(stats.get("errors") or {})
    if stats.get("run_id") and not aggregate.get("run_id"):
        aggregate["run_id"] = stats["run_id"]
    if stats.get("dataset_id") and not aggregate.get("dataset_id"):
        aggregate["dataset_id"] = stats["dataset_id"]
    for source, source_stats in (stats.get("sources") or {}).items():
        target = aggregate["sources"].setdefault(source, {})
        for count_key in ("raw_items", "normalised"):
            target[count_key] = int(target.get(count_key) or 0) + int(
                source_stats.get(count_key) or 0
            )
        for list_key in ("run_ids", "dataset_ids"):
            target[list_key] = [
                *target.get(list_key, []),
                *list(source_stats.get(list_key) or []),
            ]
        for meta_key in ("actor", "run_id", "dataset_id"):
            if source_stats.get(meta_key) and not target.get(meta_key):
                target[meta_key] = source_stats[meta_key]
    aggregate["variant_runs"].append(
        {
            "query": variant.query,
            "source_title": variant.source_title,
            "rank": variant.rank,
            "inserted": int(stats.get("inserted") or 0),
            "updated": int(stats.get("updated") or 0),
            "skipped": int(stats.get("skipped") or 0),
            "raw_items": int(stats.get("raw_items") or 0),
            "normalised": int(stats.get("normalised") or 0),
            "ok": bool(stats.get("ok", True)),
        }
    )


def _prepend_requested_title_variants(
    requested_titles: list[str] | None,
    variants: list[CandidateJobTitleVariant],
) -> list[CandidateJobTitleVariant]:
    """Put explicit chat/onboarding titles before profile-derived title variants."""
    out: list[CandidateJobTitleVariant] = []
    seen: set[str] = set()

    def _add(variant: CandidateJobTitleVariant) -> None:
        key = _norm_key(variant.query)
        if key and key not in seen:
            seen.add(key)
            out.append(variant)

    for variant in build_title_query_variants(requested_titles or []):
        _add(variant)
    for variant in variants:
        _add(variant)
    return out


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
        force_refresh: bool = False,
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
        if queries and not force_refresh:
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
            "force_refresh": force_refresh,
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
        max_variant_runs: int = 5,
        progress_callback: IngestProgressCallback | None = None,
        requested_titles: list[str] | None = None,
        requested_locations: list[str] | None = None,
        force_refresh: bool = False,
    ) -> dict:
        """
        Scrape jobs scoped to ONE candidate's career path — their target titles
        (where they want to go), falling back to current title / skills — and the
        path's target locations. This is the live counterpart of the on-demand
        "find jobs for my path" flow, so a designer's scrape pulls design roles
        rather than generic defaults.
        """
        try:
            snapshot = await load_candidate_intelligence(self._db, candidate_id)
        except Exception as exc:
            snapshot = None
            logger.warning(
                "candidate_intelligence_ingest_plan_failed",
                candidate_id=candidate_id,
                error=str(exc)[:200],
            )

        if snapshot is not None:
            plan = build_candidate_job_ingest_plan(snapshot)
            variants = plan.title_variants or build_title_query_variants(plan.title_inputs)
            variants = _prepend_requested_title_variants(requested_titles, variants)
            locations = derive_ingest_locations(
                requested_locations or plan.raw_locations or None,
                self._settings,
            )
            candidate_time_range = time_range or (
                self._settings.google_jobs_candidate_time_range if self._settings else "7d"
            )
            logger.info(
                "job_ingestion_for_candidate_started",
                candidate_id=candidate_id,
                queries=[variant.query for variant in variants],
                locations=locations,
                planner="candidate_intelligence",
                planner_diagnostics=plan.diagnostics.model_dump(mode="json"),
            )
            return await self._ingest_candidate_title_variants(
                variants=variants,
                locations=locations,
                max_results_per_query=max_results_per_query,
                time_range=candidate_time_range,
                max_variant_runs=max_variant_runs,
                progress_callback=progress_callback,
                planner_diagnostics=plan.diagnostics.model_dump(mode="json"),
                force_refresh=force_refresh,
            )

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

        for title in requested_titles or []:
            _add_title(title)
        _add_title(row.get("prioritized_title"))
        _add_title(row.get("looking_for"))
        for title in list(row["target_titles"] or []):
            _add_title(str(title))

        queries = derive_ingest_queries(
            target_titles=search_titles,
            current_title=row["current_title"],
            skills=list(row["skills"] or []),
        )
        variants = build_title_query_variants(queries)
        raw_locations = requested_locations or list(row["target_locations"] or []) or (
            [p for p in [row["location_city"], row["location_state"]] if p] or None
        )
        locations = derive_ingest_locations(raw_locations, self._settings)
        candidate_time_range = time_range or (
            self._settings.google_jobs_candidate_time_range if self._settings else "7d"
        )
        logger.info(
            "job_ingestion_for_candidate_started",
            candidate_id=candidate_id,
            queries=queries,
            locations=locations,
        )
        return await self._ingest_candidate_title_variants(
            variants=variants,
            locations=locations,
            max_results_per_query=max_results_per_query,
            time_range=candidate_time_range,
            max_variant_runs=max_variant_runs,
            progress_callback=progress_callback,
            force_refresh=force_refresh,
        )

    async def _ingest_candidate_title_variants(
        self,
        *,
        variants: list[CandidateJobTitleVariant],
        locations: list[str],
        max_results_per_query: int,
        time_range: str,
        max_variant_runs: int,
        progress_callback: IngestProgressCallback | None = None,
        planner_diagnostics: dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> dict:
        selected = variants[: max(1, max_variant_runs)]
        if not selected:
            return await self.ingest(
                queries=None,
                locations=locations,
                max_results_per_query=max_results_per_query,
                time_range=time_range,
                force_refresh=force_refresh,
            )

        await _emit_ingest_progress(
            progress_callback,
            {
                "phase": "queued",
                "total": len(selected),
                "queries": [variant.query for variant in selected],
            },
        )
        aggregate = _empty_candidate_ingest_stats()
        aggregate["planner_diagnostics"] = planner_diagnostics or {}
        aggregate["variant_queries"] = [variant.query for variant in selected]

        for index, variant in enumerate(selected, start=1):
            await _emit_ingest_progress(
                progress_callback,
                {
                    "phase": "searching",
                    "query": variant.query,
                    "source_title": variant.source_title,
                    "step": index,
                    "total": len(selected),
                },
            )
            stats = await self.ingest(
                queries=[variant.query],
                locations=locations,
                max_results_per_query=max_results_per_query,
                time_range=time_range,
            )
            _merge_candidate_ingest_stats(aggregate, variant=variant, stats=stats)
            await _emit_ingest_progress(
                progress_callback,
                {
                    "phase": "stored",
                    "query": variant.query,
                    "source_title": variant.source_title,
                    "step": index,
                    "total": len(selected),
                    "inserted": int(stats.get("inserted") or 0),
                    "updated": int(stats.get("updated") or 0),
                    "raw_items": int(stats.get("raw_items") or 0),
                },
            )

        await _emit_ingest_progress(
            progress_callback,
            {
                "phase": "completed",
                "total": len(selected),
                "inserted": aggregate["inserted"],
                "updated": aggregate["updated"],
                "raw_items": aggregate["raw_items"],
            },
        )
        return aggregate

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
