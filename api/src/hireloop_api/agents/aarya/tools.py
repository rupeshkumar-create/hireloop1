"""
Aarya agent tools — deterministic Python functions called by the LLM.

Each tool:
  1. Performs a concrete action (DB read, API call, etc.)
  2. Returns a structured result
  3. Writes a row to agent_actions table (R7 "performed X actions" UI)

Tool catalogue:
  - profile_read       : read candidate profile from DB
  - job_search         : semantic search for matching jobs
  - match_score_explain: explain why a job matches this candidate
  - request_intro      : insert into intro_requests (triggers Nitya via NOTIFY)
  - direct_apply       : record a direct application
  - save_job           : save job for later
  - prepare_application_kit : save job + tailored resume, cover letter, interview prep
  - update_job_preferences : remote vs on-site job filter
  - book_voice_call    : get available voice-call slots (in-house Google Calendar)
  - voice_response     : signal that Deepgram TTS should be used for response
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import asyncpg
import structlog

from hireloop_api.config import Settings
from hireloop_api.market_db import fetch_candidate_market, fetch_user_market
from hireloop_api.markets import job_visible_for_market_sql
from hireloop_api.services.career_path_selection import career_path_options
from hireloop_api.services.job_preferences import (
    VALID_REMOTE_PREFERENCES,
    normalize_remote_preference,
    preference_label,
    remote_filter_sql,
    resolve_remote_preference,
)

logger = structlog.get_logger()


async def _write_action(
    db: asyncpg.Connection,
    agent: str,
    user_id: str,
    session_id: str,
    action_type: str,
    payload: dict,
    result: dict,
    duration_ms: int | None = None,
) -> None:
    """Write an agent_action row — drives the "Aarya performed N actions" counter."""
    await db.execute(
        """
        INSERT INTO public.agent_actions
          (agent, user_id, session_id, action_type, payload, result, duration_ms)
        VALUES ($1, $2::uuid, $3::uuid, $4, $5::jsonb, $6::jsonb, $7)
        """,
        agent,
        user_id,
        session_id,
        action_type,
        json.dumps(payload),
        json.dumps(result),
        duration_ms,
    )


async def profile_read(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    """Read the candidate's full profile."""
    import time

    t0 = time.monotonic()

    row = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.location_city, c.location_state, c.years_experience,
               c.notice_period_days, c.expected_ctc_min, c.expected_ctc_max,
               c.current_ctc, c.skills, c.linkedin_url, c.profile_complete,
               c.remote_preference, c.looking_for,
               u.full_name, u.email
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.user_id = $1 AND c.deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )

    if not row:
        result = {"error": "Candidate profile not found"}
    else:
        from hireloop_api.services.candidate_display_name import resolve_candidate_display_name

        result = dict(row)
        result["id"] = str(result["id"])
        resolved_name = await resolve_candidate_display_name(
            db,
            user_id=user_id,
            candidate_id=str(result["id"]),
        )
        if resolved_name:
            result["full_name"] = resolved_name

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(db, "aarya", user_id, session_id, "profile_read", {}, result, duration_ms)
    return result


VALID_LOCATION_SCOPES = ("city", "state", "country", "global")
_MARKET_COUNTRY_LABELS = {"IN": "India", "US": "the US", "GB": "the UK"}


def location_scope_labels(market: str = "IN") -> dict[str, str]:
    country = _MARKET_COUNTRY_LABELS.get(market, "your country")
    return {
        "city": "roles in your city",
        "state": "roles across your state/region",
        "country": f"roles anywhere in {country}",
        "global": "roles anywhere (global)",
    }


