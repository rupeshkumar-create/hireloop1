"""
Match routes — pre-computed candidate↔job scores + embedding triggers.

GET  /api/v1/matches                    → candidate's ranked job feed
GET  /api/v1/matches/count              → total matches (same filters as feed)
GET  /api/v1/matches/{job_id}           → single match score for current candidate
POST /api/v1/matches/recompute          → admin: re-score all (service-secret)
POST /api/v1/matches/embed              → admin: re-embed all pending (service-secret)
POST /api/v1/matches/embed/candidate/{id} → embed + score a single candidate inline
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.market_db import fetch_candidate_market
from hireloop_api.markets import job_visible_for_market_sql, normalize_market
from hireloop_api.services.job_preferences import (
    extract_negative_preferences,
    normalize_remote_preference,
    remote_filter_sql,
)
from hireloop_api.services.match_quality import DEFAULT_FEED_MIN_SCORE, should_persist_match
from hireloop_api.services.match_rationale import generate_match_rationales
from hireloop_api.services.matching import (
    MatchingEngine,
    _assemble_score,
)
from hireloop_api.services.ranking import (
    HardConstraints,
    assemble_first_screen,
    attach_tiers,
    boost_by_saved,
    passes_hard_constraints,
)
from hireloop_api.services.skills import canonical_skill

logger = structlog.get_logger()
router = APIRouter(prefix="/matches", tags=["matches"])

# Per-candidate locks so a fresh candidate's first feed load scores exactly once,
# even when several requests race right after signup (see get_match_feed).
_first_score_locks: dict[str, asyncio.Lock] = {}


# ── Auth helper ───────────────────────────────────────────────────────────────


def _require_service_secret(x_service_secret: str | None, settings: Settings) -> None:
    if not x_service_secret or x_service_secret != settings.service_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing service secret")


# ── Response models ───────────────────────────────────────────────────────────


class MatchedJob(BaseModel):
    job_id: str
    title: str
    company_name: str | None
    location_city: str | None
    location_state: str | None
    is_remote: bool
    employment_type: str | None
    seniority: str | None
    ctc_min: int | None
    ctc_max: int | None
    salary_currency: str | None = None
    skills_required: list[str]
    apply_url: str | None
    # Full posting detail (so the candidate never has to leave the app).
    description: str | None = None
    requirements: str | None = None
    posted_at: str | None = None
    # Match score fields
    overall_score: float
    skills_score: float | None
    experience_score: float | None
    location_score: float | None
    ctc_score: float | None
    explanation: str | None
    computed_at: str
    # Skill detail: which required skills the candidate has vs is missing.
    skills_matched: list[str] = []
    skills_gap: list[str] = []
    # Presentation layer (services.ranking) — confidence badge for the UI.
    tier: str | None = None
    tier_label: str | None = None


class RecomputeResponse(BaseModel):
    status: str
    candidates_processed: int = 0
    total_pairs_scored: int = 0
    elapsed_seconds: float = 0.0


class EmbedResponse(BaseModel):
    status: str
    embedded: int = 0
    failed: int = 0


# ── Candidate match feed ──────────────────────────────────────────────────────


@router.get("", response_model=list[MatchedJob])
async def get_match_feed(
    min_score: float = Query(
        # Relevance floor: by default the candidate feed hides weak/wrong-function
        # matches (e.g. a 5% RevOps role for a UX designer). The frontend can pass
        # min_score=0 for an explicit "show everything" view. Tune as needed.
        default=DEFAULT_FEED_MIN_SCORE,
        ge=0.0,
        le=1.0,
        description="Minimum overall score filter (default relevance floor)",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """
    Return the current candidate's ranked job matches, best first.
    Only active jobs in the candidate's market with unexpired match scores are returned.
    """
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.current_title, c.current_company, c.headline, c.summary,
               c.years_experience, c.skills,
               c.location_city, c.location_state, c.expected_ctc_min, c.expected_ctc_max,
               c.remote_preference, c.open_to_relocation, c.location_scope,
               c.aarya_state, c.market,
               (
                   SELECT cp.target_titles
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS target_titles
        FROM public.candidates c
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    remote_pref = normalize_remote_preference(candidate.get("remote_preference"))
    market = normalize_market(candidate.get("market"))
    if not candidate.get("market"):
        market = await fetch_candidate_market(db, candidate["id"])

    rows = await _fetch_cached_match_rows(
        db,
        candidate_id=candidate["id"],
        min_score=min_score,
        limit=limit,
        offset=offset,
        remote_preference=remote_pref,
        market=market,
    )

    if not rows and offset == 0:
        # Single-flight: right after signup the feed, count, and home panel can all
        # request page 1 concurrently — without a lock each one runs the full
        # candidate-vs-jobs scoring pass (N-fold DB/LLM work and latency). The lock
        # serialises them; whoever waited re-checks the cache and skips scoring.
        lock = _first_score_locks.setdefault(str(candidate["id"]), asyncio.Lock())
        async with lock:
            rows = await _fetch_cached_match_rows(
                db,
                candidate_id=candidate["id"],
                min_score=min_score,
                limit=limit,
                offset=offset,
                remote_preference=remote_pref,
                market=market,
            )
            if not rows:
                engine = MatchingEngine(db)
                scored = await engine.score_candidate(str(candidate["id"]), limit=max(50, limit))
                logger.info(
                    "match_feed_live_scored",
                    candidate_id=str(candidate["id"]),
                    scored=scored,
                )
                if scored:
                    rows = await _fetch_cached_match_rows(
                        db,
                        candidate_id=candidate["id"],
                        min_score=min_score,
                        limit=limit,
                        offset=offset,
                        remote_preference=remote_pref,
                        market=market,
                    )
        _first_score_locks.pop(str(candidate["id"]), None)

    result = _serialize_current_quality_cached_rows(
        rows, candidate=dict(candidate), min_score=min_score
    )
    if not result:
        result = await _fetch_fallback_match_rows(
            db,
            candidate=dict(candidate),
            min_score=min_score,
            limit=limit,
            offset=offset,
            remote_preference=remote_pref,
            market=market,
        )

    # Hard constraints: drop deal-breakers on every page (so pagination is
    # consistent) — roles whose stated pay band is clearly below the candidate's
    # CTC floor (minus negotiation slack), and any remote/on-site mismatch the
    # SQL filter didn't already catch. Unknown pay is never a deal-breaker.
    excl_companies, excl_titles = extract_negative_preferences(candidate.get("aarya_state"))
    constraints = HardConstraints(
        remote_preference=remote_pref,
        ctc_floor=candidate.get("expected_ctc_min"),
        excluded_companies=excl_companies,
        excluded_titles=excl_titles,
    )
    result = [job for job in result if passes_hard_constraints(job, constraints)]

    # Presentation layer: on the opening screen (first page), personalise from
    # saved jobs, then de-duplicate and MMR-diversify so the candidate isn't
    # greeted by eight near-identical cards. Deeper pages keep pure relevance
    # order for pagination stability. Tiers are attached for the UI badge.
    if offset == 0:
        saved = await _fetch_saved_job_signals(db, candidate["id"])
        boost_by_saved(result, saved)
        # Hybrid retrieval: fuse the composite (dense-leaning) and the lexical
        # skills signal via RRF so an exceptional direct-skill match isn't buried
        # under a marginally-higher composite. Degrades to overall_score alone
        # when skills_score is absent.
        result = assemble_first_screen(
            result,
            screen_size=min(limit, 8),
            fuse_signals=("overall_score", "skills_score"),
        )
        # Off the serve path: snapshot the screen and generate/persist rationales
        # on a background connection so the feed returns immediately.
        _schedule_rationale_overlay(dict(candidate), [dict(i) for i in result], limit)
        # #33: log impressions for the learned re-ranker. Best-effort — feed
        # latency and correctness never depend on analytics writes.
        try:
            await db.executemany(
                "INSERT INTO public.match_feedback (candidate_id, job_id, event) "
                "VALUES ($1, $2::uuid, 'impression')",
                [(candidate["id"], str(item["job_id"])) for item in result],
            )
        except Exception as exc:
            logger.debug("match_impression_log_failed", error=str(exc)[:200])
    # Strip the internal cache flag before it reaches the response model.
    for item in result:
        item.pop("_rationale_cached", None)
    # Annotate each card with the candidate's matched vs missing skills (same
    # canonical taxonomy as scoring) so the feed shows "N of M skills" at a glance.
    _annotate_skill_match(result, candidate.get("skills"))
    attach_tiers(result)
    return result


def _annotate_skill_match(result: list[dict], candidate_skills: object) -> None:
    """Fill skills_matched / skills_gap on each feed item from the candidate's skills."""
    cand_canon = {canonical_skill(s) for s in (candidate_skills or [])}  # type: ignore[union-attr]
    for item in result:
        job_skills = item.get("skills_required") or []
        item["skills_matched"] = [s for s in job_skills if canonical_skill(s) in cand_canon]
        item["skills_gap"] = [s for s in job_skills if canonical_skill(s) not in cand_canon]


