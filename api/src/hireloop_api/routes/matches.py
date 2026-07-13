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
import json
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
from hireloop_api.services.candidate_intelligence import load_candidate_intelligence
from hireloop_api.services.job_preferences import (
    extract_negative_preferences,
    normalize_remote_preference,
    remote_filter_sql,
)
from hireloop_api.services.job_present import resolve_company_logo_url
from hireloop_api.services.job_relevance_pipeline import (
    filter_and_rerank_jobs,
    rationale_overlay_items,
)
from hireloop_api.services.job_visibility import LIVE_JOB_VISIBLE_SQL
from hireloop_api.services.match_audit import audit_match_quality
from hireloop_api.services.match_quality import (
    DEFAULT_FEED_MIN_SCORE,
    MIN_PERSIST_SCORE,
    should_persist_match,
)
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
    dedupe_jobs,
    passes_hard_constraints,
)
from hireloop_api.services.skills import canonical_skill
from hireloop_api.services.test_jobs import (
    append_test_jobs,
    ensure_test_match_scores,
    fetch_test_jobs_for_feed,
    is_test_job,
    test_jobs_company_sql_exclude,
    test_jobs_enabled,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/matches", tags=["matches"])

# Per-candidate locks so a fresh candidate's first feed load scores exactly once,
# even when several requests race right after signup (see get_match_feed).
_first_score_locks: dict[str, asyncio.Lock] = {}
_MIN_MARKET_FEED_JOBS = 8
_FEED_SCORE_LIMIT = 500
# Floor for brand-new signups while embeddings/scores are still computing.
_STARTER_FEED_MIN_SCORE = 0.25
# Live surfaces only: not expired + scraped within freshness window (or recruiter).
_LIVE_JOB_VISIBLE_SQL = LIVE_JOB_VISIBLE_SQL


def _is_test_match_row(row: asyncpg.Record | dict) -> bool:
    data = dict(row)
    return is_test_job(
        {
            "company_name": data.get("company_name"),
            "company_domain": data.get("company_domain"),
            "recruiter_email": data.get("recruiter_email"),
        }
    )


def _market_match_rows(rows: list[asyncpg.Record]) -> list[asyncpg.Record]:
    return [row for row in rows if not _is_test_match_row(row)]


def _market_feed_items(items: list[dict]) -> list[dict]:
    return [item for item in items if not is_test_job(item)]


def _merge_feed_results(
    primary: list[dict],
    supplemental: list[dict],
    *,
    limit: int,
) -> list[dict]:
    seen = {str(item["job_id"]) for item in primary}
    merged = list(primary)
    for item in supplemental:
        job_id = str(item["job_id"])
        if job_id in seen:
            continue
        seen.add(job_id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _unique_nonempty(values: list[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _join_text(*values: object) -> str:
    return " ".join(_unique_nonempty(list(values)))


async def _candidate_with_intelligence(
    db: asyncpg.Connection,
    candidate: asyncpg.Record | dict,
) -> dict:
    """Merge canonical candidate intelligence into the feed candidate row.

    The feed still runs without this layer, but when the saved memory/goals/resume
    snapshot is available it should influence relevance filtering before jobs are
    hidden.
    """
    base = dict(candidate)
    try:
        snapshot = await load_candidate_intelligence(db, base["id"])
    except Exception as exc:
        logger.warning(
            "match_feed_candidate_intelligence_failed",
            candidate_id=str(base.get("id")),
            error=str(exc)[:300],
        )
        return base
    if snapshot is None:
        return base

    ctx = snapshot.for_job_search()
    enriched = dict(base)
    primary_titles = _unique_nonempty(
        [
            enriched.get("prioritized_title"),
            *(enriched.get("target_titles") or []),
            enriched.get("looking_for"),
            *ctx.primary_titles,
            enriched.get("current_title"),
        ]
    )
    if primary_titles:
        enriched["prioritized_title"] = primary_titles[0]
        enriched["target_titles"] = primary_titles
        enriched["looking_for"] = enriched.get("looking_for") or primary_titles[0]

    enriched["skills"] = _unique_nonempty([*(enriched.get("skills") or []), *ctx.skills])
    enriched["market"] = ctx.hard_filters.market or enriched.get("market")
    enriched["remote_preference"] = ctx.hard_filters.remote_preference or enriched.get(
        "remote_preference"
    )
    enriched["location_scope"] = ctx.hard_filters.location_scope or enriched.get("location_scope")
    if ctx.hard_filters.ctc_floor is not None:
        enriched["expected_ctc_min"] = ctx.hard_filters.ctc_floor

    # aarya_state is stored as JSONB, but older rows / migrations can contain
    # shapes that are not a plain dict (e.g. serialized strings, or objects).
    # Never let this crash the match feed.
    raw_state = enriched.get("aarya_state")
    if raw_state is None:
        state: dict[str, object] = {}
    elif isinstance(raw_state, dict):
        state = dict(raw_state)
    elif isinstance(raw_state, str):
        try:
            parsed = json.loads(raw_state)
            state = parsed if isinstance(parsed, dict) else {}
        except Exception:
            state = {}
    elif hasattr(raw_state, "model_dump"):
        try:
            dumped = raw_state.model_dump()  # pydantic v2 models
            state = dumped if isinstance(dumped, dict) else {}
        except Exception:
            state = {}
    else:
        try:
            state = dict(raw_state)  # best-effort for mapping-like objects
        except Exception:
            state = {}

    raw_negative = state.get("negative_preferences")
    if raw_negative is None:
        negative: dict[str, object] = {}
    elif isinstance(raw_negative, dict):
        negative = dict(raw_negative)
    elif isinstance(raw_negative, str):
        try:
            parsed = json.loads(raw_negative)
            negative = parsed if isinstance(parsed, dict) else {}
        except Exception:
            negative = {}
    elif hasattr(raw_negative, "model_dump"):
        try:
            dumped = raw_negative.model_dump()
            negative = dumped if isinstance(dumped, dict) else {}
        except Exception:
            negative = {}
    else:
        try:
            negative = dict(raw_negative)
        except Exception:
            negative = {}
    negative["companies"] = _unique_nonempty(
        [
            *(negative.get("companies") or []),
            *ctx.negative_preferences.companies,
            *ctx.hard_filters.excluded_companies,
        ]
    )
    negative["titles"] = _unique_nonempty(
        [
            *(negative.get("titles") or []),
            *ctx.negative_preferences.titles,
            *ctx.hard_filters.excluded_titles,
        ]
    )
    if negative["companies"] or negative["titles"]:
        state["negative_preferences"] = negative
        enriched["aarya_state"] = state

    if ctx.memory_summary and ctx.memory_summary not in str(enriched.get("summary") or ""):
        enriched["summary"] = _join_text(enriched.get("summary"), ctx.memory_summary)
    if ctx.desired_industry:
        enriched["summary"] = _join_text(enriched.get("summary"), ctx.desired_industry)
    enriched["candidate_intelligence_sources"] = ctx.source_inventory
    return enriched


async def _supplement_market_feed(
    db: asyncpg.Connection,
    *,
    candidate: dict,
    candidate_id: uuid.UUID,
    result: list[dict],
    min_score: float,
    limit: int,
    remote_preference: str,
    market: str,
) -> list[dict]:
    """Fill a thin market feed from cached scores, then lexical fallback."""
    if len(result) >= limit:
        return result
    for floor in (min_score, MIN_PERSIST_SCORE):
        cached = await _fetch_cached_match_rows(
            db,
            candidate_id=candidate_id,
            min_score=floor,
            limit=limit,
            offset=0,
            remote_preference=remote_preference,
            market=market,
        )
        serialized = _market_feed_items(
            _serialize_current_quality_cached_rows(
                cached,
                candidate=candidate,
                min_score=floor,
            )
        )
        result = _merge_feed_results(result, serialized, limit=limit)
        if len(result) >= limit:
            return result
        fallback = await _fetch_fallback_match_rows(
            db,
            candidate=candidate,
            min_score=floor,
            limit=limit,
            offset=0,
            remote_preference=remote_preference,
            market=market,
            relaxed=floor <= MIN_PERSIST_SCORE,
        )
        result = _merge_feed_results(result, _market_feed_items(fallback), limit=limit)
        if len(result) >= limit:
            break
    if len(result) < limit:
        relaxed = await _fetch_fallback_match_rows(
            db,
            candidate=candidate,
            min_score=_STARTER_FEED_MIN_SCORE,
            limit=limit,
            offset=0,
            remote_preference=remote_preference,
            market=market,
            relaxed=True,
        )
        result = _merge_feed_results(result, _market_feed_items(relaxed), limit=limit)
    if len(result) < limit:
        starter = await _fetch_starter_market_jobs(
            db,
            candidate_id=candidate_id,
            limit=limit,
            remote_preference=remote_preference,
            market=market,
        )
        result = _merge_feed_results(result, starter, limit=limit)
    return result


async def _enqueue_candidate_match_scoring(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
) -> None:
    """Kick off embed+score in the background — never block the feed HTTP response."""
    if not hasattr(db, "fetchval"):
        return
    try:
        from hireloop_api.services.background_jobs import MATCH_EMBED_CANDIDATE, enqueue_job

        await enqueue_job(
            db,
            kind=MATCH_EMBED_CANDIDATE,
            payload={"candidate_id": str(candidate_id)},
            idempotency_key=f"match_embed_feed:{candidate_id}",
        )
    except Exception as exc:
        logger.debug(
            "match_score_enqueue_failed", candidate_id=str(candidate_id), error=str(exc)[:200]
        )


# ── Auth helper ───────────────────────────────────────────────────────────────


def _require_service_secret(x_service_secret: str | None, settings: Settings) -> None:
    if not x_service_secret or x_service_secret != settings.service_secret:
        raise HTTPException(status_code=403, detail="Invalid or missing service secret")


# ── Response models ───────────────────────────────────────────────────────────


class MatchedJob(BaseModel):
    job_id: str
    title: str
    company_name: str | None
    company_logo_url: str | None = None
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
    culture_score: float | None = None
    career_alignment_score: float | None = None
    fit_recommendation: str | None = None
    salary_benchmark: dict | None = None
    triage_notes: str | None = None
    explanation: str | None
    # None for pool jobs not yet scored for this candidate (LEFT JOIN) — a
    # required str here turned that into a response-validation 500.
    computed_at: str | None = None
    # Retention: jobs the candidate hasn't been shown before.
    is_new_for_you: bool = False
    is_new_since_visit: bool = False
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    # Skill detail: which required skills the candidate has vs is missing.
    skills_matched: list[str] = []
    skills_gap: list[str] = []
    # Presentation layer (services.ranking) — confidence badge for the UI.
    tier: str | None = None
    tier_label: str | None = None
    # Backend-only transparency metadata; optional so older clients can ignore it.
    match_diagnostics: dict | None = None


class RecomputeResponse(BaseModel):
    status: str
    candidates_processed: int = 0
    total_pairs_scored: int = 0
    elapsed_seconds: float = 0.0


class EmbedResponse(BaseModel):
    status: str
    embedded: int = 0
    failed: int = 0


class FindNewJobsResponse(BaseModel):
    jobs: list[MatchedJob]
    refreshing: bool = False
    excluded_count: int = 0
    message: str | None = None


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
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    only_new: bool = Query(
        default=False,
        description="When true, return only jobs the candidate has never been shown",
    ),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """
    Return the current candidate's ranked job matches, best first.
    Only active jobs in the candidate's market with unexpired match scores are returned.
    """
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.current_title, c.current_company, c.looking_for, c.headline, c.summary,
               c.years_experience, c.skills,
               c.location_city, c.location_state, c.expected_ctc_min, c.expected_ctc_max,
               c.remote_preference, c.open_to_relocation, c.location_scope,
               c.aarya_state, c.market,
               c.last_visit_at,
               (
                   SELECT cp.target_titles
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS target_titles,
               (
                   SELECT cp.prioritized_title
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS prioritized_title
        FROM public.candidates c
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")
    candidate = await _candidate_with_intelligence(db, candidate)

    settings = get_settings()
    remote_pref = normalize_remote_preference(candidate.get("remote_preference"))
    market = normalize_market(candidate.get("market"))
    if not candidate.get("market"):
        market = await fetch_candidate_market(db, candidate["id"])

    await ensure_test_match_scores(
        db,
        str(candidate["id"]),
        market=market,
        remote_preference="any",
        settings=settings,
    )

    if offset == 0 and settings.apify_token and hasattr(db, "fetchval"):
        apify_jobs = await db.fetchval(
            f"""
            SELECT count(*)::int
            FROM public.jobs j
            WHERE j.source = 'google_jobs'
              AND j.is_active = TRUE
              AND j.deleted_at IS NULL
              AND {_LIVE_JOB_VISIBLE_SQL}
            """
        )
        if int(apify_jobs or 0) < 20:
            from hireloop_api.services.background_jobs import (
                AARYA_AUTO_INGEST,
                enqueue_job,
            )

            await enqueue_job(
                db,
                kind=AARYA_AUTO_INGEST,
                payload={"candidate_id": str(candidate["id"]), "force_refresh": True},
                idempotency_key=f"aarya_auto_ingest:{candidate['id']}",
            )

    if offset == 0 and settings.openrouter_api_key and hasattr(db, "fetchval"):
        unembedded = await db.fetchval(
            """
            SELECT count(*)::int
            FROM public.jobs j
            LEFT JOIN public.job_embeddings je ON je.job_id = j.id
            WHERE j.is_active = TRUE
              AND j.deleted_at IS NULL
              AND je.job_id IS NULL
              AND j.source IN ('google_jobs', 'ats')
            """
        )
        if int(unembedded or 0) > 0:
            from hireloop_api.services.background_jobs import (
                MATCH_EMBED_CANDIDATE,
                enqueue_job,
            )

            await enqueue_job(
                db,
                kind=MATCH_EMBED_CANDIDATE,
                payload={"candidate_id": str(candidate["id"])},
                idempotency_key=f"match_embed_feed:{candidate['id']}",
            )

    rows = await _fetch_cached_match_rows(
        db,
        candidate_id=candidate["id"],
        min_score=min_score,
        limit=limit,
        offset=offset,
        remote_preference=remote_pref,
        market=market,
        only_new=only_new,
    )

    if not _market_match_rows(rows) and offset == 0:
        # Single-flight: concurrent first-page requests must not each enqueue a
        # background score job. Never block on embed+score here — that can take
        # minutes and leaves the Matches sidebar on skeleton loaders.
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
                only_new=only_new,
            )
            if not _market_match_rows(rows):
                await _enqueue_candidate_match_scoring(db, candidate["id"])
        _first_score_locks.pop(str(candidate["id"]), None)

    last_visit = candidate.get("last_visit_at")
    result = _market_feed_items(
        _serialize_current_quality_cached_rows(
            rows,
            candidate=dict(candidate),
            min_score=min_score,
            last_visit_at=last_visit,
        )
    )
    if not result:
        result = await _supplement_market_feed(
            db,
            candidate=dict(candidate),
            candidate_id=candidate["id"],
            result=[],
            min_score=min_score,
            limit=limit,
            remote_preference=remote_pref,
            market=market,
        )
    elif len(result) < limit:
        result = await _supplement_market_feed(
            db,
            candidate=dict(candidate),
            candidate_id=candidate["id"],
            result=result,
            min_score=min_score,
            limit=limit,
            remote_preference=remote_pref,
            market=market,
        )

    if offset == 0 and len(result) < limit:
        await _enqueue_candidate_match_scoring(db, candidate["id"])
        if len(result) < limit:
            result = await _supplement_market_feed(
                db,
                candidate=dict(candidate),
                candidate_id=candidate["id"],
                result=result,
                min_score=MIN_PERSIST_SCORE,
                limit=limit,
                remote_preference=remote_pref,
                market=market,
            )

    if offset == 0 and len(result) < 3:
        starter = await _fetch_starter_market_jobs(
            db,
            candidate_id=candidate["id"],
            limit=limit,
            remote_preference=remote_pref,
            market=market,
        )
        result = _merge_feed_results(result, starter, limit=limit)

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
    result = [
        job
        for job in result
        if (test_jobs_enabled(settings) and is_test_job(job))
        or (not is_test_job(job) and passes_hard_constraints(job, constraints))
    ]
    result = filter_and_rerank_jobs(dict(candidate), result, limit=limit)
    # Always collapse near-duplicates (same apply URL / company+title). The default
    # Matches sidebar uses limit=50, which used to skip assemble_first_screen and
    # therefore skipped dedupe entirely.
    result = dedupe_jobs(result)

    # Presentation layer: on the opening screen (first page), personalise from
    # saved jobs, then MMR-diversify so the candidate isn't greeted by eight
    # near-identical cards. Deeper pages keep pure relevance order for
    # pagination stability. Tiers are attached for the UI badge.
    if offset == 0:
        saved = await _fetch_saved_job_signals(db, candidate["id"])
        boost_by_saved(result, saved, output_key="_ranking_score")
        # Short curated screens get MMR diversity; longer feeds keep SQL order
        # (newest matches first) so the sidebar can show ~50 recent roles.
        if limit <= 20:
            # Hybrid retrieval: fuse the composite (dense-leaning) and the lexical
            # skills signal via RRF so an exceptional direct-skill match isn't buried
            # under a marginally-higher composite. Degrades to overall_score alone
            # when skills_score is absent. Dedupe already ran above; assemble still
            # re-dedupes harmlessly before MMR.
            result = assemble_first_screen(
                result,
                screen_size=min(limit, 10),
                fuse_signals=(
                    "_ranking_score" if saved else "overall_score",
                    "skills_score",
                ),
            )
        market_count = len(_market_feed_items(result))
        if market_count < 3 and test_jobs_enabled(settings):
            test_jobs = await fetch_test_jobs_for_feed(
                db,
                market=market,
                remote_preference="any",
            )
            result = append_test_jobs(result, test_jobs, limit=limit)
        # Off the serve path: snapshot the screen and generate/persist rationales
        # on a background connection so the feed returns immediately.
        _schedule_rationale_overlay(
            dict(candidate),
            rationale_overlay_items(result, limit=limit),
            limit,
        )
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
        item.pop("_ranking_score", None)
    # Annotate each card with the candidate's matched vs missing skills (same
    # canonical taxonomy as scoring) so the feed shows "N of M skills" at a glance.
    _annotate_skill_match(result, candidate.get("skills"))
    attach_tiers(result)

    # Retention: mark which jobs are new for this candidate and persist impressions.
    # Best-effort: the feed should never fail due to analytics/retention writes.
    try:
        job_ids = [str(item.get("job_id") or "") for item in result]
        job_uuids = [uuid.UUID(jid) for jid in job_ids if jid]
        seen_map: dict[str, object] = {}
        if job_uuids:
            seen_rows = await db.fetch(
                """
                SELECT job_id::text, first_seen_at
                FROM public.candidate_job_impressions
                WHERE candidate_id = $1::uuid
                  AND job_id = ANY($2::uuid[])
                """,
                candidate["id"],
                job_uuids,
            )
            seen_map = {str(r["job_id"]): r["first_seen_at"] for r in seen_rows}
        for item in result:
            jid = str(item.get("job_id") or "")
            first_seen = seen_map.get(jid)
            item["is_new_for_you"] = jid not in seen_map
            item["first_seen_at"] = (
                first_seen.isoformat() if hasattr(first_seen, "isoformat") else None
            )
            if "is_new_since_visit" not in item:
                lv = candidate.get("last_visit_at")
                if lv is None:
                    item["is_new_since_visit"] = jid not in seen_map
                else:
                    ct_raw = item.get("computed_at")
                    try:
                        ct = (
                            datetime.fromisoformat(str(ct_raw).replace("Z", "+00:00"))
                            if ct_raw
                            else None
                        )
                        item["is_new_since_visit"] = bool(ct and ct > lv)
                    except (TypeError, ValueError):
                        item["is_new_since_visit"] = False
        if job_uuids:
            await db.execute(
                """
                INSERT INTO public.candidate_job_impressions (candidate_id, job_id, source)
                SELECT $1::uuid, jid, 'matches'
                FROM unnest($2::uuid[]) AS jid
                ON CONFLICT (candidate_id, job_id) DO UPDATE
                SET last_seen_at = NOW(),
                    seen_count = public.candidate_job_impressions.seen_count + 1,
                    source = EXCLUDED.source,
                    updated_at = NOW()
                """,
                candidate["id"],
                job_uuids,
            )
    except Exception as exc:
        logger.debug("candidate_job_impressions_upsert_failed", error=str(exc)[:200])
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
    items = rationale_overlay_items(items, limit=limit)
    if not items:
        return

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
    pending = [
        item
        for item in rationale_overlay_items(result, limit=limit)
        if not item.get("_rationale_cached")
    ]
    if not pending:
        return

    try:
        reasons = await generate_match_rationales(
            candidate, pending, settings=cfg, max_jobs=min(limit, 10)
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
    settings = get_settings()
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
    candidate = await _candidate_with_intelligence(db, candidate)

    remote_pref = normalize_remote_preference(candidate.get("remote_preference"))
    market = normalize_market(candidate.get("market"))
    if not candidate.get("market"):
        market = await fetch_candidate_market(db, candidate["id"])

    await ensure_test_match_scores(
        db,
        str(candidate["id"]),
        market=market,
        remote_preference="any",
        settings=settings,
    )

    cached_rows = await _fetch_cached_match_rows(
        db,
        candidate_id=candidate["id"],
        min_score=min_score,
        limit=100,
        offset=0,
        remote_preference=remote_pref,
        market=market,
    )
    market_items = _market_feed_items(
        _serialize_current_quality_cached_rows(
            cached_rows,
            candidate=dict(candidate),
            min_score=min_score,
        )
    )
    market_items = dedupe_jobs(
        filter_and_rerank_jobs(dict(candidate), market_items, limit=100)
    )
    total = len(market_items)

    if total == 0:
        await _enqueue_candidate_match_scoring(db, candidate["id"])
        fallback = await _fetch_fallback_match_rows(
            db,
            candidate=dict(candidate),
            min_score=min_score,
            limit=50,
            offset=0,
            remote_preference=remote_pref,
            market=market,
            relaxed=min_score <= MIN_PERSIST_SCORE,
        )
        total = len(
            dedupe_jobs(
                filter_and_rerank_jobs(dict(candidate), _market_feed_items(fallback), limit=50)
            )
        )
        if total == 0 and min_score > MIN_PERSIST_SCORE:
            relaxed = await _fetch_fallback_match_rows(
                db,
                candidate=dict(candidate),
                min_score=MIN_PERSIST_SCORE,
                limit=50,
                offset=0,
                remote_preference=remote_pref,
                market=market,
                relaxed=True,
            )
            total = len(
                dedupe_jobs(
                    filter_and_rerank_jobs(dict(candidate), _market_feed_items(relaxed), limit=50)
                )
            )
        if total == 0:
            relaxed = await _fetch_fallback_match_rows(
                db,
                candidate=dict(candidate),
                min_score=_STARTER_FEED_MIN_SCORE,
                limit=50,
                offset=0,
                remote_preference=remote_pref,
                market=market,
                relaxed=True,
            )
            total = len(
                dedupe_jobs(
                    filter_and_rerank_jobs(dict(candidate), _market_feed_items(relaxed), limit=50)
                )
            )
        if total == 0:
            starter = await _fetch_starter_market_jobs(
                db,
                candidate_id=candidate["id"],
                limit=50,
                remote_preference=remote_pref,
                market=market,
            )
            total = len(
                dedupe_jobs(filter_and_rerank_jobs(dict(candidate), starter, limit=50))
            )

    test_jobs = await fetch_test_jobs_for_feed(
        db,
        market=market,
        remote_preference="any",
    )
    if test_jobs and test_jobs_enabled(settings):
        total = max(total, len(test_jobs))

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
          AND {_LIVE_JOB_VISIBLE_SQL}
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
    only_new: bool = False,
) -> list[asyncpg.Record]:
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$5")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")
    only_new_clause = "AND cji.first_seen_at IS NULL" if only_new else ""
    return await db.fetch(
        f"""
        SELECT
            ms.job_id,
            j.title,
            co.name          AS company_name,
            co.logo_url      AS company_logo_url,
            co.domain        AS company_domain,
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
            ms.culture_score,
            ms.career_alignment_score,
            ms.fit_recommendation,
            ms.salary_benchmark,
            ms.triage_notes,
            ms.explanation,
            ms.llm_rationale,
            ms.llm_rationale_at,
            ms.computed_at,
            j.scraped_at,
            cji.first_seen_at,
            cji.last_seen_at,
            -- Action-state: surface what the candidate (or Aarya) has already done
            -- for this role, so an acted-on match no longer looks untouched.
            EXISTS (
                SELECT 1 FROM public.job_application_kits k
                WHERE k.candidate_id = ms.candidate_id AND k.job_id = ms.job_id
            ) AS has_kit,
            (
                SELECT ja.status FROM public.job_applications ja
                WHERE ja.candidate_id = ms.candidate_id AND ja.job_id = ms.job_id
                ORDER BY ja.applied_at DESC LIMIT 1
            ) AS application_status,
            (
                SELECT ir.status FROM public.intro_requests ir
                WHERE ir.candidate_id = ms.candidate_id AND ir.job_id = ms.job_id
                ORDER BY ir.created_at DESC LIMIT 1
            ) AS intro_status
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.candidate_job_impressions cji
          ON cji.candidate_id = ms.candidate_id AND cji.job_id = ms.job_id
        WHERE ms.candidate_id = $1::uuid
          AND ms.overall_score >= $2
          AND j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND {_LIVE_JOB_VISIBLE_SQL}
          {remote_clause}
          {company_exclude}
          {only_new_clause}
        ORDER BY
            (cji.first_seen_at IS NULL) DESC,
            COALESCE(j.scraped_at, j.created_at) DESC NULLS LAST,
            ms.overall_score * (
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


async def _fetch_match_history_rows(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    min_score: float,
    limit: int,
    offset: int,
    remote_preference: str = "any",
    market: str = "IN",
) -> list[asyncpg.Record]:
    """All scored or previously-shown jobs for a candidate, newest activity first.

    Unlike the live feed, history keeps expired/inactive postings so past matches
    remain visible after a scrape cycle ages them out. Keys come from match_scores
    OR chat/feed impressions so roles Aarya showed in chat survive refresh even
    when the batch scorer never wrote a row.
    """
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$5")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")
    return await db.fetch(
        f"""
        SELECT
            keys.job_id,
            j.title,
            co.name          AS company_name,
            co.logo_url      AS company_logo_url,
            co.domain        AS company_domain,
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
            COALESCE(ms.overall_score, 0.55) AS overall_score,
            ms.skills_score,
            ms.experience_score,
            ms.location_score,
            ms.ctc_score,
            ms.culture_score,
            ms.career_alignment_score,
            ms.fit_recommendation,
            ms.salary_benchmark,
            ms.triage_notes,
            ms.explanation,
            ms.llm_rationale,
            ms.llm_rationale_at,
            COALESCE(ms.computed_at, cji.first_seen_at, cji.last_seen_at, j.scraped_at) AS computed_at,
            j.scraped_at,
            cji.first_seen_at,
            cji.last_seen_at,
            EXISTS (
                SELECT 1 FROM public.job_application_kits k
                WHERE k.candidate_id = $1::uuid AND k.job_id = keys.job_id
            ) AS has_kit,
            (
                SELECT ja.status FROM public.job_applications ja
                WHERE ja.candidate_id = $1::uuid AND ja.job_id = keys.job_id
                ORDER BY ja.applied_at DESC LIMIT 1
            ) AS application_status,
            (
                SELECT ir.status FROM public.intro_requests ir
                WHERE ir.candidate_id = $1::uuid AND ir.job_id = keys.job_id
                ORDER BY ir.created_at DESC LIMIT 1
            ) AS intro_status
        FROM (
            SELECT candidate_id, job_id
            FROM public.match_scores
            WHERE candidate_id = $1::uuid
            UNION
            SELECT candidate_id, job_id
            FROM public.candidate_job_impressions
            WHERE candidate_id = $1::uuid
        ) keys
        JOIN public.jobs j ON j.id = keys.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.match_scores ms
          ON ms.candidate_id = keys.candidate_id AND ms.job_id = keys.job_id
        LEFT JOIN public.candidate_job_impressions cji
          ON cji.candidate_id = keys.candidate_id AND cji.job_id = keys.job_id
        WHERE COALESCE(ms.overall_score, 0.55) >= $2
          AND {vis}
          AND j.deleted_at IS NULL
          {remote_clause}
          {company_exclude}
        ORDER BY
            COALESCE(cji.last_seen_at, cji.first_seen_at, ms.computed_at) DESC NULLS LAST,
            COALESCE(ms.overall_score, 0.55) DESC
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


_APPLICATION_STATUS_LABELS = {
    "applied": "Applied",
    "screening": "In screening",
    "interview": "Interview",
    "offer": "Offer",
    "hired": "Hired",
    "rejected": "Not selected",
    "withdrawn": "Withdrawn",
}


def _action_state(
    *,
    has_kit: bool,
    intro_status: str | None,
    application_status: str | None = None,
) -> tuple[str | None, str | None]:
    """Return (state, label) describing what's already been done for this role.

    Intro progress takes precedence over a prepared kit, since it's the later
    step in the apply funnel. Returns (None, None) when nothing actionable.
    """
    if intro_status:
        label = _INTRO_STATUS_LABELS.get(intro_status)
        if label:
            return "intro", label
    if application_status:
        label = _APPLICATION_STATUS_LABELS.get(application_status, "Applied")
        return "applied", label
    if has_kit:
        return "kit_ready", "Kit ready"
    return None, None


def _serialize_cached_match_row(
    row: asyncpg.Record | dict,
    *,
    candidate: dict | None = None,
    current_quality: dict | None = None,
    last_visit_at: datetime | None = None,
) -> dict:
    data = dict(row)
    first_seen = data.get("first_seen_at")
    last_seen = data.get("last_seen_at")
    # A cached LLM rationale is usable only if it was generated AFTER the latest
    # score (otherwise the row was re-scored and the rationale may be stale).
    llm = data.pop("llm_rationale", None)
    llm_at = data.pop("llm_rationale_at", None)
    has_kit = bool(data.pop("has_kit", False))
    intro_status = data.pop("intro_status", None)
    application_status = data.pop("application_status", None)
    computed_at = data["computed_at"]
    fresh = bool(llm) and (llm_at is None or computed_at is None or llm_at >= computed_at)

    action_state, action_label = _action_state(
        has_kit=has_kit,
        intro_status=intro_status,
        application_status=application_status,
    )

    computed_ts = computed_at
    scraped_ts = data.get("scraped_at")
    fresh_ts = computed_ts
    if scraped_ts and (fresh_ts is None or scraped_ts > fresh_ts):
        fresh_ts = scraped_ts
    is_new_since_visit = False
    if last_visit_at is None:
        is_new_since_visit = first_seen is None
    elif fresh_ts is not None and hasattr(fresh_ts, "timestamp"):
        is_new_since_visit = fresh_ts > last_visit_at

    item = {
        **data,
        "job_id": str(row["job_id"]),
        "skills_required": row["skills_required"] or [],
        "computed_at": computed_at.isoformat() if computed_at else None,
        "first_seen_at": first_seen.isoformat() if hasattr(first_seen, "isoformat") else None,
        "last_seen_at": last_seen.isoformat() if hasattr(last_seen, "isoformat") else None,
        "is_new_for_you": first_seen is None,
        "is_new_since_visit": is_new_since_visit,
        "action_state": action_state,
        "action_label": action_label,
        # Internal flag (stripped before the response): True when a fresh LLM
        # rationale is already cached, so the overlay can skip regenerating it.
        "_rationale_cached": fresh,
    }
    if fresh:
        item["explanation"] = llm
    if candidate is not None:
        cand_row = _candidate_quality_row(candidate)
        job_row = _job_quality_row(data)
        quality = current_quality or {"overall": float(data.get("overall_score") or 0.0)}
        item["match_diagnostics"] = audit_match_quality(
            cand_row,
            job_row,
            quality,
        ).model_dump(mode="json")
    return item


def _serialize_history_rows(
    rows: list[asyncpg.Record],
    *,
    candidate: dict,
    min_score: float,
    last_visit_at: datetime | None = None,
) -> list[dict]:
    """Serialize past matches from stored scores — do not re-gate on live title fit.

    Job history is a log of what the candidate already saw. Re-running
    should_persist_match against a newly prioritized title would hide those
    rows and make Matches look empty even when match_scores exist.
    """
    result: list[dict] = []
    for row in rows:
        stored = row.get("overall_score")
        if stored is None:
            continue
        overall = float(stored)
        if overall < min_score:
            continue
        result.append(
            _serialize_cached_match_row(
                row,
                candidate=candidate,
                current_quality={"overall": overall},
                last_visit_at=last_visit_at,
            )
        )
    return result


def _serialize_current_quality_cached_rows(
    rows: list[asyncpg.Record],
    *,
    candidate: dict,
    min_score: float,
    last_visit_at: datetime | None = None,
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
        result.append(
            _serialize_cached_match_row(
                row,
                candidate=candidate,
                current_quality=current,
                last_visit_at=last_visit_at,
            )
        )
    return result


def _candidate_quality_row(candidate: dict) -> dict:
    return {
        "full_name": candidate.get("full_name"),
        "current_title": candidate.get("current_title"),
        "current_company": candidate.get("current_company"),
        "looking_for": candidate.get("looking_for"),
        "prioritized_title": candidate.get("prioritized_title"),
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
    stored = row_dict.get("overall_score")
    if stored is not None:
        result = {"overall": float(stored)}
    else:
        result = _assemble_score(cand_row, job_row, embed_skills_sim=None, embed_profile_sim=None)
    if not should_persist_match(cand_row, job_row, result):
        return None
    return result


async def _candidate_has_resume(db: asyncpg.Connection, candidate_id: uuid.UUID) -> bool:
    return bool(
        await db.fetchval(
            """
            SELECT EXISTS(
              SELECT 1 FROM public.resumes
              WHERE candidate_id = $1::uuid
            )
            """,
            candidate_id,
        )
    )


async def _fetch_starter_market_jobs(
    db: asyncpg.Connection,
    *,
    candidate_id: uuid.UUID,
    limit: int,
    remote_preference: str = "any",
    market: str = "IN",
) -> list[dict]:
    """
    Last-resort feed for fresh signups: show recent market jobs once a CV is on
    file, even when parsing produced sparse fields and scoring is still running.
    """
    if not await _candidate_has_resume(db, candidate_id):
        return []

    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$2")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")
    rows = await db.fetch(
        f"""
        SELECT
            j.id AS job_id,
            j.title,
            co.name AS company_name,
            co.logo_url AS company_logo_url,
            co.domain AS company_domain,
            j.location_city,
            j.location_state,
            j.is_remote,
            j.employment_type,
            j.seniority,
            j.ctc_min,
            j.ctc_max,
            j.salary_currency,
            j.skills_required,
            j.apply_url,
            j.scraped_at
        FROM public.jobs j
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND {_LIVE_JOB_VISIBLE_SQL}
          {remote_clause}
          {company_exclude}
        ORDER BY j.scraped_at DESC NULLS LAST, j.created_at DESC
        LIMIT $1
        """,
        limit,
        market,
    )

    now = datetime.now(UTC).isoformat()
    items: list[dict] = []
    for row in rows:
        row_dict = dict(row)
        if is_test_job(row_dict):
            continue
        items.append(
            {
                "job_id": str(row_dict["job_id"]),
                "title": row_dict["title"],
                "company_name": row_dict.get("company_name"),
                "company_logo_url": resolve_company_logo_url(row_dict),
                "location_city": row_dict.get("location_city"),
                "location_state": row_dict.get("location_state"),
                "is_remote": bool(row_dict.get("is_remote")),
                "employment_type": row_dict.get("employment_type"),
                "seniority": row_dict.get("seniority"),
                "ctc_min": row_dict.get("ctc_min"),
                "ctc_max": row_dict.get("ctc_max"),
                "skills_required": list(row_dict.get("skills_required") or []),
                "apply_url": row_dict.get("apply_url"),
                "overall_score": 0.36,
                "skills_score": None,
                "experience_score": None,
                "location_score": None,
                "ctc_score": None,
                "explanation": (
                    "Starter match from your market — Aarya is still ranking roles against your CV."
                ),
                "computed_at": now,
            }
        )
    return items


async def _fetch_fallback_match_rows(
    db: asyncpg.Connection,
    *,
    candidate: dict,
    min_score: float,
    limit: int,
    offset: int,
    remote_preference: str = "any",
    market: str = "IN",
    relaxed: bool = False,
) -> list[dict]:
    """
    Return visible jobs even before the precomputed scoring pipeline is ready.
    This keeps the feed useful immediately after resume upload or voice onboarding.
    """
    candidate_skills = [str(s).lower() for s in (candidate.get("skills") or [])]
    title_probe = (
        candidate.get("prioritized_title")
        or candidate.get("looking_for")
        or candidate.get("current_title")
    )
    rows_to_rank = max(100, limit + offset)
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$4")
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")
    rows = await db.fetch(
        f"""
        SELECT
            j.id AS job_id,
            j.title,
            co.name AS company_name,
            co.logo_url AS company_logo_url,
            co.domain AS company_domain,
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
          AND {_LIVE_JOB_VISIBLE_SQL}
          {remote_clause}
          {company_exclude}
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
        title_probe,
        rows_to_rank,
        market,
    )

    ranked = [
        item
        for row in rows
        if (item := _serialize_fallback_match_row(row, candidate=candidate, relaxed=relaxed))
        is not None
    ]
    # Order by the computed score (career-path + skill aware), not just the SQL
    # ordering, so aspirational target-title matches surface.
    ranked.sort(key=lambda r: r["overall_score"], reverse=True)
    filtered = [row for row in ranked if row["overall_score"] >= min_score and not is_test_job(row)]
    return filtered[offset : offset + limit]


def _serialize_fallback_match_row(
    row: asyncpg.Record | dict,
    *,
    candidate: dict,
    relaxed: bool = False,
    allow_low_score: bool = False,
) -> dict | None:
    row_dict = dict(row)
    job_skills = list(row_dict.get("skills_required") or [])
    cand_row = _candidate_quality_row(candidate)
    job_row = _job_quality_row(row_dict)
    score = _assemble_score(cand_row, job_row, embed_skills_sim=None, embed_profile_sim=None)
    if allow_low_score:
        pass
    elif relaxed:
        if float(score.get("overall") or 0.0) < 0.25:
            return None
    elif not should_persist_match(cand_row, job_row, score):
        return None

    audit = audit_match_quality(cand_row, job_row, score).model_dump(mode="json")
    return {
        "job_id": str(row_dict["job_id"]),
        "title": row_dict["title"],
        "company_name": row_dict.get("company_name"),
        "company_logo_url": resolve_company_logo_url(row_dict),
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
        "match_diagnostics": audit,
    }


# ── Triage shortlist (/rank) ───────────────────────────────────────────────────


@router.get("/triage", response_model=list[MatchedJob])
async def get_match_triage(
    limit: int = Query(default=10, ge=1, le=20),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """Aarya's ranked top picks — apply / stretch / skip with per-job notes."""
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.current_title, c.current_company, c.looking_for, c.headline, c.summary,
               c.years_experience, c.skills,
               c.location_city, c.location_state, c.expected_ctc_min, c.expected_ctc_max,
               c.remote_preference, c.open_to_relocation, c.location_scope,
               c.aarya_state, c.market, c.profile_enrichment,
               (
                   SELECT cp.target_titles
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS target_titles,
               (
                   SELECT cp.prioritized_title
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS prioritized_title
        FROM public.candidates c
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")
    candidate = await _candidate_with_intelligence(db, candidate)

    market = await fetch_candidate_market(db, candidate["id"])
    rows = await _fetch_cached_match_rows(
        db,
        candidate_id=candidate["id"],
        min_score=0.35,
        limit=limit * 3,
        offset=0,
        remote_preference="any",
        market=market,
    )
    serialized = _serialize_current_quality_cached_rows(
        rows,
        candidate=dict(candidate),
        min_score=0.35,
    )
    # Prefer apply, then stretch; skip last.
    order = {"apply": 0, "stretch": 1, "skip": 2}
    serialized.sort(
        key=lambda r: (
            order.get(str(r.get("fit_recommendation") or "stretch"), 1),
            -(r.get("overall_score") or 0),
        )
    )
    picks = [r for r in serialized if r.get("fit_recommendation") != "skip"][:limit]
    if len(picks) < min(3, limit):
        picks = serialized[:limit]
    return picks[:limit]


# ── Job history + find-new ─────────────────────────────────────────────────────


async def _resolve_match_candidate(
    db: asyncpg.Connection,
    user_id: uuid.UUID,
) -> asyncpg.Record:
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.current_title, c.current_company, c.looking_for, c.headline, c.summary,
               c.years_experience, c.skills,
               c.location_city, c.location_state, c.expected_ctc_min, c.expected_ctc_max,
               c.remote_preference, c.open_to_relocation, c.location_scope,
               c.aarya_state, c.market,
               c.last_visit_at,
               (
                   SELECT cp.target_titles
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS target_titles,
               (
                   SELECT cp.prioritized_title
                   FROM public.career_paths cp
                   WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                   ORDER BY cp.created_at DESC
                   LIMIT 1
               ) AS prioritized_title
        FROM public.candidates c
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        user_id,
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Complete your profile first")
    return await _candidate_with_intelligence(db, candidate)


@router.get("/history", response_model=list[MatchedJob])
async def get_match_history(
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    """Full job match history for the candidate, newest activity first."""
    candidate = await _resolve_match_candidate(db, uuid.UUID(current_user["id"]))
    market = normalize_market(candidate.get("market"))
    if not candidate.get("market"):
        market = await fetch_candidate_market(db, candidate["id"])
    remote_pref = normalize_remote_preference(candidate.get("remote_preference"))

    rows = await _fetch_match_history_rows(
        db,
        candidate_id=candidate["id"],
        min_score=min_score,
        limit=limit,
        offset=offset,
        remote_preference=remote_pref,
        market=market,
    )
    return _market_feed_items(
        _serialize_history_rows(
            rows,
            candidate=dict(candidate),
            min_score=min_score,
            last_visit_at=candidate.get("last_visit_at"),
        )
    )


@router.post("/find-new", response_model=FindNewJobsResponse)
async def find_new_matches(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Surface jobs the candidate has never been shown, and queue a fresh scrape +
    re-score so more new roles arrive without repeating prior matches.
    """
    settings = get_settings()
    candidate = await _resolve_match_candidate(db, uuid.UUID(current_user["id"]))
    market = normalize_market(candidate.get("market"))
    if not candidate.get("market"):
        market = await fetch_candidate_market(db, candidate["id"])
    remote_pref = normalize_remote_preference(candidate.get("remote_preference"))

    excluded_count = int(
        await db.fetchval(
            """
            SELECT COUNT(*)::int
            FROM public.candidate_job_impressions
            WHERE candidate_id = $1::uuid
            """,
            candidate["id"],
        )
        or 0
    )

    if settings.apify_token and hasattr(db, "fetchval"):
        from hireloop_api.services.background_jobs import (
            AARYA_AUTO_INGEST,
            CAREER_PATH_INGEST,
            enqueue_job,
        )

        # Dedicated find-new keys so a soft idle ingest cannot block a hard refresh.
        await enqueue_job(
            db,
            kind=AARYA_AUTO_INGEST,
            payload={"candidate_id": str(candidate["id"]), "force_refresh": True},
            idempotency_key=f"aarya_auto_ingest:find_new:{candidate['id']}",
        )
        path_row = await db.fetchrow(
            """
            SELECT id FROM public.career_paths
            WHERE candidate_id = $1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC LIMIT 1
            """,
            candidate["id"],
        )
        if path_row is not None:
            await enqueue_job(
                db,
                kind=CAREER_PATH_INGEST,
                payload={
                    "candidate_id": str(candidate["id"]),
                    "derive_from_candidate": True,
                    "force_refresh": True,
                    "user_id": current_user["id"],
                },
                idempotency_key=f"career_path_ingest:find_new:{candidate['id']}",
            )

    await _enqueue_candidate_match_scoring(db, candidate["id"])

    rows = await _fetch_cached_match_rows(
        db,
        candidate_id=candidate["id"],
        min_score=DEFAULT_FEED_MIN_SCORE,
        limit=20,
        offset=0,
        remote_preference=remote_pref,
        market=market,
        only_new=True,
    )
    jobs = _market_feed_items(
        _serialize_current_quality_cached_rows(
            rows,
            candidate=dict(candidate),
            min_score=DEFAULT_FEED_MIN_SCORE,
            last_visit_at=candidate.get("last_visit_at"),
        )
    )

    # Never fall back to already-seen roles — Find new must only surface unseen jobs.
    # Background ingest above keeps searching; the client polls while refreshing=True.
    if jobs:
        message = f"Found {len(jobs)} new role{'s' if len(jobs) != 1 else ''}."
    elif excluded_count > 0:
        message = (
            "No new roles yet — searching fresh openings now. "
            "Check back in a minute (we won’t re-show jobs you’ve already seen)."
        )
    else:
        message = "Searching for new roles — check back in a minute."
    return {
        "jobs": jobs,
        "refreshing": len(jobs) < 3,
        "excluded_count": excluded_count,
        "message": message,
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
            co.logo_url AS company_logo_url, co.domain AS company_domain,
            j.location_city, j.location_state, j.is_remote,
            j.employment_type, j.seniority,
            j.ctc_min, j.ctc_max, j.salary_currency, j.skills_required, j.apply_url,
            j.description, j.requirements, j.scraped_at,
            ms.overall_score, ms.skills_score, ms.experience_score,
            ms.location_score, ms.ctc_score,
            ms.culture_score, ms.career_alignment_score, ms.fit_recommendation,
            ms.salary_benchmark, ms.triage_notes,
            ms.explanation, ms.computed_at
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
                       co.logo_url AS company_logo_url, co.domain AS company_domain,
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