async def update_job_preferences(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    remote_preference: str | None = None,
    open_to_relocation: bool | None = None,
    location_scope: str | None = None,
) -> dict[str, Any]:
    """Persist the candidate's job-search preferences.

    Levers (set any combination):
      - ``remote_preference``: remote vs on-site filter (any | remote_only | onsite_only).
      - ``location_scope``: how wide a geography to surface — city | state | country | global.
        Drives the location sub-score; kept in sync with open_to_relocation.
      - ``open_to_relocation``: legacy boolean (True ≈ country). Prefer location_scope.
    """
    import time

    t0 = time.monotonic()

    set_clauses: list[str] = []
    values: list[object] = [uuid.UUID(user_id)]
    summary: dict[str, Any] = {}

    async def _fail(msg: str) -> dict[str, Any]:
        res = {"error": msg}
        await _write_action(
            db,
            "aarya",
            user_id,
            session_id,
            "update_job_preferences",
            {"remote_preference": remote_preference, "location_scope": location_scope},
            res,
            int((time.monotonic() - t0) * 1000),
        )
        return res

    pref: str | None = None
    if remote_preference is not None:
        pref = normalize_remote_preference(remote_preference)
        if pref not in VALID_REMOTE_PREFERENCES:
            return await _fail(
                "Invalid remote_preference. Use one of: "
                + ", ".join(sorted(VALID_REMOTE_PREFERENCES))
            )
        set_clauses.append(f"remote_preference = ${len(values) + 1}")
        values.append(pref)
        summary["remote_preference"] = pref

    # location_scope is the source of truth; mirror open_to_relocation off it.
    scope: str | None = None
    if location_scope is not None:
        scope = location_scope.lower().strip()
        if scope not in VALID_LOCATION_SCOPES:
            return await _fail(
                "Invalid location_scope. Use one of: " + ", ".join(VALID_LOCATION_SCOPES)
            )
        set_clauses.append(f"location_scope = ${len(values) + 1}")
        values.append(scope)
        summary["location_scope"] = scope
        derived_relocation = scope in ("country", "global")
        set_clauses.append(f"open_to_relocation = ${len(values) + 1}")
        values.append(derived_relocation)
        summary["open_to_relocation"] = derived_relocation
    elif open_to_relocation is not None:
        set_clauses.append(f"open_to_relocation = ${len(values) + 1}")
        values.append(bool(open_to_relocation))
        summary["open_to_relocation"] = bool(open_to_relocation)
        # Keep scope coherent with the legacy flag.
        set_clauses.append(f"location_scope = ${len(values) + 1}")
        values.append("country" if open_to_relocation else "city")
        summary["location_scope"] = (summary["open_to_relocation"] and "country") or "city"

    if not set_clauses:
        result = {
            "error": "Nothing to update — provide remote_preference, location_scope, "
            "and/or open_to_relocation."
        }
    else:
        updated = await db.execute(
            f"""
            UPDATE public.candidates
            SET {", ".join(set_clauses)}, updated_at = NOW()
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            *values,
        )
        if updated == "UPDATE 0":
            result = {"error": "Candidate profile not found"}
        else:
            bits: list[str] = []
            if pref is not None:
                bits.append(preference_label(pref))
            effective_scope = summary.get("location_scope")
            if effective_scope:
                market = await fetch_user_market(db, uuid.UUID(user_id))
                bits.append(location_scope_labels(market)[effective_scope])
            result = {
                **summary,
                "message": "Job search preferences updated: " + "; ".join(bits) + ".",
            }

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "update_job_preferences",
        {
            "remote_preference": remote_preference,
            "open_to_relocation": open_to_relocation,
            "location_scope": location_scope,
        },
        result,
        duration_ms,
    )
    return result


async def update_profile(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    current_title: str | None = None,
    current_company: str | None = None,
    years_experience: int | None = None,
    skills: list[str] | None = None,
    expected_ctc_min_lpa: float | None = None,
    expected_ctc_max_lpa: float | None = None,
    current_ctc_lpa: float | None = None,
    notice_period_days: int | None = None,
    location_city: str | None = None,
    location_state: str | None = None,
    looking_for: str | None = None,
) -> dict[str, Any]:
    """Persist profile details Aarya gathered (e.g. on a recruiter-style call).

    CTC args are in LPA and stored as INR per annum. Pass only the fields you
    learned this turn; everything is optional.
    """
    import time

    t0 = time.monotonic()

    set_clauses: list[str] = []
    values: list[object] = [uuid.UUID(user_id)]
    saved: dict[str, Any] = {}

    def _add(column: str, value: object) -> None:
        set_clauses.append(f"{column} = ${len(values) + 1}")
        values.append(value)
        saved[column] = value

    text_inputs = {
        "current_title": current_title,
        "current_company": current_company,
        "location_city": location_city,
        "location_state": location_state,
        "looking_for": looking_for,
    }
    for column, raw in text_inputs.items():
        if raw is not None and str(raw).strip():
            _add(column, str(raw).strip())

    if years_experience is not None:
        _add("years_experience", int(years_experience))
    if notice_period_days is not None:
        _add("notice_period_days", int(notice_period_days))
    if skills:
        cleaned = [s.strip() for s in skills if s and s.strip()]
        if cleaned:
            set_clauses.append(f"skills = ${len(values) + 1}::text[]")
            values.append(cleaned)
            saved["skills"] = cleaned

    def _lpa(v: float | None) -> int | None:
        return round(v * 100_000) if v is not None and v > 0 else None

    for column, lpa in (
        ("expected_ctc_min", _lpa(expected_ctc_min_lpa)),
        ("expected_ctc_max", _lpa(expected_ctc_max_lpa)),
        ("current_ctc", _lpa(current_ctc_lpa)),
    ):
        if lpa is not None:
            _add(column, lpa)

    if not set_clauses:
        result: dict[str, Any] = {"error": "No profile fields provided to update."}
    else:
        updated = await db.execute(
            f"""
            UPDATE public.candidates
            SET {", ".join(set_clauses)}, updated_at = NOW()
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            *values,
        )
        result = (
            {"error": "Candidate profile not found"}
            if updated == "UPDATE 0"
            else {"updated_fields": sorted(saved.keys()), "message": "Profile updated."}
        )
        if updated != "UPDATE 0":
            if hasattr(db, "fetchrow"):
                cand = await db.fetchrow(
                    "SELECT id FROM public.candidates "
                    "WHERE user_id = $1::uuid AND deleted_at IS NULL",
                    uuid.UUID(user_id),
                )
                if cand:
                    from hireloop_api.services.background_jobs import (
                        MATCH_EMBED_CANDIDATE,
                        RESUME_EMBED_SCORE,
                        enqueue_job,
                    )

                    cid = str(cand["id"])
                    await enqueue_job(
                        db,
                        kind=RESUME_EMBED_SCORE,
                        payload={"candidate_id": cid},
                        idempotency_key=f"resume_embed_score:{cid}",
                    )
                    await enqueue_job(
                        db,
                        kind=MATCH_EMBED_CANDIDATE,
                        payload={"candidate_id": cid},
                        idempotency_key=f"match_embed_candidate:{cid}",
                    )

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db, "aarya", user_id, session_id, "update_profile", saved, result, duration_ms
    )
    return result


