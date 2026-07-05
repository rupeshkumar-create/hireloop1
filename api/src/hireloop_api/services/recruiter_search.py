"""Candidate search + pipeline helpers for recruiter Nitya chat."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

import asyncpg

from hireloop_api.services.matching import MatchingEngine, rank_candidates_for_job
from hireloop_api.services.skills import canonical_skill


@dataclass
class SearchCandidatesResult:
    candidates: list[dict[str, Any]]
    count: int
    diagnostic: str | None = None
    diagnostic_message: str | None = None
    job_id: str | None = None
    published: bool = False


def _parse_json_field(val: object | None) -> dict[str, Any]:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _parse_json_list(val: object | None) -> list[Any]:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _role_skills(role: asyncpg.Record | dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for item in _parse_json_list(role.get("must_haves")):
        if item:
            skills.append(str(item))
    jd_struct = role.get("jd_structured")
    if isinstance(jd_struct, str):
        try:
            jd_struct = json.loads(jd_struct)
        except (ValueError, TypeError):
            jd_struct = {}
    if isinstance(jd_struct, dict):
        for key in ("required_skills", "skills", "must_have_skills"):
            for item in jd_struct.get(key) or []:
                if item:
                    skills.append(str(item))
    return list(dict.fromkeys(skills))[:30]


async def _sync_role_fields_to_job(
    db: asyncpg.Connection,
    *,
    role: asyncpg.Record,
    job_id: uuid.UUID,
) -> None:
    is_remote = role["remote_policy"] in ("remote", "flex")
    skills = _role_skills(role)
    await db.execute(
        """
        UPDATE public.jobs SET
          title = $2,
          description = $3,
          location_city = $4,
          location_state = $5,
          is_remote = $6,
          ctc_min = $7,
          ctc_max = $8,
          skills_required = $9,
          updated_at = NOW()
        WHERE id = $1
        """,
        job_id,
        role["title"],
        role.get("jd_text"),
        role.get("location_city"),
        role.get("location_state"),
        is_remote,
        role.get("comp_min"),
        role.get("comp_max"),
        skills,
    )


async def ensure_role_scoring_job(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    recruiter_id: uuid.UUID,
) -> tuple[uuid.UUID | None, bool, str | None]:
    """
    Ensure a jobs mirror row exists for this role so MatchingEngine can score
    candidates against the recruiter's actual brief — not a scraped title proxy.

    Returns (job_id, is_published_active, error_code).
    """
    role = await db.fetchrow(
        """
        SELECT id, company_id, recruiter_id, title, jd_text, comp_min, comp_max,
               location_city, location_state, remote_policy, must_haves, nice_to_haves,
               jd_structured, status
        FROM public.roles
        WHERE id = $1 AND recruiter_id = $2 AND deleted_at IS NULL
        """,
        role_id,
        recruiter_id,
    )
    if not role:
        return None, False, "role_not_found"

    existing = await db.fetchrow(
        """
        SELECT id, is_active FROM public.jobs
        WHERE role_id = $1::uuid AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT 1
        """,
        role_id,
    )
    if existing:
        await _sync_role_fields_to_job(db, role=role, job_id=existing["id"])
        return existing["id"], bool(existing["is_active"]), None

    is_remote = role["remote_policy"] in ("remote", "flex")
    skills = _role_skills(role)
    job_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO public.jobs
          (id, company_id, recruiter_id, role_id, title, description,
           location_city, location_state, country_code, is_remote,
           ctc_min, ctc_max, skills_required, source, is_active, scraped_at, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'IN', $9, $10, $11, $12,
                'recruiter', FALSE, NOW(), NOW() + INTERVAL '60 days')
        """,
        job_id,
        role["company_id"],
        recruiter_id,
        role_id,
        role["title"],
        role.get("jd_text"),
        role.get("location_city"),
        role.get("location_state"),
        is_remote,
        role.get("comp_min"),
        role.get("comp_max"),
        skills,
    )
    return job_id, False, None


async def _job_id_for_role_pipeline(
    db: asyncpg.Connection,
    role_id: uuid.UUID,
) -> uuid.UUID | None:
    row = await db.fetchrow(
        """
        SELECT id FROM public.jobs
        WHERE role_id = $1::uuid AND deleted_at IS NULL
        ORDER BY is_active DESC, created_at DESC
        LIMIT 1
        """,
        role_id,
    )
    return row["id"] if row else None


