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
import re
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
from hireloop_api.services.match_quality import should_persist_match
from hireloop_api.services.matching import _assemble_score
from hireloop_api.services.test_jobs import (
    TEST_MATCH_EXPLANATION,
    TEST_MATCH_SCORE,
    ensure_test_match_scores,
    fetch_test_jobs,
    is_test_job,
    prepend_test_jobs,
    test_jobs_company_sql_exclude,
    test_jobs_enabled,
)

logger = structlog.get_logger()

# Generic words that shouldn't drive a keyword search on their own — they match
# thousands of unrelated postings. Kept small on purpose; role nouns like
# "manager", "engineer", "analyst" are deliberately NOT here.
_SEARCH_STOPWORDS = frozenset(
    {
        "and",
        "the",
        "for",
        "of",
        "in",
        "with",
        "to",
        "at",
        "on",
        "a",
        "an",
        "jobs",
        "job",
        "role",
        "roles",
        "position",
        "positions",
        "opening",
        "openings",
        "vacancy",
        "vacancies",
        "hiring",
        "career",
        "careers",
    }
)


def _search_tokens(query_text: str | None) -> list[str]:
    """Break a decorated role title into significant search tokens.

    Career-path titles arrive decorated, e.g. "Category Manager - Fashion &
    Apparel". A single full-string ILIKE almost never matches a real posting,
    so we tokenise and match/rank on the individual words instead. Stopwords
    and <3-char fragments are dropped; order is preserved (deduped).
    """
    if not query_text:
        return []
    seen: set[str] = set()
    tokens: list[str] = []
    for raw in re.split(r"[^0-9a-zA-Z]+", query_text.lower()):
        if len(raw) < 3 or raw in _SEARCH_STOPWORDS or raw in seen:
            continue
        seen.add(raw)
        tokens.append(raw)
    return tokens


def _candidate_quality_row(candidate: dict[str, Any], target_titles: list[str]) -> dict[str, Any]:
    return {
        "current_title": candidate.get("current_title"),
        "current_company": candidate.get("current_company"),
        "full_name": candidate.get("full_name") or "there",
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
        "target_titles": target_titles,
    }


def _job_quality_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": row.get("title"),
        "company_name": row.get("company_name"),
        "description": row.get("description"),
        "seniority": row.get("seniority"),
        "skills_required": list(row.get("skills_required") or []),
        "is_remote": bool(row.get("is_remote")),
        "location_city": row.get("location_city"),
        "location_state": row.get("location_state"),
        "ctc_min": row.get("ctc_min"),
        "ctc_max": row.get("ctc_max"),
    }