# Holds references to fire-and-forget tasks so they aren't GC'd (legacy; prefer background_jobs).
_BG_TASKS: set[asyncio.Task] = set()


async def _auto_ingest_for_candidate(settings: Settings, candidate_id: str) -> None:
    """Background: warm the job index with a career-path-scoped Apify scrape."""
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.apify.job_ingester import JobIngester

    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as conn:
            ingester = JobIngester(
                settings.apify_token,
                conn,
                settings=settings,
                linkedin_actor=settings.apify_linkedin_jobs_actor,
                career_site_actor=settings.apify_career_site_actor,
                enable_career_site=settings.apify_enable_career_site_ingest,
            )
            await ingester.ingest_for_candidate(candidate_id)
        logger.info("aarya_auto_ingest_done", candidate_id=candidate_id)
    except Exception as exc:  # background best-effort; never surfaces to the user
        logger.warning("aarya_auto_ingest_failed", error=str(exc)[:200])


async def job_search(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    query_text: str,
    skills_filter: list[str] | None = None,
    location_city: str | None = None,
    ctc_min: int | None = None,
    remote_preference: str | None = None,
    limit: int = 10,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic job search using pgvector cosine similarity + pre-computed match scores.
    Falls back to trigram keyword search if embeddings haven't been generated yet.

    Priority order:
      1. If the candidate has pre-computed match scores → return top-ranked subset
         filtered by the query (fast, personalized)
      2. If job_embeddings exist → cosine similarity on title_embedding against
         an ad-hoc query embedding
      3. Full-text / ILIKE fallback (always works, even on fresh installs)
    """
    import time

    from hireloop_api.services.career_path import CareerPathService

    t0 = time.monotonic()

    candidate = await db.fetchrow(
        """
        SELECT id, remote_preference, market
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )

    market = "IN"
    if candidate:
        market = await fetch_candidate_market(db, candidate["id"])

    vis = job_visible_for_market_sql(market_param="$7")

    pref = resolve_remote_preference(
        stored=candidate["remote_preference"] if candidate else None,
        override=remote_preference,
    )
    remote_clause = remote_filter_sql(pref)

    if candidate:
        path = await CareerPathService.get_latest(db, str(candidate["id"]))
        has_real_path = bool(path and (path.get("target_titles") or path.get("steps")))
        if has_real_path and not path.get("prioritized_title"):
            duration_ms = int((time.monotonic() - t0) * 1000)
            options = career_path_options(path)
            block_result = {
                "blocked": True,
                "reason": "prioritize_career_path",
                "message": (
                    "Career path is not locked in yet. Call prioritize_career_path "
                    "with the title the user chose (1→first option, 2→second, etc.), "
                    "then call job_search again. Do not re-ask if they already answered."
                ),
                "path_options": options,
            }
            await _write_action(
                db,
                "aarya",
                user_id,
                session_id,
                "job_search",
                {"query": query_text},
                block_result,
                duration_ms,
            )
            return {"count": 0, "job_cards": [], "matches": [], **block_result}

    rows = None
    if candidate:
        rows = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url,
                   co.name AS company_name, co.logo_url,
                   ms.overall_score, ms.explanation
            FROM public.match_scores ms
            JOIN public.jobs j ON j.id = ms.job_id
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE ms.candidate_id = $1::uuid
              AND j.is_active = TRUE
              AND {vis}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              AND (
                $2::text = '' OR
                j.title ILIKE '%' || $2::text || '%' OR
                j.skills_required::text ILIKE '%' || $2::text || '%'
              )
              AND ($3::text[] IS NULL OR j.skills_required && $3::text[])
              AND ($4::text IS NULL OR j.location_city ILIKE '%' || $4::text || '%')
              AND ($5::integer IS NULL OR j.ctc_max IS NULL OR j.ctc_max >= $5::integer)
            ORDER BY ms.overall_score DESC
            LIMIT $6::integer
            """,
            candidate["id"],
            query_text,
            skills_filter,
            location_city,
            ctc_min,
            limit,
            market,
        )

    # Step 1b: the candidate HAS ranked matches, but the narrow query/filters
    # zeroed them out — e.g. Aarya searched a niche title like "Growth Designer"
    # that no live job title literally contains, or a tight CTC floor. Don't tell
    # them "no jobs" while the Jobs panel shows 185: fall back to their top-ranked
    # matches (the same personalized set the match feed serves), keeping only the
    # hard constraints + their remote preference.
    vis_fallback = job_visible_for_market_sql(market_param="$3")
    if candidate and not rows:
        rows = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url,
                   co.name AS company_name, co.logo_url,
                   ms.overall_score, ms.explanation
            FROM public.match_scores ms
            JOIN public.jobs j ON j.id = ms.job_id
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE ms.candidate_id = $1::uuid
              AND j.is_active = TRUE
              AND {vis_fallback}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
            ORDER BY ms.overall_score DESC
            LIMIT $2::integer
            """,
            candidate["id"],
            limit,
            market,
        )

    # Step 2: fallback — unranked keyword search (no match scores yet at all)
    vis_kw = job_visible_for_market_sql(market_param="$6")
    if not rows:
        rows = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.is_active = TRUE
              AND {vis_kw}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              AND (
                $1::text = '' OR
                j.title ILIKE '%' || $1::text || '%' OR
                j.description ILIKE '%' || $1::text || '%'
              )
              AND ($2::text[] IS NULL OR j.skills_required && $2::text[])
              AND ($3::text IS NULL OR j.location_city ILIKE '%' || $3::text || '%')
              AND ($4::integer IS NULL OR j.ctc_max IS NULL OR j.ctc_max >= $4::integer)
            ORDER BY j.scraped_at DESC
            LIMIT $5::integer
            """,
            query_text,
            skills_filter,
            location_city,
            ctc_min,
            limit,
            market,
        )

    from hireloop_api.services.job_present import serialize_job_card
    from hireloop_api.services.ranking import dedupe_jobs

    results = [
        {
            **dict(r),
            "id": str(r["id"]),
            "skills_required": r["skills_required"] or [],
            "overall_score": float(r["overall_score"]) if r["overall_score"] is not None else None,
        }
        for r in rows
    ]
    job_cards = dedupe_jobs([serialize_job_card(r) for r in rows])
    duration_ms = int((time.monotonic() - t0) * 1000)

    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "job_search",
        {
            "query": query_text,
            "location": location_city,
            "limit": limit,
            "remote_preference": pref,
        },
        {"count": len(results), "jobs": job_cards, "remote_preference": pref},
        duration_ms,
    )

    # When nothing matched, optionally warm the index with a career-path-scoped
    # scrape so the candidate's NEXT search has live openings (opt-in via
    # AUTO_INGEST_ON_EMPTY_SEARCH; needs an Apify token; spends credits).
    if (
        not results
        and settings is not None
        and settings.auto_ingest_on_empty_search
        and settings.apify_token
        and candidate is not None
    ):
        from hireloop_api.services.background_jobs import AARYA_AUTO_INGEST, enqueue_job

        await enqueue_job(
            db,
            kind=AARYA_AUTO_INGEST,
            payload={"candidate_id": str(candidate["id"])},
            idempotency_key=f"aarya_auto_ingest:{candidate['id']}",
        )
        logger.info("aarya_auto_ingest_enqueued", candidate_id=str(candidate["id"]))

    return {
        "count": len(results),
        "job_cards": job_cards,
        "matches": results,
    }


async def prepare_application_kit(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    settings: Settings,
    job_ids: list[str] | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """
    Save role(s) and generate apply assets: tailored resume, cover letter,
    interview prep, and a mock-interview session link per job.
    """
    import time

    from hireloop_api.services.application_kit import prepare_application_kits

    t0 = time.monotonic()
    ids = list(job_ids or [])
    if job_id and job_id not in ids:
        ids.insert(0, job_id)
    if not ids:
        return {"error": "Provide at least one job_id"}

    result = await prepare_application_kits(db, user_id, ids, settings)
    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "prepare_application_kit",
        {"job_ids": ids},
        result,
        duration_ms,
    )
    return result


async def save_job(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    job_id: str,
) -> dict[str, Any]:
    """Bookmark a job for the candidate's Saved jobs list."""
    import time

    t0 = time.monotonic()
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not candidate:
        return {"error": "Candidate not found"}

    try:
        await db.execute(
            """
            INSERT INTO public.saved_jobs (candidate_id, job_id)
            VALUES ($1::uuid, $2::uuid)
            ON CONFLICT (candidate_id, job_id) DO NOTHING
            """,
            candidate["id"],
            uuid.UUID(job_id),
        )
        result = {"saved": True, "job_id": job_id}
    except Exception as exc:
        logger.error("save_job_failed", error=str(exc))
        result = {"error": str(exc)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "save_job",
        {"job_id": job_id},
        result,
        duration_ms,
    )
    return result