def _serialize_candidate_card(row: asyncpg.Record | dict[str, Any]) -> dict[str, Any]:
    r = dict(row)
    scores = _parse_json_field(r.get("criterion_scores"))
    skills = r.get("skills")
    if skills is None:
        skills_list: list[str] = []
    elif isinstance(skills, list):
        skills_list = [str(s) for s in skills]
    else:
        skills_list = []

    # Canonicalised skill breakdown — mirror the candidate feed so variants count
    # as matches ("PostgreSQL" == "postgresql", "ReactJS" == "react"). The old SQL
    # used exact `= ANY(skills)`, so a perfect candidate showed 0 matched.
    job_skills = r.get("skills_required") or []
    if isinstance(job_skills, str):
        job_skills = json.loads(job_skills)
    cand_canon = {canonical_skill(s) for s in skills_list}
    skills_matched = [s for s in job_skills if canonical_skill(s) in cand_canon]
    skills_gap = [s for s in job_skills if canonical_skill(s) not in cand_canon]

    return {
        "candidate_id": r["candidate_id"],
        "pipeline_id": str(r["pipeline_id"]) if r.get("pipeline_id") else None,
        "stage": r.get("stage") or "search",
        "overall_score": float(r.get("match_score") or r.get("overall_score") or 0),
        "display_name": r.get("display_name"),
        "headline": r.get("headline"),
        "summary": r.get("summary"),
        "current_title": r.get("current_title"),
        "current_company": r.get("current_company"),
        "years_experience": r.get("years_experience"),
        "location_city": r.get("location_city"),
        "location_state": r.get("location_state"),
        "skills": skills_list,
        "skills_matched": list(skills_matched),
        "skills_gap": list(skills_gap),
        "looking_for": r.get("looking_for"),
        "remote_preference": r.get("remote_preference"),
        "notice_period_days": r.get("notice_period_days"),
        "expected_ctc_min": r.get("expected_ctc_min"),
        "expected_ctc_max": r.get("expected_ctc_max"),
        "current_ctc": r.get("current_ctc"),
        "match_explanation": r.get("match_explanation"),
        "scores": scores,
    }


async def search_candidates_for_role(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    limit: int = 25,
    public_profiles: bool = True,
    openrouter_api_key: str = "",
) -> SearchCandidatesResult:
    """Rank candidates against the recruiter role (not a scraped job proxy)."""
    _ = openrouter_api_key

    role = await db.fetchrow(
        "SELECT id, title, hiring_brief, recruiter_id FROM public.roles WHERE id = $1",
        role_id,
    )
    if not role:
        return SearchCandidatesResult(
            candidates=[],
            count=0,
            diagnostic="role_not_found",
            diagnostic_message="Role not found.",
        )

    job_id, published, err = await ensure_role_scoring_job(
        db,
        role_id=role_id,
        recruiter_id=role["recruiter_id"],
    )
    if err or not job_id:
        return SearchCandidatesResult(
            candidates=[],
            count=0,
            diagnostic=err or "mirror_failed",
            diagnostic_message="Couldn't prepare this role for candidate search.",
        )

    engine = MatchingEngine(db)
    await engine.score_job(str(job_id), limit=500, notify=False)

    ranked = await rank_candidates_for_job(db, job_id=job_id, limit=limit)

    if not ranked:
        msg = (
            "No candidates matched yet. Try publishing the role, widening comp or "
            "location in the brief, or check back after more candidates join."
        )
        if not published:
            msg = (
                "Search is ready but no strong matches yet. Publish the role to the "
                "marketplace so candidates can discover it, or relax must-haves in the brief."
            )
        return SearchCandidatesResult(
            candidates=[],
            count=0,
            diagnostic="no_matches",
            diagnostic_message=msg,
            job_id=str(job_id),
            published=published,
        )

    for item in ranked:
        cid = item["candidate_id"]
        await db.execute(
            """
            INSERT INTO public.role_pipeline
              (role_id, candidate_id, stage, match_score, criterion_scores)
            VALUES ($1, $2, 'search', $3, $4::jsonb)
            ON CONFLICT (role_id, candidate_id) DO UPDATE SET
              match_score = EXCLUDED.match_score,
              criterion_scores = EXCLUDED.criterion_scores,
              is_public_search = $5,
              updated_at = NOW()
            """,
            role_id,
            cid,
            item.get("overall_score"),
            json.dumps(item.get("scores", {})),
            public_profiles,
        )

    if role.get("recruiter_id"):
        search_id = uuid.uuid4()
        await db.execute(
            """
            INSERT INTO public.recruiter_searches
              (id, recruiter_id, job_id, brief, status, ran_at, candidate_ids)
            VALUES ($1, $2, $3, $4, 'done', NOW(), $5)
            """,
            search_id,
            role["recruiter_id"],
            job_id,
            role.get("hiring_brief") or role["title"],
            [uuid.UUID(c["candidate_id"]) for c in ranked if c.get("candidate_id")],
        )

    candidates = await load_pipeline_candidates_for_chat(
        db,
        role_id=role_id,
        limit=limit,
        job_id=job_id,
    )
    return SearchCandidatesResult(
        candidates=candidates,
        count=len(candidates),
        diagnostic=None,
        job_id=str(job_id),
        published=published,
    )


