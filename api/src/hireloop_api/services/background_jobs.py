"""
Durable background job queue.

Replaces fire-and-forget ``BackgroundTasks`` / ``asyncio.create_task`` for work
that must survive process restarts and be retried on failure.

Claim pattern: ``SELECT … FOR UPDATE SKIP LOCKED`` so multiple API replicas can
poll safely (one winner per row).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings

logger = structlog.get_logger()

# ── Job kinds (stable string identifiers) ─────────────────────────────────────

CAREER_PATH_INGEST = "career_path_ingest"
POOL_INGEST = "pool_ingest"
AARYA_AUTO_INGEST = "aarya_auto_ingest"
RESUME_EMBED_SCORE = "resume_embed_score"
CAREER_INTELLIGENCE_UPDATE = "career_intelligence_update"
CAREER_PATH_UPDATE = "career_path_update"
PROFILE_COMPLETENESS = "profile_completeness"
TAILORED_RESUME = "tailored_resume"
CAREER_PATH_RESUMES = "career_path_resumes"
LEARNING_ROADMAP = "learning_roadmap"
APPLICATION_KIT = "application_kit"
MATCH_EMBED_ALL = "match_embed_all"
MATCH_RECOMPUTE_ALL = "match_recompute_all"
MATCH_EMBED_CANDIDATE = "match_embed_candidate"
JOB_EMBED = "job_embed"
JOB_SCORE = "job_score"
JOB_INGEST = "job_ingest"
LINKDAPI_ENRICH = "linkdapi_enrich"
HM_ENRICH = "hm_enrich"
INTERVIEW_REMINDER = "interview_reminder"
AARYA_WEEKLY_DIGEST = "aarya_weekly_digest"
FIRECRAWL_JD_BACKFILL = "firecrawl_jd_backfill"
FIRECRAWL_COMPANY_INTEL = "firecrawl_company_intel"

Handler = Callable[[Settings, dict[str, Any]], Awaitable[None]]

_BACKOFF_BASE_SECONDS = 30
_BACKOFF_MAX_SECONDS = 900

# User-facing generation must not sit behind multi-minute Apify scrapes.
# claim_next_job orders these ahead of ingest/embed bulk work.
_INTERACTIVE_JOB_KINDS = frozenset(
    {
        APPLICATION_KIT,
        TAILORED_RESUME,
        CAREER_PATH_RESUMES,
        LEARNING_ROADMAP,
    }
)
# Heavy kinds run on the single heavy lane so they cannot block interactive kits.
_HEAVY_JOB_KINDS = frozenset(
    {
        AARYA_AUTO_INGEST,
        CAREER_PATH_INGEST,
        POOL_INGEST,
        JOB_INGEST,
        MATCH_EMBED_ALL,
        MATCH_RECOMPUTE_ALL,
        MATCH_EMBED_CANDIDATE,
        JOB_EMBED,
        JOB_SCORE,
    }
)
_MAX_CONCURRENT_INTERACTIVE = 2


async def enqueue_job(
    db: asyncpg.Connection,
    *,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> uuid.UUID:
    """
    Insert a pending job. When ``idempotency_key`` is set and an active
    (pending/running) job already exists, returns the existing job id.
    """
    when = run_after or datetime.now(UTC)
    if idempotency_key:
        existing = await db.fetchval(
            """
            SELECT id FROM public.background_jobs
            WHERE idempotency_key = $1
              AND status IN ('pending', 'running')
            """,
            idempotency_key,
        )
        if existing:
            return uuid.UUID(str(existing))

    job_id = await db.fetchval(
        """
        INSERT INTO public.background_jobs
          (kind, payload, idempotency_key, run_after, max_attempts)
        VALUES ($1, $2::jsonb, $3, $4, $5)
        RETURNING id
        """,
        kind,
        json.dumps(payload),
        idempotency_key,
        when,
        max_attempts,
    )
    logger.info("background_job_enqueued", job_id=str(job_id), kind=kind)
    return uuid.UUID(str(job_id))


async def claim_next_job(
    db: asyncpg.Connection,
    *,
    worker_id: str,
    kinds: frozenset[str] | None = None,
    exclude_kinds: frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Atomically claim the next runnable job, or None if the queue is empty.

    Interactive kinds (application kits, tailored resumes) are claimed before
    heavy Apify/embed work so the UI 90s poll does not time out while scrapes run.
    """
    # $1 = worker_id, $2 = interactive priority list (ORDER BY), then optional filters.
    args: list[object] = [worker_id, list(_INTERACTIVE_JOB_KINDS)]
    filters = ["status = 'pending'", "run_after <= NOW()"]
    if kinds:
        args.append(list(kinds))
        filters.append(f"kind = ANY(${len(args)}::text[])")
    if exclude_kinds:
        args.append(list(exclude_kinds))
        filters.append(f"kind <> ALL(${len(args)}::text[])")
    where = " AND ".join(filters)
    row = await db.fetchrow(
        f"""
        WITH next AS (
          SELECT id
          FROM public.background_jobs
          WHERE {where}
          ORDER BY
            CASE WHEN kind = ANY($2::text[]) THEN 0 ELSE 1 END,
            run_after ASC,
            created_at ASC
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE public.background_jobs j
        SET status = 'running',
            worker_id = $1,
            started_at = NOW(),
            attempts = j.attempts + 1,
            updated_at = NOW()
        FROM next
        WHERE j.id = next.id
        RETURNING j.id, j.kind, j.payload, j.attempts, j.max_attempts
        """,
        *args,
    )
    if not row:
        return None
    data = dict(row)
    payload = data.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "id": str(data["id"]),
        "kind": data["kind"],
        "payload": payload or {},
        "attempts": int(data["attempts"]),
        "max_attempts": int(data["max_attempts"]),
    }