async def request_intro(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    job_id: str,
    hiring_manager_id: str | None = None,
) -> dict[str, Any]:
    """
    Request an intro for the candidate on a job. Delegates to the two-sided
    intro service, which routes to a registered recruiter (in-app), an email
    invite for an unregistered recruiter, or the legacy HM enrichment path.
    The intro_requests INSERT fires the Postgres NOTIFY trigger (R5) — the only
    mechanism for Aarya → Nitya / recruiter communication.
    """
    import time

    from hireloop_api.services.intro_service import create_candidate_intro

    t0 = time.monotonic()
    try:
        result = await create_candidate_intro(
            db,
            user_id=user_id,
            job_id=job_id,
            hiring_manager_id=hiring_manager_id,
        )
    except Exception as exc:
        logger.error("intro_request_failed", error=str(exc))
        result = {"error": str(exc)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "request_intro",
        {"job_id": job_id, "hm_id": hiring_manager_id},
        result,
        duration_ms,
    )
    return result


async def direct_apply(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    job_id: str,
    apply_url: str,
) -> dict[str, Any]:
    """Record a direct application (candidate clicks the job's native apply link)."""
    import time

    t0 = time.monotonic()

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not candidate:
        return {"error": "Candidate not found"}

    try:
        app_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO public.job_applications
              (id, candidate_id, job_id, apply_type, status, applied_at)
            VALUES ($1::uuid, $2::uuid, $3::uuid, 'direct', 'applied', NOW())
            ON CONFLICT (candidate_id, job_id) DO NOTHING
            """,
            app_id,
            candidate["id"],
            uuid.UUID(job_id),
        )
        result = {"application_id": app_id, "apply_url": apply_url}
    except Exception as exc:
        result = {"error": str(exc)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "direct_apply",
        {"job_id": job_id},
        result,
        duration_ms,
    )
    return result


async def prioritize_career_path(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    title: str,
) -> dict[str, Any]:
    """Lock in the candidate's chosen target role before job_search."""
    import time

    from hireloop_api.services.career_path import CareerPathService

    t0 = time.monotonic()
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not candidate:
        result: dict[str, Any] = {"error": "Candidate profile not found"}
    else:
        path = await CareerPathService.get_latest(db, str(candidate["id"]))
        if not path:
            result = {"error": "Generate a career path first (build_career_path)."}
        else:
            pick = (title or "").strip()
            options = career_path_options(path)
            if options and pick.isdigit() and 1 <= int(pick) <= len(options):
                pick = options[int(pick) - 1]
            elif options:
                from hireloop_api.services.career_path_selection import (
                    parse_career_path_selection,
                )

                resolved = parse_career_path_selection(pick, options)
                if resolved:
                    pick = resolved
            try:
                updated = await CareerPathService.prioritize(db, str(candidate["id"]), pick)
            except ValueError as exc:
                result = {"error": str(exc)}
            else:
                if not updated:
                    result = {"error": "Could not save career path choice."}
                else:
                    result = {
                        "prioritized_title": updated.get("prioritized_title"),
                        "path_options": options,
                        "message": (
                            f"Locked in {updated.get('prioritized_title')}. "
                            "You can call job_search now."
                        ),
                    }

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "prioritize_career_path",
        {"title": title},
        result,
        duration_ms,
    )
    return result