async def _fetch_saved_job_signals(db: asyncpg.Connection, candidate_id) -> list[dict]:
    """Title/company/seniority/city of the candidate's saved jobs — the signal
    `boost_by_saved` uses to surface more of what they've shown interest in."""
    rows = await db.fetch(
        """
        SELECT j.title, j.seniority, j.location_city, co.name AS company_name
        FROM public.saved_jobs sj
        JOIN public.jobs j ON j.id = sj.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE sj.candidate_id = $1::uuid AND j.deleted_at IS NULL
        LIMIT 50
        """,
        candidate_id,
    )
    return [dict(r) for r in rows]


# Holds references to fire-and-forget rationale tasks so they aren't GC'd.
_rationale_tasks: set[asyncio.Task] = set()


def _schedule_rationale_overlay(candidate: dict, items: list[dict], limit: int) -> None:
    """Generate + persist match rationales OFF the request path.

    The feed must never block on an LLM call. We snapshot the opening screen and
    run the overlay on its own pooled connection; the rationales persist to
    match_scores and surface (from cache) on the candidate's next load.
    """

    async def _run() -> None:
        try:
            from hireloop_api.deps import get_db_pool

            pool = await get_db_pool(get_settings())
            async with pool.acquire() as bg_db:
                await _overlay_llm_rationale(bg_db, items, candidate=candidate, limit=limit)
        except Exception as exc:  # never surface background failures
            logger.warning("bg_rationale_overlay_failed", error=str(exc)[:200])

    task = asyncio.create_task(_run())
    _rationale_tasks.add(task)
    task.add_done_callback(_rationale_tasks.discard)


