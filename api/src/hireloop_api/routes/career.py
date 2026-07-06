"""
Career path routes.

GET  /api/v1/career/path            → current candidate's latest career path (or null)
POST /api/v1/career/path/generate   → (re)generate the path from the profile
POST /api/v1/career/path/find-jobs  → find jobs along the path

find-jobs strategy ("search existing + background top-up"):
  1. Immediately return jobs already in the DB that best fit the path's target
     roles (scored for this candidate, path-matching titles first).
  2. Fire a background Apify scrape scoped to the path's target titles + the
     candidate's city, then re-score this candidate so the feed gets fresher
     within a minute or two.
"""

from __future__ import annotations

import uuid
from typing import Any

import asyncpg
import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_db_pool, get_phone_verified_user
from hireloop_api.market_db import fetch_candidate_market
from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.routes.matches import MatchedJob, _serialize_cached_match_row
from hireloop_api.services.career_intelligence import CareerIntelligenceService
from hireloop_api.services.career_path import CareerPathService
from hireloop_api.services.career_path_selection import default_prioritize_title
from hireloop_api.services.matching import MatchingEngine
from hireloop_api.services.rate_limit import check_rate_limit
from hireloop_api.services.test_jobs import (
    ensure_test_match_scores,
    fetch_test_jobs_for_feed,
    prepend_test_jobs,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/career", tags=["career"])


# ── Response models ───────────────────────────────────────────────────────────


class CareerStep(BaseModel):
    title: str
    level: str
    timeframe: str | None = None
    rationale: str | None = None
    skills_to_build: list[str] = []


class CareerPath(BaseModel):
    id: str
    current_role: str | None
    summary: str | None
    steps: list[CareerStep]
    target_titles: list[str]
    target_locations: list[str]
    model: str | None
    prioritized_title: str | None = None
    created_at: str | None
    updated_at: str | None


class PrioritizePathRequest(BaseModel):
    title: str
    # Optional full confirmed set from the kickoff multi-select (preferred
    # first). When present it replaces target_titles so find-jobs and path
    # resumes work off what the candidate actually chose.
    selected_titles: list[str] | None = None


class CareerPathResponse(BaseModel):
    path: CareerPath | None


class FindJobsResponse(BaseModel):
    jobs: list[MatchedJob]
    refreshing: bool
    target_titles: list[str]
    # False only when we returned zero jobs AND the Apify source is unreachable
    # (e.g. missing/expired token) — lets the UI explain the empty state instead
    # of silently showing nothing. True in the normal case.
    source_available: bool = True


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _resolve_candidate_id(db: asyncpg.Connection, user_id: str) -> str:
    row = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Complete your profile first")
    return str(row["id"])


# Prefilter SQL pool before Python title-fit gate (wider net, stricter final filter).
_PATH_JOBS_SQL_PREFILTER_SCORE = 0.45
_PATH_JOBS_SQL_FETCH_MULTIPLIER = 8


async def _fetch_path_jobs(
    db: asyncpg.Connection,
    candidate_id: str,
    target_titles: list[str],
    limit: int,
    *,
    remote_preference: str = "any",
    market: str = "IN",
    prioritized_title: str | None = None,
) -> list[asyncpg.Record]:
    """Scored jobs for this candidate that fit the career path titles."""
    from hireloop_api.services.career_path_jobs import (
        normalize_path_search_titles,
        rank_path_job_rows,
    )
    from hireloop_api.services.job_preferences import remote_filter_sql

    path_titles = normalize_path_search_titles(
        target_titles,
        prioritized_title=prioritized_title,
    )
    if not path_titles:
        return []

    patterns = [f"%{t}%" for t in path_titles]
    remote_clause = remote_filter_sql(remote_preference)
    vis = job_visible_for_market_sql(market_param="$4")
    fetch_limit = min(max(limit * _PATH_JOBS_SQL_FETCH_MULTIPLIER, limit + 10), 120)
    raw = await db.fetch(
        f"""
        SELECT ms.job_id, j.title, co.name AS company_name,
               j.location_city, j.location_state, j.is_remote,
               j.employment_type, j.seniority, j.ctc_min, j.ctc_max,
               j.skills_required, j.apply_url,
               ms.overall_score, ms.skills_score, ms.experience_score,
               ms.location_score, ms.ctc_score, ms.explanation, ms.computed_at
        FROM public.match_scores ms
        JOIN public.jobs j ON j.id = ms.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ms.candidate_id = $1::uuid
          AND j.is_active = TRUE
          AND {vis}
          AND j.deleted_at IS NULL
          AND j.expires_at > NOW()
          {remote_clause}
          AND (
            j.title ILIKE ANY($2::text[])
            OR ms.overall_score >= $5
          )
        ORDER BY ms.overall_score DESC
        LIMIT $3
        """,
        uuid.UUID(candidate_id),
        patterns,
        fetch_limit,
        market,
        _PATH_JOBS_SQL_PREFILTER_SCORE,
    )
    ranked = rank_path_job_rows([dict(r) for r in raw], path_titles, limit=limit)
    return ranked


async def _apify_reachable(settings: Settings) -> bool:
    """
    Cheap read-only check that Apify is usable for the ACTIVE job source (no run,
    no cost). Verifies both that the token is valid AND that the configured
    career-site actor is accessible — so a missing/misconfigured/unavailable
    actor surfaces as "source unavailable" instead of a silently-empty feed
    (previously this only checked the token, not the actor).
    """
    if not settings.apify_token:
        return False
    headers = {"Authorization": f"Bearer {settings.apify_token}"}
    actor_id = (settings.apify_career_site_actor or "").replace("/", "~")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            me = await client.get("https://api.apify.com/v2/users/me", headers=headers)
            if me.status_code != 200:
                return False
            if actor_id:
                act = await client.get(f"https://api.apify.com/v2/acts/{actor_id}", headers=headers)
                if act.status_code != 200:
                    logger.warning(
                        "apify_actor_unavailable", actor=actor_id, status=act.status_code
                    )
                    return False
        return True
    except Exception as exc:
        logger.warning("apify_reachability_probe_failed", error=str(exc))
        return False


async def _ingest_and_rescore(
    settings: Settings,
    candidate_id: str,
    queries: list[str],
    locations: list[str],
) -> None:
    """
    Background task: scrape fresh jobs for the path's roles, then re-score the
    candidate. Acquires its own pooled connection (the request connection is
    already released by the time background tasks run).
    """
    from hireloop_api.services.apify.job_ingester import JobIngester

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        # Ingestion failures propagate: if every job source is down (e.g. an
        # Apify actor whose rental lapsed), ingest() raises and the background
        # job is marked failed + retried — a loud signal, not a silently-empty
        # feed. Scoring is best-effort (a scoring hiccup shouldn't fail the job).
        if settings.apify_token:
            ingester = JobIngester(
                apify_token=settings.apify_token,
                db=conn,
                settings=settings,
                linkedin_actor=settings.apify_linkedin_jobs_actor,
                career_site_actor=settings.apify_career_site_actor,
                enable_career_site=settings.apify_enable_career_site_ingest,
            )
            stats = await ingester.ingest(
                queries=queries or None,
                locations=locations or ["India"],
                max_results_per_query=25,
                # Niche/senior path roles (Head of Growth, Director GTM) are
                # sparse even over a week. The actor only allows 1h/24h/7d/6m, so
                # on-demand career pulls use the widest window (6m) — recall
                # matters more than freshness for these. (Nightly cron stays 24h.)
                time_range="6m",
            )
            logger.info("career_find_jobs_ingest_done", **stats)
        else:
            logger.info("career_find_jobs_ingest_skipped", reason="no_apify_token")

        try:
            engine = MatchingEngine(conn)
            scored = await engine.score_candidate(candidate_id, limit=150)
            logger.info("career_find_jobs_rescored", candidate_id=candidate_id, scored=scored)
        except Exception as exc:  # scoring is best-effort
            logger.error("career_find_jobs_rescore_failed", error=str(exc))


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/path", response_model=CareerPathResponse)
async def get_career_path(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Return the candidate's latest career path, or null if none generated yet."""
    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    path = await CareerPathService.get_latest(db, candidate_id)
    return {"path": path}


@router.post("/path/generate", response_model=CareerPathResponse)
async def generate_career_path(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """(Re)generate the candidate's career path from their profile."""
    # #48: full path generation is a heavy LLM call — cap per user per hour.
    check_rate_limit(str(current_user["id"]), "career_path_generate", max_per_hour=10)
    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    pool = await get_db_pool(settings)
    try:
        path = await CareerPathService.generate(pool, candidate_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"path": path}


@router.post("/path/prioritize", response_model=CareerPathResponse)
async def prioritize_career_path(
    body: PrioritizePathRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Set which career path title the candidate wants to prioritize for job search."""
    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    try:
        path = await CareerPathService.prioritize(
            db, candidate_id, title, selected_titles=body.selected_titles
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path is None:
        raise HTTPException(status_code=404, detail="Generate your career path first.")
    return {"path": path}


@router.post("/path/find-jobs", response_model=FindJobsResponse)
async def find_jobs_for_path(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Find jobs along the candidate's career path. Returns existing matches
    immediately and kicks off a background Apify top-up + re-score.
    """
    candidate_id = await _resolve_candidate_id(db, current_user["id"])

    from hireloop_api.services.job_preferences import normalize_remote_preference

    pref_row = await db.fetchrow(
        "SELECT remote_preference FROM public.candidates WHERE id = $1::uuid",
        uuid.UUID(candidate_id),
    )
    remote_pref = normalize_remote_preference(pref_row["remote_preference"] if pref_row else None)

    path = await CareerPathService.get_latest(db, candidate_id)
    if path is None:
        raise HTTPException(
            status_code=400,
            detail="Generate your career path first.",
        )
    if not path.get("prioritized_title"):
        auto_title = default_prioritize_title(path)
        if auto_title:
            updated = await CareerPathService.prioritize(db, candidate_id, auto_title)
            if updated:
                path = updated
        if not path.get("prioritized_title"):
            raise HTTPException(
                status_code=400,
                detail="Pick one of your top career paths before searching for jobs.",
            )

    target_titles: list[str] = path.get("target_titles") or []
    target_locations: list[str] = path.get("target_locations") or []
    market = await fetch_candidate_market(db, uuid.UUID(candidate_id))
    prioritized = path.get("prioritized_title") or ""

    await ensure_test_match_scores(
        db,
        candidate_id,
        market=market,
        remote_preference="any",
    )

    from hireloop_api.services.background_jobs import CAREER_PATH_INGEST, POOL_INGEST, enqueue_job
    from hireloop_api.services.career_path_jobs import (
        normalize_path_search_titles,
        rank_path_job_rows,
    )
    from hireloop_api.services.career_path_pool import (
        fetch_scored_pool_jobs,
        pool_job_count,
        resolve_definition_for_title,
        score_pool_for_candidate,
    )

    path_search_titles = normalize_path_search_titles(
        target_titles,
        prioritized_title=prioritized,
    )
    definition = await resolve_definition_for_title(db, prioritized, market=market)
    rows: list[dict[str, Any]] = []

    # 1) Shared pool first (senior paths scraped once for all similar candidates).
    if definition is not None:
        pool_rows = await fetch_scored_pool_jobs(
            db,
            candidate_id,
            definition["id"],
            limit=40,
            remote_preference=remote_pref,
            market=market,
        )
        rows = rank_path_job_rows(
            [dict(r) for r in pool_rows],
            path_search_titles,
            limit=20,
        )
        if not rows:
            try:
                await score_pool_for_candidate(db, candidate_id, definition["id"])
            except Exception as exc:
                logger.warning("pool_initial_score_failed", error=str(exc)[:200])
            pool_rows = await fetch_scored_pool_jobs(
                db,
                candidate_id,
                definition["id"],
                limit=40,
                remote_preference=remote_pref,
                market=market,
            )
            rows = rank_path_job_rows(
                [dict(r) for r in pool_rows],
                path_search_titles,
                limit=20,
            )

    # 2) Supplement with per-candidate path matches when the pool is thin.
    if len(rows) < 20:
        extra = await _fetch_path_jobs(
            db,
            candidate_id,
            target_titles,
            limit=20 - len(rows),
            remote_preference=remote_pref,
            market=market,
            prioritized_title=prioritized,
        )
        seen = {str(r["job_id"]) for r in rows}
        for r in extra:
            jid = str(r["job_id"])
            if jid not in seen:
                rows.append(dict(r))
                seen.add(jid)

    # Thin scored coverage → score now so the first click isn't empty (or just
    # the seeded demo jobs: _fetch_path_jobs inner-joins match_scores, so real
    # jobs the candidate was never scored against are invisible until this runs).
    if len(rows) < 5:
        engine = MatchingEngine(db)
        await engine.score_candidate(candidate_id, limit=80)
        rescored = await _fetch_path_jobs(
            db,
            candidate_id,
            target_titles,
            limit=20,
            remote_preference=remote_pref,
            market=market,
            prioritized_title=prioritized,
        )
        seen = {str(r["job_id"]) for r in rows}
        for r in rescored:
            jid = str(r["job_id"])
            if jid not in seen:
                rows.append(dict(r))
                seen.add(jid)

    # If we have nothing to show yet, confirm the upstream source is even
    # reachable so the UI can tell the user "search is unavailable" vs. "no
    # matches right now".
    source_available = True
    if not rows:
        source_available = await _apify_reachable(settings)

    # Background top-up: refresh shared pool for senior paths; per-candidate Apify only
    # when there is no canonical pool or the pool is still too thin.
    pool_min = int(definition["pool_min_jobs"]) if definition is not None else 0
    pool_count = await pool_job_count(db, definition["id"]) if definition is not None else 0

    if definition is not None and pool_count < pool_min:
        await enqueue_job(
            db,
            kind=POOL_INGEST,
            payload={
                "definition_id": str(definition["id"]),
                "candidate_id": candidate_id,
                "locations": target_locations,
            },
            idempotency_key=f"pool_ingest:{definition['slug']}:{market}",
        )
    elif len(rows) < 8:
        await enqueue_job(
            db,
            kind=CAREER_PATH_INGEST,
            payload={
                "candidate_id": candidate_id,
                "queries": path_search_titles or target_titles,
                "locations": target_locations,
            },
            idempotency_key=f"career_path_ingest:{candidate_id}",
        )

    jobs = [_serialize_cached_match_row(r) for r in rows]
    for job in jobs:
        job.pop("_rationale_cached", None)  # internal flag, not part of the API
    test_jobs = await fetch_test_jobs_for_feed(
        db,
        market=market,
        remote_preference="any",
    )
    jobs = prepend_test_jobs(jobs, test_jobs, limit=20)
    return {
        "jobs": jobs,
        "refreshing": source_available,
        "target_titles": target_titles,
        "source_available": source_available,
    }


# ── Career Intelligence (24-layer profile) ───────────────────────────────────


@router.get("/intelligence")
async def get_career_intelligence(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Return the candidate's stored Career Intelligence, or null if not computed."""
    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    intel = await CareerIntelligenceService.get(db, candidate_id)
    live = await CareerIntelligenceService.get_completeness(db, candidate_id)
    if live is not None:
        if intel:
            intel["data_completeness"] = live
        else:
            intel = {"data_completeness": live}
    return {"intelligence": intel}


@router.post("/intelligence/generate")
async def generate_career_intelligence(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    (Re)compute the candidate's full 24-layer Career Intelligence from their
    resume, LinkedIn, and chat data. Synchronous (deliberate "analyze me"
    action); falls back to a deterministic profile if the LLM is unavailable.
    """
    pool = await get_db_pool(settings)
    async with pool.acquire() as db:
        candidate_id = await _resolve_candidate_id(db, current_user["id"])
    try:
        intel = await CareerIntelligenceService.generate(pool, candidate_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"intelligence": intel}


# ── Career-path resumes (one per direction, up to 3) ────────────────────────


@router.get("/path-resumes")
async def list_career_path_resumes(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    from hireloop_api.services.career_path_resume import list_path_resumes

    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    resumes = await list_path_resumes(db, candidate_id)
    return {"resumes": resumes}


@router.post("/path-resumes/generate")
async def generate_career_path_resumes(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    from hireloop_api.services.career_path_resume import generate_path_resumes

    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    check_rate_limit(str(current_user["id"]), "career_path_resumes", max_per_hour=5)
    try:
        resumes = await generate_path_resumes(db, candidate_id, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"resumes": resumes}


@router.get("/path-resumes/{resume_id}/download")
async def download_career_path_resume(
    resume_id: str,
    file_format: str = Query(default="html", pattern="^(html|pdf|docx)$"),
    print_dialog: bool = Query(default=True),
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> Response:
    from hireloop_api.services.career_path_resume import fetch_path_resume_html
    from hireloop_api.services.resume_export import html_resume_to_docx
    from hireloop_api.services.resume_tailor import wrap_print_document

    candidate_id = await _resolve_candidate_id(db, current_user["id"])
    html_fragment, path_title = await fetch_path_resume_html(
        db, resume_id=resume_id, candidate_id=candidate_id
    )
    if not html_fragment:
        raise HTTPException(status_code=404, detail="Resume not found.")

    safe_title = (path_title or "Career path resume").replace("/", "-")[:80]
    doc_title = f"{safe_title} — Resume"

    if file_format == "docx":
        docx_bytes = html_resume_to_docx(html_fragment, title=doc_title)
        filename = f"{safe_title.replace(' ', '_')}.docx"
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    auto_print = file_format == "pdf" or (file_format == "html" and print_dialog)
    html_doc = wrap_print_document(
        html_fragment,
        title=doc_title,
        auto_print=auto_print,
    )
    disposition = "attachment" if file_format == "pdf" else "inline"
    return HTMLResponse(
        content=html_doc,
        headers={"Content-Disposition": f'{disposition}; filename="{safe_title}.html"'},
    )