async def build_career_path(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """
    Generate (and persist) a career path for the candidate from their profile.
    Returns the path's current role, summary, steps, and the target role titles
    to search for. Use the target_titles to drive job_search.
    """
    import time

    from hireloop_api.services.career_path import CareerPathService

    t0 = time.monotonic()

    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
        uuid.UUID(user_id),
    )
    if not candidate:
        result: dict[str, Any] = {"error": "Candidate profile not found"}
    else:
        try:
            from hireloop_api.deps import get_db_pool

            pool = await get_db_pool(settings)
            result = await CareerPathService.generate(pool, str(candidate["id"]), settings)
        except Exception as exc:  # surface a clean error to the LLM
            logger.error("build_career_path_failed", error=str(exc))
            result = {"error": str(exc)}

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "build_career_path",
        {},
        {"target_titles": result.get("target_titles")},
        duration_ms,
    )
    return result


async def get_match_score(
    db: asyncpg.Connection,
    user_id: str,
    session_id: str,
    job_id: str,
) -> dict[str, Any]:
    """
    Fetch (or compute on-the-fly) the match score for a candidate-job pair.
    Uses pre-computed score if available; falls back to MatchingEngine.score_pair().
    """
    import time

    from hireloop_api.services.matching import MatchingEngine

    t0 = time.monotonic()

    # Try cached score first
    row = await db.fetchrow(
        """
        SELECT ms.overall_score, ms.skills_score, ms.experience_score,
               ms.location_score, ms.ctc_score, ms.explanation
        FROM public.match_scores ms
        JOIN public.candidates c ON c.id = ms.candidate_id
        WHERE c.user_id = $1 AND ms.job_id = $2::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(user_id),
        uuid.UUID(job_id),
    )

    if row:
        result: dict[str, Any] = {
            "overall_score": round(float(row["overall_score"]) * 100, 1),  # as % for LLM
            "skills_score": round(float(row["skills_score"] or 0) * 100, 1),
            "experience_score": round(float(row["experience_score"] or 0) * 100, 1),
            "location_score": round(float(row["location_score"] or 0) * 100, 1),
            "ctc_score": round(float(row["ctc_score"] or 0) * 100, 1),
            "explanation": row["explanation"],
            "source": "precomputed",
        }
    else:
        # On-the-fly computation (slower, used when nightly hasn't run yet)
        candidate = await db.fetchrow(
            "SELECT id FROM public.candidates WHERE user_id = $1 AND deleted_at IS NULL",
            uuid.UUID(user_id),
        )
        if not candidate:
            result = {"error": "Candidate profile not found"}
        else:
            engine = MatchingEngine(db)
            score = await engine.score_pair(str(candidate["id"]), job_id)
            if score is None:
                result = {"error": "Job not found or scoring unavailable"}
            else:
                # Re-fetch the explanation that was just written
                fresh = await db.fetchrow(
                    "SELECT overall_score, explanation FROM public.match_scores "
                    "WHERE candidate_id = $1::uuid AND job_id = $2::uuid",
                    candidate["id"],
                    uuid.UUID(job_id),
                )
                result = {
                    "overall_score": round(float(score) * 100, 1),
                    "explanation": fresh["explanation"] if fresh else None,
                    "source": "computed_live",
                }

    duration_ms = int((time.monotonic() - t0) * 1000)
    await _write_action(
        db,
        "aarya",
        user_id,
        session_id,
        "get_match_score",
        {"job_id": job_id},
        {"overall_score": result.get("overall_score")},
        duration_ms,
    )
    return result