async def _overlay_llm_rationale(
    db: asyncpg.Connection, result: list[dict], *, candidate: dict, limit: int
) -> None:
    """
    Best-effort: replace the rule-based `explanation` on the opening screen with
    Aarya's personalised, evidence-based one-liner. Opt-in via
    MATCH_RATIONALE_ENABLED; any failure leaves the existing explanations intact.

    Rationales are PERSISTED to match_scores (HIR-20): items that already carry a
    fresh cached rationale are skipped, and newly generated ones are written back
    so subsequent loads serve them from the DB instead of re-calling the LLM.
    """
    cfg = get_settings()
    if not (cfg.match_rationale_enabled and cfg.openrouter_api_key):
        return

    # Only spend LLM calls on items without a fresh cached rationale.
    pending = [item for item in result if not item.get("_rationale_cached")]
    if not pending:
        return

    try:
        reasons = await generate_match_rationales(
            candidate, pending, settings=cfg, max_jobs=min(limit, 8)
        )
    except Exception as exc:  # never let rationale enrichment break the feed
        logger.warning("match_feed_rationale_overlay_failed", error=str(exc)[:300])
        return

    fresh: list[tuple[str, str]] = []
    for item in result:
        reason = reasons.get(str(item.get("job_id")))
        if reason:
            item["explanation"] = reason
            item["_rationale_cached"] = True
            fresh.append((str(item["job_id"]), reason))

    if fresh:
        await _persist_rationales(db, str(candidate["id"]), fresh)