def _quality_filter_job_rows(
    rows: list[Any] | None,
    *,
    candidate: dict[str, Any] | None,
    target_titles: list[str],
    lenient: bool = False,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if candidate is None:
        return [dict(r) for r in rows]

    cand_row = _candidate_quality_row(candidate, target_titles)
    filtered: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        job_row = _job_quality_row(row_dict)
        if is_test_job(row_dict):
            if not test_jobs_enabled():
                continue
            if row_dict.get("overall_score") is None:
                row_dict["overall_score"] = TEST_MATCH_SCORE
            row_dict["explanation"] = row_dict.get("explanation") or TEST_MATCH_EXPLANATION
            filtered.append(row_dict)
            continue
        score = _assemble_score(cand_row, job_row, embed_skills_sim=None, embed_profile_sim=None)
        if not should_persist_match(cand_row, job_row, score):
            continue
        row_dict["overall_score"] = score["overall"]
        row_dict["skills_score"] = round(score["skills_sim"], 4)
        row_dict["experience_score"] = round(score["exp_score"], 4)
        row_dict["location_score"] = round(score["loc_score"], 4)
        row_dict["ctc_score"] = round(score["ctc_score"], 4)
        row_dict["explanation"] = row_dict.get("explanation") or score["explanation"]
        filtered.append(row_dict)
    if filtered or not lenient:
        return filtered
    fallback: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("overall_score") is None:
            job_row = _job_quality_row(row_dict)
            score = _assemble_score(
                cand_row, job_row, embed_skills_sim=None, embed_profile_sim=None
            )
            row_dict["overall_score"] = score["overall"]
            row_dict["explanation"] = row_dict.get("explanation") or score["explanation"]
        fallback.append(row_dict)
    return fallback


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
    """Background: career-path scrape → embed new jobs → score for this candidate."""
    from hireloop_api.deps import get_db_pool
    from hireloop_api.services.apify.job_ingester import JobIngester
    from hireloop_api.services.embeddings import embed_pending_and_score_candidate

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
            embedded, scored = await embed_pending_and_score_candidate(
                conn, settings, candidate_id, limit=500
            )
        logger.info(
            "aarya_auto_ingest_done",
            candidate_id=candidate_id,
            embedded=embedded,
            scored=scored,
        )
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
    exclude_job_ids: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
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
    from hireloop_api.services.job_search_refresh import (
        compute_job_search_fetch_limit,
        exclude_job_rows,
    )

    t0 = time.monotonic()

    exclude_ids = list(exclude_job_ids or [])
    fetch_limit = compute_job_search_fetch_limit(limit=limit, exclude_count=len(exclude_ids))

    candidate = await db.fetchrow(
        """
        SELECT c.id, c.remote_preference, c.market,
               c.current_title, c.current_company, c.headline, c.summary,
               c.years_experience, c.skills, c.location_city, c.location_state,
               c.expected_ctc_min, c.expected_ctc_max,
               c.open_to_relocation, c.location_scope,
               u.full_name
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.user_id = $1::uuid AND c.deleted_at IS NULL
        """,
        uuid.UUID(user_id),
    )

    market = "IN"
    if candidate:
        market = await fetch_candidate_market(db, candidate["id"])
        if test_jobs_enabled(settings):
            await ensure_test_match_scores(
                db,
                str(candidate["id"]),
                market=market,
                remote_preference="any",
                settings=settings,
            )

    vis = job_visible_for_market_sql(market_param="$7")

    pref = resolve_remote_preference(
        stored=candidate["remote_preference"] if candidate else None,
        override=remote_preference,
    )
    remote_clause = remote_filter_sql(pref)
    company_exclude = test_jobs_company_sql_exclude(company_alias="co")

    target_titles: list[str] = []
    if candidate:
        path = await CareerPathService.get_latest(db, str(candidate["id"]))
        target_titles = list((path or {}).get("target_titles") or [])
    candidate_profile = dict(candidate) if candidate else None

    rows = None
    if candidate:
        step1_raw = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
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
              {company_exclude}
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
            fetch_limit,
            market,
        )
        step1_filtered = _quality_filter_job_rows(
            step1_raw,
            candidate=candidate_profile,
            target_titles=target_titles,
        )
        # Lenient re-fetch is only safe when step 1 had nothing REAL to offer
        # (empty, or demo rows only). If real rows existed and strict quality
        # filtering dropped them (e.g. domain mismatch — dental sales for a
        # SaaS GTM profile), an honest empty beats leniently re-admitting them.
        had_real_raw = any(not is_test_job(dict(r)) for r in step1_raw)
        if step1_filtered:
            rows = step1_filtered
        elif not had_real_raw:
            # Step 1b: narrow query missed, or only demo rows were filtered out.
            vis_fallback = job_visible_for_market_sql(market_param="$3")
            step1b_raw = await db.fetch(
                f"""
                SELECT j.id, j.title, j.location_city, j.location_state,
                       j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                       j.employment_type, j.seniority, j.apply_url, j.description,
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
                  {company_exclude}
                ORDER BY ms.overall_score DESC
                LIMIT $2::integer
                """,
                candidate["id"],
                fetch_limit,
                market,
            )
            rows = _quality_filter_job_rows(
                step1b_raw,
                candidate=candidate_profile,
                target_titles=target_titles,
                lenient=True,
            )

    # Step 2: fallback — unranked keyword search (no match scores yet at all)
    vis_kw = job_visible_for_market_sql(market_param="$6")
    if not rows:
        rows = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.is_active = TRUE
              AND {vis_kw}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              {company_exclude}
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
            fetch_limit,
            market,
        )
        rows = _quality_filter_job_rows(
            rows,
            candidate=candidate_profile,
            target_titles=target_titles,
        )

    # Step 2b: the exact phrase missed. Relax to token-level matching so a
    # decorated title ("Category Manager - Fashion & Apparel") degrades to the
    # closest live roles instead of a dead end. Rank by how many query tokens
    # appear in the title, then recency. Quality filter still gates fit.
    tokens = _search_tokens(query_text)
    if not rows and tokens:
        vis_tok = job_visible_for_market_sql(market_param="$6")
        tok_rows = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.is_active = TRUE
              AND {vis_tok}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              {company_exclude}
              AND ($2::text[] IS NULL OR j.skills_required && $2::text[])
              AND ($3::text IS NULL OR j.location_city ILIKE '%' || $3::text || '%')
              AND ($4::integer IS NULL OR j.ctc_max IS NULL OR j.ctc_max >= $4::integer)
              AND EXISTS (
                SELECT 1 FROM unnest($1::text[]) AS t
                WHERE j.title ILIKE '%' || t || '%'
              )
            ORDER BY (
                SELECT count(*) FROM unnest($1::text[]) AS t
                WHERE j.title ILIKE '%' || t || '%'
              ) DESC,
              j.scraped_at DESC
            LIMIT $5::integer
            """,
            tokens,
            skills_filter,
            location_city,
            ctc_min,
            fetch_limit,
            market,
        )
        rows = _quality_filter_job_rows(
            tok_rows,
            candidate=candidate_profile,
            target_titles=target_titles,
            lenient=True,
        )

    # Step 3: exact title/city can still be too brittle for generalist titles
    # ("Assistant Manager", "Senior Executive") or sparse city feeds. Pull a
    # broader visible market pool, score it against the CV, and keep the best
    # profile-fit roles so Aarya always has cards before narrating a dry feed.
    if not rows:
        vis_profile = job_visible_for_market_sql(market_param="$4")
        broad_limit = max(fetch_limit * 5, 50)
        profile_rows = await db.fetch(
            f"""
            SELECT j.id, j.title, j.location_city, j.location_state,
                   j.is_remote, j.ctc_min, j.ctc_max, j.skills_required,
                   j.employment_type, j.seniority, j.apply_url, j.description,
                   co.name AS company_name, co.logo_url,
                   NULL::real AS overall_score
            FROM public.jobs j
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.is_active = TRUE
              AND {vis_profile}
              AND j.deleted_at IS NULL
              AND (j.expires_at IS NULL OR j.expires_at > NOW())
              {remote_clause}
              {company_exclude}
              AND ($2::integer IS NULL OR j.ctc_max IS NULL OR j.ctc_max >= $2::integer)
            ORDER BY
              CASE
                WHEN $1::text IS NOT NULL
                 AND j.location_city ILIKE '%' || $1::text || '%'
                THEN 0
                ELSE 1
              END,
              j.scraped_at DESC
            LIMIT $3::integer
            """,
            location_city,
            ctc_min,
            broad_limit,
            market,
        )
        rows = _quality_filter_job_rows(
            profile_rows,
            candidate=candidate_profile,
            target_titles=target_titles,
        )
        if not rows:
            rows = _quality_filter_job_rows(
                profile_rows,
                candidate=candidate_profile,
                target_titles=target_titles,
                lenient=True,
            )

    if rows:
        rows = exclude_job_rows(
            [dict(r) for r in rows],
            exclude_job_ids=exclude_ids,
            limit=limit,
        )

    if candidate and test_jobs_enabled(settings):
        test_rows = await fetch_test_jobs(db, market=market, remote_preference="any")
        test_dicts = []
        for row in test_rows:
            row_dict = dict(row)
            row_dict["id"] = row_dict["job_id"]
            row_dict["overall_score"] = TEST_MATCH_SCORE
            row_dict["explanation"] = TEST_MATCH_EXPLANATION
            test_dicts.append(row_dict)
        rows = prepend_test_jobs(
            [dict(r) for r in rows],
            test_dicts,
            limit=limit,
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

    # When nothing matched, warm the index so the candidate's NEXT search has
    # live openings. Career-path users get a path-scoped ingest regardless of
    # the old generic auto-ingest flag; generic fallbacks still respect the flag
    # to avoid broad Apify spend.
    if not results and settings is not None and settings.apify_token and candidate is not None:
        from hireloop_api.services.background_jobs import (
            AARYA_AUTO_INGEST,
            CAREER_PATH_INGEST,
            enqueue_job,
        )

        candidate_id = str(candidate["id"])
        location_parts = [
            p
            for p in [
                candidate_profile.get("location_city") if candidate_profile else None,
                candidate_profile.get("location_state") if candidate_profile else None,
            ]
            if p
        ]
        if target_titles:
            await enqueue_job(
                db,
                kind=CAREER_PATH_INGEST,
                payload={
                    "candidate_id": candidate_id,
                    "queries": target_titles,
                    "locations": location_parts or ["India"],
                },
                idempotency_key=f"career_path_ingest:{candidate_id}",
            )
            logger.info(
                "aarya_path_ingest_enqueued",
                candidate_id=candidate_id,
                queries=target_titles,
            )
        elif settings.auto_ingest_on_empty_search:
            await enqueue_job(
                db,
                kind=AARYA_AUTO_INGEST,
                payload={"candidate_id": candidate_id},
                idempotency_key=f"aarya_auto_ingest:{candidate_id}",
            )
            logger.info("aarya_auto_ingest_enqueued", candidate_id=candidate_id)

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

    from hireloop_api.config import get_settings
    from hireloop_api.services.job_pipeline import record_direct_application

    t0 = time.monotonic()
    result = await record_direct_application(
        db,
        user_id=user_id,
        job_id=job_id,
        settings=get_settings(),
    )
    if "error" not in result:
        result["apply_url"] = apply_url

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