async def load_pipeline_candidates_for_chat(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    limit: int = 25,
    job_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Load pipeline rows with full candidate profile fields for chat cards."""
    if job_id is None:
        job_id = await _job_id_for_role_pipeline(db, role_id)

    rows = await db.fetch(
        """
        SELECT p.id AS pipeline_id, p.stage, p.match_score, p.criterion_scores,
               c.id::text AS candidate_id,
               c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state,
               c.skills, c.looking_for, c.remote_preference, c.notice_period_days,
               c.expected_ctc_min, c.expected_ctc_max, c.current_ctc,
               u.full_name AS display_name,
               ms.explanation AS match_explanation,
               ms.skills_score,
               j.skills_required
        FROM public.role_pipeline p
        JOIN public.candidates c ON c.id = p.candidate_id AND c.deleted_at IS NULL
        JOIN public.users u ON u.id = c.user_id
        LEFT JOIN public.match_scores ms
          ON ms.candidate_id = c.id AND ms.job_id = $3::uuid
        LEFT JOIN public.jobs j ON j.id = $3::uuid
        WHERE p.role_id = $1
          AND c.share_with_recruiters = TRUE
          AND c.visibility <> 'private'
        ORDER BY p.match_score DESC NULLS LAST, p.moved_at DESC
        LIMIT $2
        """,
        role_id,
        limit,
        job_id,
    )
    return [_serialize_candidate_card(r) for r in rows]


def _candidate_search_clause(param_ref: str) -> str:
    """ILIKE filter on name, title, company, headline, skills, looking_for."""
    return f"""
      AND (
        u.full_name ILIKE {param_ref}
        OR c.headline ILIKE {param_ref}
        OR c.current_title ILIKE {param_ref}
        OR c.current_company ILIKE {param_ref}
        OR c.looking_for ILIKE {param_ref}
        OR EXISTS (
          SELECT 1 FROM unnest(COALESCE(c.skills, ARRAY[]::text[])) s
          WHERE s ILIKE {param_ref}
        )
      )
    """


def _serialize_directory_row(row: asyncpg.Record) -> dict[str, Any]:
    from hireloop_api.services.display_name import sanitize_display_name

    d = dict(row)
    cid = str(d["candidate_id"])
    skills = d.get("skills")
    if isinstance(skills, list):
        skills_list = [str(s) for s in skills if str(s).strip()]
    else:
        skills_list = []

    slug = d.get("public_slug")
    public_enabled = bool(d.get("public_profile_enabled"))
    public_url = f"/p/{slug}" if slug and public_enabled else None

    return {
        "candidate_id": cid,
        "display_name": sanitize_display_name(d.get("full_name")) or "Candidate",
        "headline": d.get("headline"),
        "summary": d.get("summary"),
        "current_title": d.get("current_title"),
        "current_company": d.get("current_company"),
        "location_city": d.get("location_city"),
        "location_state": d.get("location_state"),
        "years_experience": d.get("years_experience"),
        "looking_for": d.get("looking_for"),
        "skills": skills_list[:12],
        "role_id": str(d["role_id"]) if d.get("role_id") else None,
        "role_title": d.get("role_title"),
        "pipeline_stage": d.get("pipeline_stage"),
        "match_score": float(d["match_score"]) if d.get("match_score") is not None else None,
        "source": d.get("source") or "discover",
        "public_profile_url": public_url,
    }


async def list_recruiter_candidates(
    db: asyncpg.Connection,
    *,
    recruiter_id: uuid.UUID,
    q: str | None = None,
    role_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Pipeline matches plus opted-in talent pool for the recruiter directory."""
    query = (q or "").strip()
    pattern = f"%{query}%" if query else None
    search_sql = _candidate_search_clause("$4") if pattern else ""

    pipeline_rows = await db.fetch(
        f"""
        SELECT DISTINCT ON (c.id)
          c.id AS candidate_id,
          u.full_name,
          c.headline,
          c.summary,
          c.current_title,
          c.current_company,
          c.location_city,
          c.location_state,
          c.years_experience,
          c.skills,
          c.looking_for,
          c.public_slug,
          c.public_profile_enabled,
          r.id AS role_id,
          r.title AS role_title,
          p.stage AS pipeline_stage,
          p.match_score,
          'pipeline' AS source
        FROM public.role_pipeline p
        JOIN public.roles r ON r.id = p.role_id
        JOIN public.candidates c ON c.id = p.candidate_id
        JOIN public.users u ON u.id = c.user_id
        JOIN public.recruiters rec ON rec.id = r.recruiter_id
        WHERE r.recruiter_id = $1
          AND r.deleted_at IS NULL
          AND c.deleted_at IS NULL
          AND u.deleted_at IS NULL
          AND c.user_id <> rec.user_id
          AND ($2::uuid IS NULL OR r.id = $2::uuid)
          {search_sql}
        ORDER BY c.id, p.match_score DESC NULLS LAST
        LIMIT $3
        """,
        recruiter_id,
        role_id,
        limit,
        *([pattern] if pattern else []),
    )

    seen = {str(r["candidate_id"]) for r in pipeline_rows}
    remaining = max(0, limit - len(pipeline_rows))
    discover_rows: list[asyncpg.Record] = []
    if remaining > 0:
        exclude_ids = [uuid.UUID(cid) for cid in seen]
        discover_search = _candidate_search_clause("$2") if pattern else ""
        discover_rows = await db.fetch(
            f"""
            SELECT
              c.id AS candidate_id,
              u.full_name,
              c.headline,
              c.summary,
              c.current_title,
              c.current_company,
              c.location_city,
              c.location_state,
              c.years_experience,
              c.skills,
              c.looking_for,
              c.public_slug,
              c.public_profile_enabled,
              NULL::uuid AS role_id,
              NULL::text AS role_title,
              NULL::text AS pipeline_stage,
              NULL::real AS match_score,
              'discover' AS source
            FROM public.candidates c
            JOIN public.users u ON u.id = c.user_id
            JOIN public.recruiters rec ON rec.id = $3
            WHERE c.deleted_at IS NULL
              AND u.deleted_at IS NULL
              AND c.share_with_recruiters = TRUE
              AND c.visibility IN ('open_to_matches', 'exceptional_only')
              AND c.user_id <> rec.user_id
              AND NOT (c.id = ANY($4::uuid[]))
              {discover_search}
            ORDER BY c.updated_at DESC NULLS LAST
            LIMIT $1
            """,
            remaining,
            *([pattern] if pattern else []),
            recruiter_id,
            exclude_ids,
        )

    results: list[dict[str, Any]] = []
    for row in list(pipeline_rows) + list(discover_rows):
        results.append(_serialize_directory_row(row))
        if len(results) >= limit:
            break
    return results


async def shortlist_top_candidates(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    count: int = 1,
) -> int:
    """Move top search-stage candidates to shortlisted."""
    rows = await db.fetch(
        """
        SELECT id FROM public.role_pipeline
        WHERE role_id = $1 AND stage = 'search'
        ORDER BY match_score DESC NULLS LAST
        LIMIT $2
        """,
        role_id,
        count,
    )
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    await db.execute(
        """
        UPDATE public.role_pipeline
        SET stage = 'shortlisted', moved_at = NOW(), updated_at = NOW()
        WHERE id = ANY($1::uuid[])
        """,
        ids,
    )
    return len(ids)


async def is_role_published(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
) -> bool:
    val = await db.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM public.jobs
          WHERE role_id = $1::uuid AND deleted_at IS NULL AND is_active = TRUE
        )
        """,
        role_id,
    )
    return bool(val)