async def mark_job_completed(db: asyncpg.Connection, job_id: str) -> None:
    await db.execute(
        """
        UPDATE public.background_jobs
        SET status = 'completed',
            completed_at = NOW(),
            last_error = NULL,
            updated_at = NOW()
        WHERE id = $1::uuid
        """,
        uuid.UUID(job_id),
    )


async def mark_job_failed(
    db: asyncpg.Connection,
    job_id: str,
    *,
    error: str,
    attempts: int,
    max_attempts: int,
) -> None:
    """Mark failed; re-queue with backoff when attempts remain."""
    if attempts < max_attempts:
        delay = min(_BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), _BACKOFF_MAX_SECONDS)
        run_after = datetime.now(UTC) + timedelta(seconds=delay)
        await db.execute(
            """
            UPDATE public.background_jobs
            SET status = 'pending',
                worker_id = NULL,
                started_at = NULL,
                last_error = $2,
                run_after = $3,
                updated_at = NOW()
            WHERE id = $1::uuid
            """,
            uuid.UUID(job_id),
            error[:2000],
            run_after,
        )
        logger.warning(
            "background_job_retry_scheduled",
            job_id=job_id,
            attempts=attempts,
            retry_in_seconds=delay,
        )
        return

    await db.execute(
        """
        UPDATE public.background_jobs
        SET status = 'failed',
            last_error = $2,
            completed_at = NOW(),
            updated_at = NOW()
        WHERE id = $1::uuid
        """,
        uuid.UUID(job_id),
        error[:2000],
    )
    logger.error("background_job_failed_permanently", job_id=job_id, error=error[:200])