async def _persist_rationales(
    db: asyncpg.Connection, candidate_id: str, updates: list[tuple[str, str]]
) -> None:
    """Write generated rationales back to match_scores. Best-effort, never raises."""
    try:
        await db.executemany(
            "UPDATE public.match_scores SET llm_rationale = $1, llm_rationale_at = NOW() "
            "WHERE candidate_id = $2::uuid AND job_id = $3::uuid",
            [(reason, candidate_id, job_id) for job_id, reason in updates],
        )
    except Exception as exc:  # caching is an optimisation, not correctness
        logger.warning("match_rationale_persist_failed", error=str(exc)[:300])


class MatchFeedCountResponse(BaseModel):
    total: int


@router.get("/count", response_model=MatchFeedCountResponse)
async def get_match_feed_count(
    min_score: float = Query(
        # Relevance floor: by default the candidate feed hides weak/wrong-function
        # matches (e.g. a 5% RevOps role for a UX designer). The frontend can pass
        # min_score=0 for an explicit "show everything" view. Tune as needed.
        default=DEFAULT_FEED_MIN_SCORE,
        ge=0.0,
        le=1.0,
        description="Minimum overall score filter (default relevance floor)",
    ),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Total job matches for the candidate (same rules as GET /matches)."""
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.current_title, c.current_company, c.headline, c.summary,
               c.years_experience, c.skills,
               c.location_city, c.location_state, c.expected_ctc_min, c.expected_ctc_max,
               c.remote_preference, c.open_to_relocation, c.location_scope,
               c.aarya_state, c.market,
               (
                   SELECT cp.target_titles
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS target_titles
        FROM public.candidates c
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    remote_pref = normalize_remote_preference(candidate.get("remote_preference"))
    market = normalize_market(candidate.get("market"))
    if not candidate.get("market"):
        market = await fetch_candidate_market(db, candidate["id"])

    cached_rows = await _fetch_cached_match_rows(
        db,
        candidate_id=candidate["id"],
        min_score=min_score,
        limit=100,
        offset=0,
        remote_preference=remote_pref,
        market=market,
    )
    total = len(
        _serialize_current_quality_cached_rows(
            cached_rows,
            candidate=dict(candidate),
            min_score=min_score,
        )
    )

    if total == 0:
        engine = MatchingEngine(db)
        scored = await engine.score_candidate(str(candidate["id"]), limit=50)
        logger.info(
            "match_feed_count_live_scored",
            candidate_id=str(candidate["id"]),
            scored=scored,
        )
        if scored:
            cached_rows = await _fetch_cached_match_rows(
                db,
                candidate_id=candidate["id"],
                min_score=min_score,
                limit=100,
                offset=0,
                remote_preference=remote_pref,
                market=market,
            )
            total = len(
                _serialize_current_quality_cached_rows(
                    cached_rows,
                    candidate=dict(candidate),
                    min_score=min_score,
                )
            )

    if total == 0:
        # No real scored matches above the floor. Fall back to the quick lexical
        # pool, but cap it at a believable number — the old limit=500 reported the
        # whole active-job pool as "matches", which read as fake. 50 aligns with
        # the feed's page size so the count matches what the candidate can browse.
        fallback = await _fetch_fallback_match_rows(
            db,
            candidate=dict(candidate),
            min_score=min_score,
            limit=50,
            offset=0,
            remote_preference=remote_pref,
            market=market,
        )
        total = len(fallback)

    return {"total": total}


async def _count_cached_match_rows(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    min_score: float,
    remote_preference: str = "any",
    market: str = "IN",
) -> int:
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$3")
    val = await db.fetchval(
        f"""
        SELECT COUNT(*)::int
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        WHERE ms.candidate_id = $1::uuid
          AND ms.overall_score >= $2
          AND j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND j.expires_at > NOW()
          {remote_clause}
        """,
        candidate_id,
        min_score,
        market,
    )
    return int(val or 0)


async def _fetch_cached_match_rows(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    min_score: float,
    limit: int,
    offset: int,
    remote_preference: str = "any",
    market: str = "IN",
) -> list[asyncpg.Record]:
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$5")
    return await db.fetch(
        f"""
        SELECT
            ms.job_id,
            j.title,
            co.name          AS company_name,
            j.location_city,
            j.location_state,
            j.is_remote,
            j.employment_type,
            j.seniority,
            j.ctc_min,
            j.ctc_max,
            j.salary_currency,
            j.skills_required,
            j.description,
            j.apply_url,
            ms.overall_score,
            ms.skills_score,
            ms.experience_score,
            ms.location_score,
            ms.ctc_score,
            ms.explanation,
            ms.llm_rationale,
            ms.llm_rationale_at,
            ms.computed_at,
            -- Action-state: surface what the candidate (or Aarya) has already done
            -- for this role, so an acted-on match no longer looks untouched.
            EXISTS (
                SELECT 1 FROM public.job_application_kits k
                WHERE k.candidate_id = ms.candidate_id AND k.job_id = ms.job_id
            ) AS has_kit,
            (
                SELECT ir.status FROM public.intro_requests ir
                WHERE ir.candidate_id = ms.candidate_id AND ir.job_id = ms.job_id
                ORDER BY ir.created_at DESC LIMIT 1
            ) AS intro_status
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ms.candidate_id = $1::uuid
          AND ms.overall_score >= $2
          AND j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND j.expires_at > NOW()
          {remote_clause}
        ORDER BY ms.overall_score * (
            -- Freshness decay (#27), applied at serve time so the stored score
            -- stays a pure "fit" signal: small boost for jobs scraped <72h ago,
            -- gentle penalty after 14d, stronger after 30d. Recruiter-posted
            -- jobs (scraped_at NULL) are treated as fresh.
            CASE
                WHEN j.scraped_at IS NULL THEN 1.0
                WHEN j.scraped_at > NOW() - INTERVAL '72 hours' THEN 1.05
                WHEN j.scraped_at > NOW() - INTERVAL '14 days' THEN 1.0
                WHEN j.scraped_at > NOW() - INTERVAL '30 days' THEN 0.92
                ELSE 0.85
            END
        ) DESC
        LIMIT $3 OFFSET $4
        """,
        candidate_id,
        min_score,
        limit,
        offset,
        market,
    )


# Maps the latest intro_requests.status to a candidate-facing feed label.
_INTRO_STATUS_LABELS = {
    "pending": "Intro requested",
    "enriching": "Intro requested",
    "drafting": "Intro requested",
    "sent": "Intro sent",
    "opened": "Intro opened",
    "replied": "HM replied",
    "declined": "Intro declined",
    "cancelled": None,  # treat as no active action
}


def _action_state(*, has_kit: bool, intro_status: str | None) -> tuple[str | None, str | None]:
    """Return (state, label) describing what's already been done for this role.

    Intro progress takes precedence over a prepared kit, since it's the later
    step in the apply funnel. Returns (None, None) when nothing actionable.
    """
    if intro_status:
        label = _INTRO_STATUS_LABELS.get(intro_status)
        if label:
            return "intro", label
    if has_kit:
        return "kit_ready", "Kit ready"
    return None, None


def _serialize_cached_match_row(row: asyncpg.Record | dict) -> dict:
    data = dict(row)
    # A cached LLM rationale is usable only if it was generated AFTER the latest
    # score (otherwise the row was re-scored and the rationale may be stale).
    llm = data.pop("llm_rationale", None)
    llm_at = data.pop("llm_rationale_at", None)
    has_kit = bool(data.pop("has_kit", False))
    intro_status = data.pop("intro_status", None)
    computed_at = data["computed_at"]
    fresh = bool(llm) and (llm_at is None or computed_at is None or llm_at >= computed_at)

    action_state, action_label = _action_state(has_kit=has_kit, intro_status=intro_status)

    item = {
        **data,
        "job_id": str(row["job_id"]),
        "skills_required": row["skills_required"] or [],
        "computed_at": computed_at.isoformat() if computed_at else None,
        "action_state": action_state,
        "action_label": action_label,
        # Internal flag (stripped before the response): True when a fresh LLM
        # rationale is already cached, so the overlay can skip regenerating it.
        "_rationale_cached": fresh,
    }
    if fresh:
        item["explanation"] = llm
    return item


def _serialize_current_quality_cached_rows(
    rows: list[asyncpg.Record],
    *,
    candidate: dict,
    min_score: float,
) -> list[dict]:
    """Serialize cached match_scores only if they still pass current quality gates.

    Cached scores can predate domain-fit fixes. Re-check the job/candidate pair at
    serve time so stale rows like hotel sales for a staffing-SaaS GTM profile do
    not remain visible until the next full recompute.
    """
    result: list[dict] = []
    for row in rows:
        current = _current_quality_score(row, candidate=candidate)
        if current is None or current["overall"] < min_score:
            continue
        result.append(_serialize_cached_match_row(row))
    return result


def _candidate_quality_row(candidate: dict) -> dict:
    return {
        "full_name": candidate.get("full_name"),
        "current_title": candidate.get("current_title"),
        "current_company": candidate.get("current_company"),
        "headline": candidate.get("headline"),
        "summary": candidate.get("summary"),
        "years_experience": candidate.get("years_experience"),
        "skills": list(candidate.get("skills") or []),
        "expected_ctc_min": candidate.get("expected_ctc_min"),
        "expected_ctc_max": candidate.get("expected_ctc_max"),
        "location_city": candidate.get("location_city"),
        "location_state": candidate.get("location_state"),
        "remote_preference": candidate.get("remote_preference"),
        "open_to_relocation": bool(candidate.get("open_to_relocation")),
        "location_scope": candidate.get("location_scope"),
        "target_titles": list(candidate.get("target_titles") or []),
    }


def _job_quality_row(row_dict: dict) -> dict:
    return {
        "title": row_dict.get("title"),
        "company_name": row_dict.get("company_name"),
        "description": row_dict.get("description"),
        "seniority": row_dict.get("seniority"),
        "skills_required": list(row_dict.get("skills_required") or []),
        "is_remote": bool(row_dict.get("is_remote")),
        "location_city": row_dict.get("location_city"),
        "location_state": row_dict.get("location_state"),
        "ctc_min": row_dict.get("ctc_min"),
        "ctc_max": row_dict.get("ctc_max"),
    }


def _current_quality_score(row: asyncpg.Record | dict, *, candidate: dict) -> dict | None:
    row_dict = dict(row)
    cand_row = _candidate_quality_row(candidate)
    job_row = _job_quality_row(row_dict)
    score = _assemble_score(cand_row, job_row, embed_skills_sim=None, embed_profile_sim=None)
    if not should_persist_match(cand_row, job_row, score):
        return None
    return score


async def _fetch_fallback_match_rows(
    db: asyncpg.Connection,
    *,
    candidate: dict,
    min_score: float,
    limit: int,
    offset: int,
    remote_preference: str = "any",
    market: str = "IN",
) -> list[dict]:
    """
    Return visible jobs even before the precomputed scoring pipeline is ready.
    This keeps the feed useful immediately after resume upload or voice onboarding.
    """
    candidate_skills = [str(s).lower() for s in (candidate.get("skills") or [])]
    current_title = candidate.get("current_title")
    rows_to_rank = max(100, limit + offset)
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$4")
    rows = await db.fetch(
        f"""
        SELECT
            j.id AS job_id,
            j.title,
            co.name AS company_name,
            j.location_city,
            j.location_state,
            j.is_remote,
            j.employment_type,
            j.seniority,
            j.ctc_min,
            j.ctc_max,
            j.salary_currency,
            j.skills_required,
            j.description,
            j.apply_url,
            j.scraped_at,
            COALESCE(
                (
                  SELECT count(*)
                  FROM unnest(j.skills_required) skill
                  WHERE lower(skill) = ANY($1::text[])
                ),
                0
            ) AS skills_overlap
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND j.expires_at > NOW()
          {remote_clause}
        ORDER BY
          skills_overlap DESC,
          CASE
            WHEN $2::text IS NOT NULL
             AND j.title ILIKE '%' || $2::text || '%'
            THEN 1 ELSE 0
          END DESC,
          j.scraped_at DESC
        LIMIT $3
        """,
        candidate_skills,
        current_title,
        rows_to_rank,
        market,
    )

    ranked = [
        item
        for row in rows
        if (item := _serialize_fallback_match_row(row, candidate=candidate)) is not None
    ]
    # Order by the computed score (career-path + skill aware), not just the SQL
    # ordering, so aspirational target-title matches surface.
    ranked.sort(key=lambda r: r["overall_score"], reverse=True)
    filtered = [row for row in ranked if row["overall_score"] >= min_score]
    return filtered[offset : offset + limit]


def _serialize_fallback_match_row(row: asyncpg.Record | dict, *, candidate: dict) -> dict | None:
    row_dict = dict(row)
    job_skills = list(row_dict.get("skills_required") or [])
    cand_row = _candidate_quality_row(candidate)
    job_row = _job_quality_row(row_dict)
    score = _assemble_score(cand_row, job_row, embed_skills_sim=None, embed_profile_sim=None)
    if not should_persist_match(cand_row, job_row, score):
        return None

    return {
        "job_id": str(row_dict["job_id"]),
        "title": row_dict["title"],
        "company_name": row_dict.get("company_name"),
        "location_city": row_dict.get("location_city"),
        "location_state": row_dict.get("location_state"),
        "is_remote": bool(row_dict.get("is_remote")),
        "employment_type": row_dict.get("employment_type"),
        "seniority": row_dict.get("seniority"),
        "ctc_min": row_dict.get("ctc_min"),
        "ctc_max": row_dict.get("ctc_max"),
        "skills_required": job_skills,
        "apply_url": row_dict.get("apply_url"),
        "overall_score": score["overall"],
        "skills_score": round(score["skills_sim"], 4),
        "experience_score": round(score["exp_score"], 4),
        "location_score": round(score["loc_score"], 4),
        "ctc_score": round(score["ctc_score"], 4),
        "explanation": f"{score['explanation']} Aarya is still finalising your full ranking.",
        "computed_at": datetime.now(UTC).isoformat(),
    }


# ── Single match score ────────────────────────────────────────────────────────


@router.get("/{job_id}", response_model=MatchedJob)
async def get_single_match(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Get (or compute on-the-fly) the match score for the current candidate and a
    specific job. Used by the Aarya get_match_score tool.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid job ID") from exc

    candidate = await db.fetchrow(
        "SELECT id, skills FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    market = await fetch_candidate_market(db, candidate["id"])
    vis = job_visible_for_market_sql(market_param="$3")

    # Full detail SELECT — includes description/requirements/scraped_at so the
    # candidate gets the whole posting inline (no need to leave the app).
    detail_cols = """
            ms.job_id, j.title, co.name AS company_name,
            j.location_city, j.location_state, j.is_remote,
            j.employment_type, j.seniority,
            j.ctc_min, j.ctc_max, j.salary_currency, j.skills_required, j.apply_url,
            j.description, j.requirements, j.scraped_at,
            ms.overall_score, ms.skills_score, ms.experience_score,
            ms.location_score, ms.ctc_score, ms.explanation, ms.computed_at
    """
    row = await db.fetchrow(
        f"""
        SELECT {detail_cols}
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ms.candidate_id = $1::uuid
          AND ms.job_id = $2::uuid
          AND j.is_active = TRUE
          AND {vis}
        """,
        candidate["id"],
        job_uuid,
        market,
    )

    if not row:
        # Compute on-the-fly (slow path — no embedding available yet)
        engine = MatchingEngine(db)
        score = await engine.score_pair(str(candidate["id"]), job_id)
        if score is None:
            raise HTTPException(status_code=404, detail="Job not found or scoring failed")
        row = await db.fetchrow(
            f"""
            SELECT {detail_cols}
            FROM public.match_scores ms
            JOIN public.jobs j ON j.id = ms.job_id
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE ms.candidate_id = $1::uuid AND ms.job_id = $2::uuid
            """,
            candidate["id"],
            job_uuid,
        )
        if not row:
            # Score was computed but fell below the persist threshold, so it's not
            # in match_scores. Return the live computed result instead of 500 so
            # the job detail page always renders.
            job_row = await db.fetchrow(
                """
                SELECT j.id AS job_id, j.title, co.name AS company_name,
                       j.location_city, j.location_state, j.is_remote,
                       j.employment_type, j.seniority, j.ctc_min, j.ctc_max, j.salary_currency,
                       j.skills_required, j.apply_url, j.description,
                       j.requirements, j.scraped_at
                FROM public.jobs j
                LEFT JOIN public.companies co ON co.id = j.company_id
                WHERE j.id = $1::uuid AND j.is_active = TRUE AND j.deleted_at IS NULL
                """,
                job_uuid,
            )
            if not job_row:
                raise HTTPException(status_code=404, detail="Job not found")
            full_cand = await db.fetchrow(
                """
                SELECT id, skills, current_title, years_experience,
                       location_city, location_state
                FROM public.candidates WHERE id = $1::uuid
                """,
                candidate["id"],
            )
            computed = _serialize_fallback_match_row(dict(job_row), candidate=dict(full_cand or {}))
            job_skills_live = job_row["skills_required"] or []
            cand_canon_live = {canonical_skill(s) for s in (candidate["skills"] or [])}
            scraped_live = job_row["scraped_at"]
            return {
                **computed,
                "description": job_row.get("description"),
                "requirements": job_row.get("requirements"),
                "posted_at": scraped_live.isoformat() if scraped_live else None,
                "skills_matched": [
                    s for s in job_skills_live if canonical_skill(s) in cand_canon_live
                ],
                "skills_gap": [
                    s for s in job_skills_live if canonical_skill(s) not in cand_canon_live
                ],
            }

    # Split required skills into "you have" vs "gap" using the shared canonical
    # taxonomy, so the score breakdown is actionable (this is what powers the
    # "Skills gap detected" line — now it shows WHICH skills).
    job_skills = row["skills_required"] or []
    cand_canon = {canonical_skill(s) for s in (candidate["skills"] or [])}
    matched = [s for s in job_skills if canonical_skill(s) in cand_canon]
    gap = [s for s in job_skills if canonical_skill(s) not in cand_canon]
    scraped = row["scraped_at"]

    return {
        **dict(row),
        "job_id": str(row["job_id"]),
        "skills_required": job_skills,
        "skills_matched": matched,
        "skills_gap": gap,
        "posted_at": scraped.isoformat() if scraped else None,
        "computed_at": row["computed_at"].isoformat(),
    }


# ── Admin: embed all pending ──────────────────────────────────────────────────


@router.post("/embed", response_model=EmbedResponse, status_code=202)
async def trigger_embed(
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> EmbedResponse:
    """
    Admin endpoint — embed all candidates and jobs that are missing vectors.
    Runs via durable background_jobs queue. Auth: X-Service-Secret.
    """
    _require_service_secret(x_service_secret, settings)

    from hireloop_api.services.background_jobs import MATCH_EMBED_ALL, enqueue_job

    await enqueue_job(db, kind=MATCH_EMBED_ALL, payload={})
    return EmbedResponse(status="queued")


# ── Admin: recompute all match scores ─────────────────────────────────────────


@router.post("/recompute", response_model=RecomputeResponse, status_code=202)
async def trigger_recompute(
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> RecomputeResponse:
    """
    Admin endpoint — recompute all match scores from scratch.
    Called nightly by pg_cron after embedding refresh.
    Auth: X-Service-Secret.
    """
    _require_service_secret(x_service_secret, settings)

    from hireloop_api.services.background_jobs import MATCH_RECOMPUTE_ALL, enqueue_job

    await enqueue_job(db, kind=MATCH_RECOMPUTE_ALL, payload={})
    return RecomputeResponse(status="queued")


# ── Inline: embed + score a single candidate ──────────────────────────────────


@router.post("/embed/candidate/{candidate_id}", status_code=202)
async def embed_candidate_inline(
    candidate_id: str,
    x_service_secret: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Immediately embed a single candidate and score them against active jobs.
    Auth: X-Service-Secret (called from API backend, not from frontend).
    """
    _require_service_secret(x_service_secret, settings)

    from hireloop_api.services.background_jobs import MATCH_EMBED_CANDIDATE, enqueue_job

    await enqueue_job(
        db,
        kind=MATCH_EMBED_CANDIDATE,
        payload={"candidate_id": candidate_id},
        idempotency_key=f"match_embed_candidate:{candidate_id}",
    )
    return {"status": "queued", "candidate_id": candidate_id}