async def list_background_jobs(
    db: asyncpg.Connection,
    *,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List recent background jobs for admin / ops."""
    clauses = ["1=1"]
    args: list[object] = []
    if status:
        args.append(status)
        clauses.append(f"status = ${len(args)}")
    if kind:
        args.append(kind)
        clauses.append(f"kind = ${len(args)}")
    args.append(min(limit, 200))
    limit_idx = len(args)
    where = " AND ".join(clauses)
    rows = await db.fetch(
        f"""
        SELECT id, kind, status, attempts, max_attempts, last_error,
               idempotency_key, run_after, started_at, completed_at, created_at
        FROM public.background_jobs
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${limit_idx}
        """,
        *args,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        d["id"] = str(d["id"])
        for ts_key in ("run_after", "started_at", "completed_at", "created_at"):
            ts = d.get(ts_key)
            if ts is not None and hasattr(ts, "isoformat"):
                d[ts_key] = ts.isoformat()
        out.append(d)
    return out


# ── Handlers ──────────────────────────────────────────────────────────────────


async def _handle_career_path_ingest(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.routes.career import _ingest_and_rescore, _ingest_candidate_and_rescore

    candidate_id = str(payload["candidate_id"])
    force_refresh = bool(payload.get("force_refresh"))
    locations = list(payload.get("locations") or [])
    if payload.get("derive_from_candidate"):
        await _ingest_candidate_and_rescore(
            settings,
            candidate_id,
            requested_titles=[str(t) for t in list(payload.get("requested_titles") or [])],
            requested_locations=[str(loc) for loc in locations],
            force_refresh=force_refresh,
            user_id=str(payload["user_id"]) if payload.get("user_id") else None,
            session_id=str(payload["session_id"]) if payload.get("session_id") else None,
        )
        return
    queries = list(payload.get("queries") or [])
    await _ingest_and_rescore(
        settings,
        candidate_id,
        [str(query) for query in queries],
        [str(loc) for loc in (locations or ["India"])],
        force_refresh=force_refresh,
    )


async def _handle_pool_ingest(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.career_path_pool import ingest_pool

    await ingest_pool(
        settings,
        definition_id=str(payload["definition_id"]),
        candidate_id=str(payload["candidate_id"]) if payload.get("candidate_id") else None,
        locations=list(payload.get("locations") or ["India"]),
    )


async def _handle_aarya_auto_ingest(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.agents.aarya.tools import _auto_ingest_for_candidate

    candidate_id = str(payload["candidate_id"])
    await _auto_ingest_for_candidate(
        settings,
        candidate_id,
        user_id=str(payload["user_id"]) if payload.get("user_id") else None,
        session_id=str(payload["session_id"]) if payload.get("session_id") else None,
        force_refresh=bool(payload.get("force_refresh")),
    )


async def _handle_resume_embed_score(settings: Settings, payload: dict[str, Any]) -> None:
    if not settings.openrouter_api_key:
        return
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.embeddings import EmbeddingService, InsufficientCreditsError
    from hireloop_api.services.matching import MatchingEngine

    candidate_id = str(payload["candidate_id"])
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        svc = EmbeddingService(api_key=settings.openrouter_api_key, db=conn)
        try:
            try:
                await svc.embed_candidate(candidate_id)
            except InsufficientCreditsError as exc:
                logger.warning(
                    "resume_embed_skipped_insufficient_credits",
                    candidate_id=candidate_id,
                    error=str(exc)[:200],
                )
        finally:
            await svc.close()
        engine = MatchingEngine(conn)
        await engine.score_candidate(candidate_id, limit=200)
        # Best-effort job-match email (Resend; self-throttled, no-op if unconfigured).
        try:
            from hireloop_api.services.email.transactional import send_job_match_alert

            await send_job_match_alert(conn, settings, candidate_id)
        except Exception as exc:
            logger.warning("job_match_alert_failed", error=str(exc)[:200])


async def _handle_career_intelligence_update(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.career_intelligence import run_career_intelligence_update

    await run_career_intelligence_update(
        settings,
        str(payload["candidate_id"]),
        only_if_missing=bool(payload.get("only_if_missing")),
    )


async def _handle_career_path_update(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.career_path import run_career_path_update

    await run_career_path_update(settings, str(payload["candidate_id"]))


async def _handle_profile_completeness(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.career_intelligence import recompute_completeness_only

    await recompute_completeness_only(settings, str(payload["candidate_id"]))


async def _handle_career_path_resumes(settings: Settings, payload: dict[str, Any]) -> None:
    # LLM-heavy (up to 3 resume builds) — runs here so no request connection is
    # held for minutes; the worker uses one short-lived pooled connection.
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.career_path_resume import generate_path_resumes

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        await generate_path_resumes(conn, str(payload["candidate_id"]), settings)


async def _handle_tailored_resume(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.routes.tailored_resumes import _run_tailor_task

    await _run_tailor_task(
        uuid.UUID(str(payload["candidate_id"])),
        uuid.UUID(str(payload["job_id"])),
        str(payload.get("template") or "modern"),
        settings,
    )


async def _handle_learning_roadmap(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.routes.learning_roadmaps import _run_roadmap_task

    await _run_roadmap_task(
        uuid.UUID(str(payload["candidate_id"])),
        uuid.UUID(str(payload["job_id"])),
        settings,
    )


async def _handle_application_kit(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.application_kit import run_application_kit_job

    await run_application_kit_job(
        settings,
        str(payload["candidate_id"]),
        str(payload["job_id"]),
    )


async def _handle_match_embed_all(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.embeddings import EmbeddingService, InsufficientCreditsError

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        svc = EmbeddingService(api_key=settings.openrouter_api_key, db=conn)
        try:
            try:
                await svc.embed_all_pending_jobs()
                await svc.embed_all_pending_candidates()
            except InsufficientCreditsError as exc:
                logger.warning(
                    "match_embed_all_skipped_insufficient_credits",
                    error=str(exc)[:200],
                )
        finally:
            await svc.close()


async def _handle_match_recompute_all(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.matching import MatchingEngine

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        engine = MatchingEngine(conn)
        await engine.recompute_all()


async def _handle_match_embed_candidate(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.embeddings import EmbeddingService, InsufficientCreditsError
    from hireloop_api.services.matching import MatchingEngine

    candidate_id = str(payload["candidate_id"])
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        if settings.openrouter_api_key:
            svc = EmbeddingService(api_key=settings.openrouter_api_key, db=conn)
            try:
                try:
                    await svc.embed_all_pending_jobs()
                    await svc.embed_candidate(candidate_id)
                except InsufficientCreditsError as exc:
                    logger.warning(
                        "match_embed_candidate_skipped_insufficient_credits",
                        candidate_id=candidate_id,
                        error=str(exc)[:200],
                    )
            finally:
                await svc.close()
        # Always score — lexical matching works without embeddings.
        engine = MatchingEngine(conn)
        await engine.score_candidate(candidate_id)


async def _handle_job_embed(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.embeddings import run_job_embedding

    await run_job_embedding(settings, str(payload["job_id"]))


async def _handle_job_score(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.matching import run_job_scoring

    limit = int(payload.get("limit") or 500)
    await run_job_scoring(settings, str(payload["job_id"]), limit=limit)


async def _handle_job_ingest(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.apify.job_ingester import JobIngester

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        ingester = JobIngester(
            apify_token=settings.apify_token,
            db=conn,
            settings=settings,
            jobs_actor=settings.apify_jobs_actor,
        )
        await ingester.ingest(
            queries=payload.get("queries"),
            locations=payload.get("locations"),
            max_results_per_query=int(payload.get("max_results_per_query") or 50),
            time_range=str(payload.get("time_range") or settings.google_jobs_time_range),
            force_refresh=bool(payload.get("force_refresh")),
        )


async def _handle_linkdapi_enrich(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.services.linkedin_enrichment import run_linkedin_profile_enrichment

    await run_linkedin_profile_enrichment(
        settings,
        str(payload["user_id"]),
        str(payload["linkedin_url"]),
    )


async def _handle_interview_reminder(settings: Settings, payload: dict[str, Any]) -> None:
    from datetime import datetime

    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.notifications import send_interview_reminder_email

    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        scheduled = datetime.fromisoformat(str(payload["scheduled_at"]).replace("Z", "+00:00"))
        await send_interview_reminder_email(
            conn,
            settings,
            user_id=str(payload["user_id"]),
            session_id=str(payload["session_id"]),
            session_type=str(payload.get("session_type") or "career_chat"),
            scheduled_at=scheduled,
        )


async def _handle_aarya_weekly_digest(settings: Settings, payload: dict[str, Any]) -> None:

    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.notifications import schedule_weekly_digest, send_weekly_digest

    user_id = str(payload["user_id"])
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        await send_weekly_digest(conn, settings, user_id=user_id)
        await schedule_weekly_digest(conn, user_id=user_id, first_run_days=7)


async def _handle_firecrawl_jd_backfill(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.firecrawl.jd_fetcher import run_jd_backfill_for_job

    job_id = str(payload["job_id"])
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        await run_jd_backfill_for_job(conn, job_id=job_id, settings=settings)


async def _handle_firecrawl_company_intel(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.firecrawl.company_intel import fetch_company_intel

    company_id = str(payload["company_id"])
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        await fetch_company_intel(conn, company_id=company_id, settings=settings)


async def _handle_hm_enrich(settings: Settings, payload: dict[str, Any]) -> None:
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.apify.hm_enricher import HMEnricher

    hm_id = str(payload["hm_id"])
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        enricher = HMEnricher(
            apify_token=settings.apify_token,
            neverbounce_api_key=settings.neverbounce_api_key,
            db=conn,
        )
        try:
            await enricher.enrich(hm_id)
        finally:
            await enricher.close()


_HANDLERS: dict[str, Handler] = {
    CAREER_PATH_INGEST: _handle_career_path_ingest,
    POOL_INGEST: _handle_pool_ingest,
    AARYA_AUTO_INGEST: _handle_aarya_auto_ingest,
    RESUME_EMBED_SCORE: _handle_resume_embed_score,
    CAREER_INTELLIGENCE_UPDATE: _handle_career_intelligence_update,
    CAREER_PATH_UPDATE: _handle_career_path_update,
    PROFILE_COMPLETENESS: _handle_profile_completeness,
    TAILORED_RESUME: _handle_tailored_resume,
    CAREER_PATH_RESUMES: _handle_career_path_resumes,
    LEARNING_ROADMAP: _handle_learning_roadmap,
    APPLICATION_KIT: _handle_application_kit,
    MATCH_EMBED_ALL: _handle_match_embed_all,
    MATCH_RECOMPUTE_ALL: _handle_match_recompute_all,
    MATCH_EMBED_CANDIDATE: _handle_match_embed_candidate,
    JOB_EMBED: _handle_job_embed,
    JOB_SCORE: _handle_job_score,
    JOB_INGEST: _handle_job_ingest,
    LINKDAPI_ENRICH: _handle_linkdapi_enrich,
    HM_ENRICH: _handle_hm_enrich,
    INTERVIEW_REMINDER: _handle_interview_reminder,
    AARYA_WEEKLY_DIGEST: _handle_aarya_weekly_digest,
    FIRECRAWL_JD_BACKFILL: _handle_firecrawl_jd_backfill,
    FIRECRAWL_COMPANY_INTEL: _handle_firecrawl_company_intel,
}


async def process_job(
    pool: asyncpg.Pool,
    settings: Settings,
    job: dict[str, Any],
) -> None:
    """Run one claimed job to completion or schedule a retry.

    Handlers may run for minutes (embed + match scoring). They acquire their own
    connections from ``pool``; this function must not hold a connection open
    across ``handler`` execution or the API pool starves under load.
    """
    kind = job["kind"]
    handler = _HANDLERS.get(kind)
    if handler is None:
        async with pool.acquire() as conn:
            await mark_job_failed(
                conn,
                job["id"],
                error=f"unknown job kind: {kind}",
                attempts=job["attempts"],
                max_attempts=job["max_attempts"],
            )
        return
    try:
        await handler(settings, job["payload"])
        async with pool.acquire() as conn:
            await mark_job_completed(conn, job["id"])
        logger.info("background_job_completed", job_id=job["id"], kind=kind)
    except Exception as exc:
        async with pool.acquire() as conn:
            await mark_job_failed(
                conn,
                job["id"],
                error=str(exc),
                attempts=job["attempts"],
                max_attempts=job["max_attempts"],
            )


async def run_background_worker(
    settings: Settings,
    stop_event: asyncio.Event,
    *,
    worker_id: str | None = None,
    poll_seconds: float = 2.0,
) -> None:
    """
    Long-polling worker loop. Started from FastAPI lifespan; disabled in tests
    unless ``settings.background_worker_enabled`` is True.

    Heavy Apify/embed jobs stay single-lane; interactive kits/resumes run on up
    to ``_MAX_CONCURRENT_INTERACTIVE`` concurrent tasks so UI polls succeed while
    scrapes are in flight.
    """
    import time as _time

    from hireloop_api.deps import get_db_pool

    wid = worker_id or f"api-{uuid.uuid4().hex[:8]}"
    logger.info("background_worker_started", worker_id=wid)

    # Periodic intro follow-up sweep (72h nudges) rides the same loop — no
    # extra scheduler process. First run ~1 min after boot, then every 15 min.
    sweep_interval_s = 15 * 60
    next_sweep_at = _time.monotonic() + 60
    # Reclaim jobs left "running" after deploy/crash so one zombie cannot starve
    # the single-threaded worker forever (Apify + embed jobs can exceed 15m).
    reclaim_interval_s = 5 * 60
    next_reclaim_at = _time.monotonic() + 30
    stuck_running_ttl = timedelta(minutes=20)

    heavy_task: asyncio.Task[None] | None = None
    interactive_tasks: set[asyncio.Task[None]] = set()

    def _on_interactive_done(task: asyncio.Task[None]) -> None:
        interactive_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("interactive_background_job_task_error", error=str(exc)[:300])

    while not stop_event.is_set():
        try:
            pool = await get_db_pool(settings)
            if _time.monotonic() >= next_reclaim_at:
                next_reclaim_at = _time.monotonic() + reclaim_interval_s
                async with pool.acquire() as conn:
                    reclaimed = await conn.fetch(
                        """
                        UPDATE public.background_jobs
                        SET status = 'failed',
                            last_error = 'reclaimed: stuck running after worker death',
                            completed_at = NOW(),
                            updated_at = NOW(),
                            worker_id = NULL
                        WHERE status = 'running'
                          AND started_at < NOW() - $1::interval
                        RETURNING id
                        """,
                        stuck_running_ttl,
                    )
                if reclaimed:
                    logger.warning(
                        "background_jobs_reclaimed_stuck",
                        count=len(reclaimed),
                        ttl_minutes=int(stuck_running_ttl.total_seconds() // 60),
                    )

            claimed_any = False

            # Drain interactive queue concurrently (kits must not wait on Apify).
            while len(interactive_tasks) < _MAX_CONCURRENT_INTERACTIVE:
                async with pool.acquire() as conn:
                    interactive = await claim_next_job(
                        conn,
                        worker_id=f"{wid}-ui",
                        kinds=_INTERACTIVE_JOB_KINDS,
                    )
                if not interactive:
                    break
                claimed_any = True
                task = asyncio.create_task(
                    process_job(pool, settings, interactive),
                    name=f"bg-{interactive['kind']}-{interactive['id'][:8]}",
                )
                interactive_tasks.add(task)
                task.add_done_callback(_on_interactive_done)

            # Single heavy lane for Apify / bulk embed work.
            if heavy_task is None or heavy_task.done():
                if heavy_task is not None and not heavy_task.cancelled():
                    exc = heavy_task.exception()
                    if exc is not None:
                        logger.error("heavy_background_job_task_error", error=str(exc)[:300])
                heavy_task = None
                async with pool.acquire() as conn:
                    heavy = await claim_next_job(
                        conn,
                        worker_id=f"{wid}-heavy",
                        exclude_kinds=_INTERACTIVE_JOB_KINDS,
                    )
                if heavy:
                    claimed_any = True
                    heavy_task = asyncio.create_task(
                        process_job(pool, settings, heavy),
                        name=f"bg-{heavy['kind']}-{heavy['id'][:8]}",
                    )

            if claimed_any:
                continue

            if _time.monotonic() >= next_sweep_at:
                next_sweep_at = _time.monotonic() + sweep_interval_s
                from hireloop_api.services.intro_followups import run_intro_followup_sweep

                async with pool.acquire() as conn:
                    nudged = await run_intro_followup_sweep(conn, settings)
                    # Bounded retention for the parse cache (hash-keyed, so it
                    # can't be purged per-account — the TTL bounds it instead).
                    await conn.execute(
                        "DELETE FROM public.resume_parse_cache "
                        "WHERE created_at < NOW() - INTERVAL '30 days'"
                    )
                if nudged:
                    logger.info("intro_followup_sweep_done", nudged=nudged)
        except Exception as exc:
            logger.error("background_worker_poll_error", error=str(exc)[:300])

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass

    # Drain in-flight tasks on shutdown (best-effort).
    pending = list(interactive_tasks)
    if heavy_task is not None and not heavy_task.done():
        pending.append(heavy_task)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    logger.info("background_worker_stopped", worker_id=wid)
