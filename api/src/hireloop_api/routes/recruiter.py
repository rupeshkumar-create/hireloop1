"""
Recruiter routes - Nitya side (P16-P18).

Roles, hiring brief, candidate search, pipeline, inbox.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from hireloop_api.agents.nitya.recruiter_chat import (
    MAX_RECRUITER_TURNS,
    POST_BRIEF_CHIPS,
    ensure_nitya_conversation,
    persist_role_from_brief,
    run_nitya_post_brief_turn,
    run_nitya_turn,
    shortlist_count_from_text,
    wants_candidate_search,
    wants_shortlist,
)
from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_current_user, get_db, get_recruiter_user
from hireloop_api.services.public_role import public_role_path
from hireloop_api.services.recruiter_nudges import compute_recruiter_nudges
from hireloop_api.services.recruiter_search import (
    is_role_published,
    list_recruiter_candidates,
    load_pipeline_candidates_for_chat,
    search_candidates_for_role,
    shortlist_top_candidates,
)
from hireloop_api.services.role_inbound import add_external_candidate
from hireloop_api.services.role_interview_kit import generate_interview_kit
from hireloop_api.services.role_jd_bias import scan_jd_bias
from hireloop_api.services.role_jd_extract import (
    apply_extraction_to_role,
    compute_role_readiness,
    extract_role_from_jd,
    suggest_chips_for_reply,
)
from hireloop_api.services.role_jd_fetch import (
    RoleImportError,
    fetch_role_from_url,
    infer_role_location,
    location_conflicts_with_title,
    merge_import_warnings,
)
from hireloop_api.services.role_market_intel import compute_role_market_intel

logger = structlog.get_logger()
router = APIRouter(prefix="/recruiter", tags=["recruiter"])

_JSONB_COLS = (
    "jd_structured",
    "must_haves",
    "nice_to_haves",
    "evaluation_criteria",
    "calibration_candidates",
    "jd_bias_report",
    "interview_kit",
    "market_intel_cache",
)


def _serialize_role(row: asyncpg.Record | dict) -> dict[str, Any]:
    d = dict(row)
    for key in _JSONB_COLS:
        val = d.get(key)
        if isinstance(val, str):
            try:
                d[key] = json.loads(val)
            except (ValueError, TypeError):
                pass
    for key in ("id", "company_id", "recruiter_id"):
        if d.get(key) is not None:
            d[key] = str(d[key])
    if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
        d["created_at"] = d["created_at"].isoformat()
    if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
        d["updated_at"] = d["updated_at"].isoformat()
    slug = d.get("public_slug")
    if slug and d.get("public_listing_enabled"):
        d["public_role_url"] = public_role_path(str(slug))
    else:
        d["public_role_url"] = None
    d["readiness"] = compute_role_readiness(d)
    return d


class CreateRoleRequest(BaseModel):
    title: str
    jd_text: str | None = None
    company_id: uuid.UUID | None = None
    company_name: str | None = None
    duplicate_from_role_id: uuid.UUID | None = None
    comp_min_lpa: int | None = None
    comp_max_lpa: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    remote_policy: str | None = Field(
        default=None,
        pattern="^(onsite|hybrid|remote|flex)$",
    )
    seniority: str | None = Field(
        default=None,
        pattern="^(junior|mid|senior|lead|manager|director)$",
    )


class ImportRoleUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class ImportRoleUrlResponse(BaseModel):
    title: str | None = None
    jd_text: str | None = None
    company_name: str | None = None
    comp_min_lpa: int | None = None
    comp_max_lpa: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    remote_policy: str | None = None
    seniority: str | None = None
    source_url: str
    source_type: str
    extraction: dict[str, Any] | None = None
    warnings: list[str] = []
    ready_for_brief: bool = False


class UpdateRoleRequest(BaseModel):
    title: str | None = None
    jd_text: str | None = None
    comp_min_lpa: int | None = None
    comp_max_lpa: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    remote_policy: str | None = Field(
        default=None,
        pattern="^(onsite|hybrid|remote|flex)$",
    )
    seniority: str | None = Field(
        default=None,
        pattern="^(junior|mid|senior|lead|manager|director)$",
    )
    hiring_brief: str | None = None
    candidate_pitch: str | None = None
    must_haves: list[str] | None = None
    nice_to_haves: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(draft|hiring|paused|closed)$")
    calendly_url: str | None = Field(default=None, max_length=2048)


class NityaMessageRequest(BaseModel):
    content: str = ""
    role_id: str | None = None
    bootstrap: bool = False


class PipelineMoveRequest(BaseModel):
    stage: str | None = Field(
        default=None,
        pattern="^(search|shortlisted|intro_requested|intro_made|interview|offer|hired|archived)$",
    )
    notes: str | None = Field(default=None, max_length=4000)


class CalibrationEntry(BaseModel):
    candidate_id: uuid.UUID | None = None
    inbound_applicant_id: uuid.UUID | None = None
    verdict: str = Field(..., pattern="^(ideal|borderline|reject)$")


class SetCalibrationRequest(BaseModel):
    entries: list[CalibrationEntry] = Field(..., min_length=1, max_length=5)


class AddExternalCandidateRequest(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    linkedin_url: str | None = Field(default=None, max_length=2048)


class RunSearchRequest(BaseModel):
    public_profiles: bool = False
    limit: int = Field(default=25, ge=1, le=100)


class UpdateRecruiterProfileRequest(BaseModel):
    company_name: str | None = None
    recruiter_title: str | None = None
    hiring_focus: str | None = None
    onboarding_complete: bool | None = None


@router.get("/me")
async def get_recruiter_profile(
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    from hireloop_api.services.recruiter_profile import (
        build_hiring_focus_from_roles,
        fetch_recruiter_role_rows,
        resolve_company_name_from_roles,
        serialize_active_roles,
    )

    recruiter = current_user["recruiter"]
    company = None
    if recruiter.get("company_id"):
        company = await db.fetchrow(
            "SELECT id, name FROM public.companies WHERE id = $1",
            recruiter["company_id"],
        )
    state = recruiter.get("nitya_state") or {}
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except (ValueError, TypeError):
            state = {}
    role_rows = await fetch_recruiter_role_rows(db, recruiter["id"])
    derived_focus = build_hiring_focus_from_roles(role_rows)
    derived_company = resolve_company_name_from_roles(company, role_rows)
    profile_from_roles = bool(role_rows)
    hiring_focus_source = "roles" if derived_focus else "manual"
    hiring_focus = derived_focus if derived_focus else state.get("hiring_focus")
    company_name = derived_company if derived_company else (company["name"] if company else None)
    return {
        "recruiter_id": str(recruiter["id"]),
        "title": recruiter.get("title"),
        "company_name": company_name,
        "company_id": str(recruiter["company_id"]) if recruiter.get("company_id") else None,
        "onboarding_complete": bool(state.get("onboarding_complete")),
        "hiring_focus": hiring_focus,
        "hiring_focus_source": hiring_focus_source,
        "profile_from_roles": profile_from_roles,
        "active_roles": serialize_active_roles(role_rows),
    }


@router.patch("/me")
async def update_recruiter_profile(
    body: UpdateRecruiterProfileRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    if body.recruiter_title is not None:
        await db.execute(
            "UPDATE public.recruiters SET title = $2, updated_at = NOW() WHERE id = $1",
            recruiter["id"],
            body.recruiter_title.strip() or None,
        )
    from hireloop_api.services.recruiter_profile import fetch_recruiter_role_rows

    role_rows = await fetch_recruiter_role_rows(db, recruiter["id"])
    profile_from_roles = bool(role_rows)
    if body.company_name and recruiter.get("company_id") and not profile_from_roles:
        await db.execute(
            "UPDATE public.companies SET name = $2, updated_at = NOW() WHERE id = $1",
            recruiter["company_id"],
            body.company_name.strip(),
        )
    state = recruiter.get("nitya_state") or {}
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except (ValueError, TypeError):
            state = {}
    if not isinstance(state, dict):
        state = {}
    if body.hiring_focus is not None and not profile_from_roles:
        state["hiring_focus"] = body.hiring_focus.strip() or None
    if body.onboarding_complete is not None:
        state["onboarding_complete"] = body.onboarding_complete
    await db.execute(
        "UPDATE public.recruiters SET nitya_state = $2::jsonb, updated_at = NOW() WHERE id = $1",
        recruiter["id"],
        json.dumps(state),
    )
    return await get_recruiter_profile(current_user=current_user, db=db)


@router.get("/dashboard")
async def recruiter_dashboard(
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Recruiter home — role stats, Nitya chats, and inbox summary."""
    recruiter = current_user.get("recruiter")
    if not recruiter:
        return {
            "stats": {
                "active_roles": 0,
                "pipeline_total": 0,
                "pending_intros": 0,
            },
            "chats": [],
            "roles": [],
        }

    recruiter_id = recruiter["id"]
    stats_row = await db.fetchrow(
        """
        SELECT
          (SELECT count(*)::int FROM public.roles r
             WHERE r.recruiter_id = $1 AND r.deleted_at IS NULL
               AND r.status IN ('active', 'hiring', 'draft')) AS active_roles,
          (SELECT count(*)::int FROM public.role_pipeline p
             JOIN public.roles r ON r.id = p.role_id
             WHERE r.recruiter_id = $1 AND r.deleted_at IS NULL) AS pipeline_total,
          (SELECT count(*)::int FROM public.intro_requests ir
             WHERE ir.recruiter_id = $1
               AND ir.direction = 'candidate_to_recruiter'
               AND ir.status = 'pending') AS pending_intros
        """,
        recruiter_id,
    )

    chat_rows = await db.fetch(
        """
        SELECT c.id, c.title, c.role_id, c.updated_at,
               r.title AS role_title, r.status AS role_status,
               (
                 SELECT m.content
                 FROM public.messages m
                 WHERE m.conversation_id = c.id
                   AND m.role IN ('user', 'assistant')
                 ORDER BY m.created_at DESC
                 LIMIT 1
               ) AS last_message
        FROM public.conversations c
        LEFT JOIN public.roles r ON r.id = c.role_id
        WHERE c.recruiter_id = $1
          AND c.agent = 'nitya'
          AND c.deleted_at IS NULL
        ORDER BY c.updated_at DESC
        LIMIT 20
        """,
        recruiter_id,
    )

    role_rows = await db.fetch(
        """
        SELECT id, title, status, location_city, updated_at, public_slug, public_listing_enabled,
               (SELECT count(*)::int FROM public.role_pipeline p
                  WHERE p.role_id = roles.id) AS pipeline_count
        FROM public.roles
        WHERE recruiter_id = $1 AND deleted_at IS NULL
        ORDER BY updated_at DESC
        LIMIT 8
        """,
        recruiter_id,
    )

    chats: list[dict[str, Any]] = []
    for row in chat_rows:
        d = dict(row)
        d["id"] = str(d["id"])
        if d.get("role_id"):
            d["role_id"] = str(d["role_id"])
        if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        preview = (d.get("last_message") or "").strip()
        d["last_message"] = preview[:160] + ("…" if len(preview) > 160 else "")
        chats.append(d)

    roles: list[dict[str, Any]] = []
    for row in role_rows:
        d = dict(row)
        d["id"] = str(d["id"])
        if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        slug = d.get("public_slug")
        d["public_role_url"] = (
            public_role_path(str(slug)) if slug and d.get("public_listing_enabled") else None
        )
        roles.append(d)

    return {
        "stats": dict(stats_row) if stats_row else {},
        "chats": chats,
        "roles": roles,
    }


@router.get("/candidates")
async def recruiter_candidate_directory(
    q: str | None = Query(default=None, max_length=100),
    role_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Browse live platform candidates and pipeline matches (optional search filter)."""
    recruiter = current_user["recruiter"]
    candidates = await list_recruiter_candidates(
        db,
        recruiter_id=recruiter["id"],
        q=q,
        role_id=role_id,
        limit=limit,
    )
    return {
        "query": (q or "").strip() or None,
        "count": len(candidates),
        "candidates": candidates,
    }


@router.get("/candidates/search")
async def search_recruiter_candidates(
    q: str = Query(..., min_length=2, max_length=100),
    role_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Find candidates in pipeline or opted-in talent pool."""
    recruiter = current_user["recruiter"]
    candidates = await list_recruiter_candidates(
        db,
        recruiter_id=recruiter["id"],
        q=q,
        role_id=role_id,
        limit=limit,
    )
    return {"query": q.strip(), "count": len(candidates), "candidates": candidates}


@router.get("/inbox")
async def recruiter_inbox(
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Cross-role updates for default recruiter landing (P18)."""
    recruiter = current_user.get("recruiter")
    if not recruiter:
        return {"items": [], "roles": []}

    intros = await db.fetch(
        """
        SELECT ir.id, ir.status, ir.direction, ir.updated_at, ir.created_at,
               j.title AS job_title,
               c.id AS candidate_id, c.headline AS candidate_headline,
               cu.full_name AS candidate_name,
               r.title AS role_title
        FROM public.intro_requests ir
        JOIN public.jobs j ON j.id = ir.job_id
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users cu ON cu.id = c.user_id
        LEFT JOIN public.roles r ON r.id = ir.role_id
        WHERE ir.recruiter_id = $1
          AND NOT (
            ir.direction = 'candidate_to_hm'
            AND ir.status IN ('draft_ready', 'sent')
          )
        ORDER BY ir.updated_at DESC
        LIMIT 30
        """,
        recruiter["id"],
    )

    roles = await db.fetch(
        """
        SELECT id, title, status, updated_at, public_slug, public_listing_enabled,
               (SELECT count(*) FROM public.role_pipeline p
                  WHERE p.role_id = roles.id) AS pipeline_count
        FROM public.roles
        WHERE recruiter_id = $1 AND deleted_at IS NULL
        ORDER BY updated_at DESC
        """,
        recruiter["id"],
    )

    role_rows = []
    for r in roles:
        d = dict(r)
        d["id"] = str(d["id"])
        if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        slug = d.get("public_slug")
        d["public_role_url"] = (
            public_role_path(str(slug)) if slug and d.get("public_listing_enabled") else None
        )
        role_rows.append(d)

    return {
        "items": [dict(r) for r in intros],
        "roles": role_rows,
    }


@router.get("/roles")
async def list_roles(
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    recruiter = current_user["recruiter"]
    rows = await db.fetch(
        """
        SELECT r.id, r.title, r.status, r.location_city, r.comp_min, r.comp_max,
               r.version, r.created_at, r.updated_at, r.public_slug, r.public_listing_enabled,
               (r.hiring_brief IS NOT NULL) AS has_brief,
               EXISTS(
                 SELECT 1 FROM public.jobs j
                 WHERE j.role_id = r.id AND j.deleted_at IS NULL AND j.is_active = TRUE
               ) AS published,
               (SELECT count(*)::int FROM public.role_pipeline p
                WHERE p.role_id = r.id) AS pipeline_count
        FROM public.roles r
        WHERE r.recruiter_id = $1 AND r.deleted_at IS NULL
        ORDER BY r.updated_at DESC
        """,
        recruiter["id"],
    )
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        if d.get("updated_at") and hasattr(d["updated_at"], "isoformat"):
            d["updated_at"] = d["updated_at"].isoformat()
        slug = d.get("public_slug")
        d["public_role_url"] = (
            public_role_path(str(slug)) if slug and d.get("public_listing_enabled") else None
        )
        out.append(d)
    return out


@router.post("/roles/import-url", response_model=ImportRoleUrlResponse)
async def import_role_from_url(
    body: ImportRoleUrlRequest,
    current_user: dict = Depends(get_recruiter_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Crawl a public job posting URL and return structured fields for the new-role form.
    Runs the same JD extraction pipeline as paste-JD create when enough text is found.
    """
    _ = current_user
    try:
        imported = await fetch_role_from_url(body.url.strip(), settings=settings)
    except RoleImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    jd_text = (imported.get("jd_text") or "").strip()
    title = (imported.get("title") or "").strip() or None
    company_name = (imported.get("company_name") or "").strip() or None
    extraction: dict[str, Any] | None = None

    comp_min_lpa: int | None = None
    comp_max_lpa: int | None = None
    location_city = imported.get("location_city")
    location_state = imported.get("location_state")
    remote_policy = imported.get("remote_policy")
    seniority: str | None = None

    if jd_text and len(jd_text) >= 40 and settings.openrouter_api_key:
        extraction = await extract_role_from_jd(
            title=title or "Role",
            jd_text=jd_text,
            settings=settings,
        )
        title = extraction.get("title") or title
        company_name = extraction.get("company_name") or company_name
        if extraction.get("comp_min_lpa") is not None:
            comp_min_lpa = int(extraction["comp_min_lpa"])
        elif extraction.get("comp_min"):
            comp_min_lpa = int(extraction["comp_min"]) // 100_000
        if extraction.get("comp_max_lpa") is not None:
            comp_max_lpa = int(extraction["comp_max_lpa"])
        elif extraction.get("comp_max"):
            comp_max_lpa = int(extraction["comp_max"]) // 100_000
        # Prefer URL-imported location; only take LLM city when it doesn't conflict
        # with the title (e.g. reject Singapore for a "US East Coast" role).
        llm_city = extraction.get("location_city")
        llm_state = extraction.get("location_state")
        if not location_city and llm_city:
            if not location_conflicts_with_title(title, str(llm_city)):
                location_city = llm_city
                location_state = llm_state or location_state
        elif location_city and llm_city and location_conflicts_with_title(title, str(llm_city)):
            pass  # keep imported city
        elif not location_city:
            location_city = llm_city
            location_state = llm_state or location_state
        refined_city, refined_state = infer_role_location(
            title=title,
            body=jd_text,
            structured_city=location_city if isinstance(location_city, str) else None,
            structured_state=location_state if isinstance(location_state, str) else None,
        )
        location_city = refined_city or location_city
        location_state = refined_state or location_state
        remote_policy = extraction.get("remote_policy") or remote_policy
        jd_struct = extraction.get("jd_structured") or {}
        if isinstance(jd_struct, dict):
            sen = jd_struct.get("seniority")
            if isinstance(sen, str) and sen in {
                "junior",
                "mid",
                "senior",
                "lead",
                "manager",
                "director",
            }:
                seniority = sen
    elif not location_city:
        location_city, location_state = infer_role_location(
            title=title,
            body=jd_text,
            structured_city=location_city if isinstance(location_city, str) else None,
            structured_state=location_state if isinstance(location_state, str) else None,
        )
    warnings = merge_import_warnings(imported, extraction)
    source_note = f"\n\nSource: {imported['source_url']}"
    if source_note.strip() not in jd_text:
        jd_text = f"{jd_text}{source_note}"

    return {
        "title": title,
        "jd_text": jd_text,
        "company_name": company_name,
        "comp_min_lpa": comp_min_lpa,
        "comp_max_lpa": comp_max_lpa,
        "location_city": location_city,
        "location_state": location_state,
        "remote_policy": remote_policy,
        "seniority": seniority,
        "source_url": imported["source_url"],
        "source_type": imported.get("source_type") or "html",
        "extraction": extraction,
        "warnings": warnings,
        "ready_for_brief": bool(jd_text and len(jd_text) >= 40),
    }


@router.post("/roles", status_code=201)
async def create_role(
    body: CreateRoleRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    recruiter = current_user["recruiter"]
    company_id = body.company_id or recruiter.get("company_id")
    imported_company = (body.company_name or "").strip() or None
    if not company_id:
        company_name = imported_company or "My Company"
        company_id = await db.fetchval(
            """
            INSERT INTO public.companies (name, country_code)
            VALUES ($1, 'IN')
            RETURNING id
            """,
            company_name,
        )
        await db.execute(
            "UPDATE public.recruiters SET company_id = $2, updated_at = NOW() WHERE id = $1",
            recruiter["id"],
            company_id,
        )
    elif imported_company:
        # Prefer an imported/real company name over the placeholder "My Company".
        await db.execute(
            """
            UPDATE public.companies
            SET name = $2, updated_at = NOW()
            WHERE id = $1
              AND (name IS NULL OR btrim(name) = '' OR lower(btrim(name)) = 'my company')
            """,
            company_id,
            imported_company,
        )

    title = body.title.strip()
    jd_text = (body.jd_text or "").strip() or None
    src: asyncpg.Record | None = None

    if body.duplicate_from_role_id:
        src = await db.fetchrow(
            """
            SELECT title, jd_text, comp_min, comp_max, location_city, location_state,
                   remote_policy, must_haves, nice_to_haves, hiring_brief, candidate_pitch,
                   evaluation_criteria, jd_structured
            FROM public.roles
            WHERE id = $1 AND recruiter_id = $2 AND deleted_at IS NULL
            """,
            body.duplicate_from_role_id,
            recruiter["id"],
        )
        if src:
            if not jd_text and src["jd_text"]:
                jd_text = src["jd_text"]
            title = title or src["title"]

    role_id = uuid.uuid4()
    conv_id = uuid.uuid4()

    comp_min = int(body.comp_min_lpa * 100_000) if body.comp_min_lpa else None
    comp_max = int(body.comp_max_lpa * 100_000) if body.comp_max_lpa else None

    await db.execute(
        """
        INSERT INTO public.roles (
          id, company_id, recruiter_id, title, jd_text, status,
          comp_min, comp_max, location_city, location_state, remote_policy
        )
        VALUES ($1, $2, $3, $4, $5, 'draft', $6, $7, $8, $9, $10)
        """,
        role_id,
        company_id,
        recruiter["id"],
        title,
        jd_text,
        comp_min,
        comp_max,
        body.location_city,
        body.location_state,
        body.remote_policy,
    )

    if body.duplicate_from_role_id and src:
        await db.execute(
            """
            UPDATE public.roles SET
              must_haves = $2::jsonb,
              nice_to_haves = $3::jsonb,
              evaluation_criteria = $4::jsonb,
              jd_structured = $5::jsonb,
              hiring_brief = COALESCE(hiring_brief, $6),
              candidate_pitch = COALESCE(candidate_pitch, $7),
              comp_min = COALESCE(comp_min, $8),
              comp_max = COALESCE(comp_max, $9),
              location_city = COALESCE(location_city, $10),
              location_state = COALESCE(location_state, $11),
              remote_policy = COALESCE(remote_policy, $12)
            WHERE id = $1
            """,
            role_id,
            json.dumps(list(src["must_haves"] or [])),
            json.dumps(list(src["nice_to_haves"] or [])),
            json.dumps(list(src["evaluation_criteria"] or [])),
            json.dumps(dict(src["jd_structured"] or {})),
            src["hiring_brief"],
            src["candidate_pitch"],
            src["comp_min"],
            src["comp_max"],
            src["location_city"],
            src["location_state"],
            src["remote_policy"],
        )

    if body.seniority:
        await db.execute(
            """
            UPDATE public.roles SET
              jd_structured = COALESCE(jd_structured, '{}'::jsonb) || $2::jsonb
            WHERE id = $1
            """,
            role_id,
            json.dumps({"seniority": body.seniority}),
        )

    extraction: dict[str, Any] | None = None
    if jd_text and len(jd_text) >= 40:
        extraction = await extract_role_from_jd(
            title=title,
            jd_text=jd_text,
            settings=settings,
        )
        await apply_extraction_to_role(db, role_id, extraction)

    await db.execute(
        """
        INSERT INTO public.conversations (id, recruiter_id, role_id, agent, title)
        VALUES ($1, $2, $3, 'nitya', $4)
        """,
        conv_id,
        recruiter["id"],
        role_id,
        f"Intake: {title}",
    )

    row = await db.fetchrow(
        "SELECT * FROM public.roles WHERE id = $1",
        role_id,
    )
    serialized = _serialize_role(row)
    skip_intake = bool(jd_text and len(jd_text) >= 40)

    return {
        "role_id": str(role_id),
        "conversation_id": str(conv_id),
        "role": serialized,
        "extraction": extraction,
        "skip_intake": skip_intake,
        "readiness": serialized["readiness"],
    }


def _format_role_context(role: dict[str, Any]) -> str:
    lines = [f"Title: {role.get('title') or ''}"]
    jd = (role.get("jd_text") or "").strip()
    if jd:
        lines.append(f"JD excerpt:\n{jd[:2500]}")
    if role.get("hiring_brief"):
        lines.append(f"Hiring brief: {role['hiring_brief']}")
    comp_min = role.get("comp_min")
    comp_max = role.get("comp_max")
    if comp_min or comp_max:
        min_lpa = int(comp_min / 100_000) if comp_min else None
        max_lpa = int(comp_max / 100_000) if comp_max else None
        lines.append(f"Comp (INR): min={min_lpa} LPA max={max_lpa} LPA")
    if role.get("location_city"):
        lines.append(f"City: {role['location_city']}")
    if role.get("remote_policy"):
        lines.append(f"Remote policy: {role['remote_policy']}")
    must = role.get("must_haves") or []
    if must:
        lines.append(f"Must-haves: {', '.join(must[:8])}")
    return "\n".join(lines)


@router.get("/roles/{role_id}")
async def get_role(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    row = await db.fetchrow(
        """
        SELECT r.*, co.name AS company_name
        FROM public.roles r
        LEFT JOIN public.companies co ON co.id = r.company_id
        WHERE r.id = $1 AND r.recruiter_id = $2 AND r.deleted_at IS NULL
        """,
        role_id,
        recruiter["id"],
    )
    if not row:
        raise HTTPException(404, "Role not found")
    serialized = _serialize_role(row)
    pipeline_count = await db.fetchval(
        """
        SELECT
          (SELECT COUNT(*) FROM public.role_pipeline WHERE role_id = $1)
          + (SELECT COUNT(*) FROM public.role_inbound_applicants WHERE role_id = $1)
        """,
        role_id,
    )
    serialized["pipeline_count"] = int(pipeline_count or 0)
    return serialized


@router.patch("/roles/{role_id}")
async def update_role(
    role_id: uuid.UUID,
    body: UpdateRoleRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    recruiter = current_user["recruiter"]
    existing = await db.fetchrow(
        "SELECT * FROM public.roles WHERE id = $1 AND recruiter_id = $2 AND deleted_at IS NULL",
        role_id,
        recruiter["id"],
    )
    if not existing:
        raise HTTPException(404, "Role not found")

    comp_min = int(body.comp_min_lpa * 100_000) if body.comp_min_lpa is not None else None
    comp_max = int(body.comp_max_lpa * 100_000) if body.comp_max_lpa is not None else None

    await db.execute(
        """
        UPDATE public.roles SET
          title = COALESCE($3, title),
          jd_text = COALESCE($4, jd_text),
          comp_min = COALESCE($5, comp_min),
          comp_max = COALESCE($6, comp_max),
          location_city = COALESCE($7, location_city),
          location_state = COALESCE($8, location_state),
          remote_policy = COALESCE($9, remote_policy),
          hiring_brief = COALESCE($10, hiring_brief),
          candidate_pitch = COALESCE($11, candidate_pitch),
          must_haves = COALESCE($12::jsonb, must_haves),
          nice_to_haves = COALESCE($13::jsonb, nice_to_haves),
          status = COALESCE($14, status),
          calendly_url = COALESCE($15, calendly_url),
          updated_at = NOW()
        WHERE id = $1 AND recruiter_id = $2
        """,
        role_id,
        recruiter["id"],
        body.title,
        body.jd_text,
        comp_min,
        comp_max,
        body.location_city,
        body.location_state,
        body.remote_policy,
        body.hiring_brief,
        body.candidate_pitch,
        json.dumps(body.must_haves) if body.must_haves is not None else None,
        json.dumps(body.nice_to_haves) if body.nice_to_haves is not None else None,
        body.status,
        body.calendly_url,
    )

    re_extract = False
    if body.jd_text and body.jd_text.strip() != (existing.get("jd_text") or "").strip():
        re_extract = True

    if re_extract and len(body.jd_text.strip()) >= 40:
        title = body.title or existing["title"]
        extraction = await extract_role_from_jd(
            title=title,
            jd_text=body.jd_text,
            settings=settings,
        )
        await apply_extraction_to_role(db, role_id, extraction)

    row = await db.fetchrow("SELECT * FROM public.roles WHERE id = $1", role_id)
    return _serialize_role(row)


@router.post("/roles/{role_id}/re-extract")
async def re_extract_role(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Re-run JD extraction for an existing role."""
    recruiter = current_user["recruiter"]
    row = await db.fetchrow(
        "SELECT title, jd_text FROM public.roles WHERE id = $1 AND recruiter_id = $2",
        role_id,
        recruiter["id"],
    )
    if not row:
        raise HTTPException(404, "Role not found")
    jd_text = (row["jd_text"] or "").strip()
    if len(jd_text) < 40:
        raise HTTPException(400, "JD too short for extraction")

    extraction = await extract_role_from_jd(
        title=row["title"],
        jd_text=jd_text,
        settings=settings,
    )
    await apply_extraction_to_role(db, role_id, extraction)
    updated = await db.fetchrow("SELECT * FROM public.roles WHERE id = $1", role_id)
    serialized = _serialize_role(updated)
    return {"role": serialized, "extraction": extraction, "readiness": serialized["readiness"]}


@router.post("/roles/{role_id}/chat/messages")
async def nitya_chat_message(
    role_id: uuid.UUID,
    body: NityaMessageRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Nitya intake message — may emit hiring brief JSON."""
    recruiter = current_user["recruiter"]
    try:
        role = await db.fetchrow(
            """
            SELECT id, company_id, title, jd_text, hiring_brief, candidate_pitch,
                   comp_min, comp_max, location_city, location_state, remote_policy,
                   must_haves, nice_to_haves, jd_structured
            FROM public.roles WHERE id = $1 AND recruiter_id = $2
            """,
            role_id,
            recruiter["id"],
        )
    except Exception as exc:
        logger.exception("nitya_chat_role_fetch_failed", role_id=str(role_id), error=str(exc)[:300])
        raise HTTPException(
            status_code=502,
            detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
        ) from exc
    if not role:
        raise HTTPException(404, "Role not found")

    try:
        conv_id = await ensure_nitya_conversation(
            db,
            recruiter_id=recruiter["id"],
            role_id=role_id,
            title=role["title"] or "Role",
        )
        history_rows = await db.fetch(
            """
            SELECT role, content FROM public.messages
            WHERE conversation_id = $1::uuid
            ORDER BY created_at ASC
            """,
            conv_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "nitya_chat_history_fetch_failed",
            role_id=str(role_id),
            error=str(exc)[:300],
        )
        raise HTTPException(
            status_code=502,
            detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
        ) from exc
    history = [{"role": r["role"], "content": r["content"]} for r in history_rows]
    recruiter_turn_count = sum(1 for h in history if h["role"] == "user")

    role_dict = dict(role)
    for key in ("must_haves", "nice_to_haves", "jd_structured"):
        val = role_dict.get(key)
        if isinstance(val, str):
            try:
                role_dict[key] = json.loads(val)
            except (ValueError, TypeError):
                pass

    content = body.content.strip()
    brief_complete = bool(role.get("hiring_brief"))
    candidates: list[dict] = []
    search_meta: dict[str, Any] | None = None
    brief: dict | None = None
    chips: list[str] = []
    reply = ""
    published = await is_role_published(db, role_id=role_id)

    if not (getattr(settings, "openrouter_api_key", "") or ""):
        raise HTTPException(
            status_code=503,
            detail="Nitya chat is temporarily unavailable (LLM not configured).",
        )

    if body.bootstrap and history:
        candidates = await load_pipeline_candidates_for_chat(db, role_id=role_id)
        reply = next(
            (h["content"] for h in reversed(history) if h["role"] == "assistant"),
            "",
        )
        if brief_complete:
            chips = list(POST_BRIEF_CHIPS)
        else:
            chips = suggest_chips_for_reply(reply, role_dict) if reply else []
    elif body.bootstrap and brief_complete:
        candidates = await load_pipeline_candidates_for_chat(db, role_id=role_id)
        if not candidates:
            try:
                sr = await search_candidates_for_role(
                    db,
                    role_id=role_id,
                    limit=25,
                    public_profiles=True,
                    openrouter_api_key=settings.openrouter_api_key,
                )
                candidates = sr.candidates
                search_meta = {
                    "diagnostic": sr.diagnostic,
                    "message": sr.diagnostic_message,
                    "published": sr.published,
                }
                if candidates:
                    await db.execute(
                        """
                        INSERT INTO public.agent_actions
                          (agent, user_id, session_id, action_type, payload, result)
                        VALUES ('nitya', $1::uuid, $2::uuid, 'candidate_search', '{}'::jsonb,
                                $3::jsonb)
                        """,
                        current_user["id"],
                        conv_id,
                        json.dumps({"count": len(candidates)}),
                    )
            except Exception as exc:
                logger.exception(
                    "nitya_candidate_search_failed_bootstrap",
                    role_id=str(role_id),
                    error=str(exc)[:300],
                )
                search_meta = {
                    "diagnostic": "search_failed",
                    "message": (
                        "Your hiring brief is ready, but candidate search hit a snag. "
                        "Try again in a moment or ask me to refresh matches."
                    ),
                    "published": published,
                }
        if search_meta and search_meta.get("diagnostic") == "no_matches":
            reply = search_meta.get("message") or (
                "Your hiring brief is ready, but I couldn't find strong matches yet. "
                "Try publishing the role or widening comp/location in the brief."
            )
        else:
            reply = (
                "Your hiring brief is ready. Here are the best matches — "
                "request an intro on anyone you'd like to meet, or ask me to refresh the search."
            )
        chips = list(POST_BRIEF_CHIPS)
        await db.execute(
            """
            INSERT INTO public.messages (conversation_id, role, content, content_type)
            VALUES ($1::uuid, 'assistant', $2, 'text')
            """,
            conv_id,
            reply,
        )
    elif body.bootstrap:
        user_message = (
            "The recruiter opened intake to refine the brief. "
            "Review the role context. Ask ONE blocking gap question "
            "(comp, location, or must-have) if unclear. Otherwise confirm readiness."
        )
        llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.4,
            max_tokens=2048,
            default_headers={
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Nitya Recruiter Chat",
            },
        )
        try:
            reply, brief, chips = await run_nitya_turn(
                db,
                llm=llm,
                user_id=current_user["id"],
                conversation_id=conv_id,
                user_message=user_message,
                history=history,
                role_context=_format_role_context(role_dict),
                role=role_dict,
                recruiter_turn_count=0,
            )
        except Exception as exc:
            logger.exception(
                "nitya_chat_bootstrap_failed", role_id=str(role_id), error=str(exc)[:300]
            )
            raise HTTPException(
                status_code=502,
                detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
            ) from exc
        await db.execute(
            """
            INSERT INTO public.messages (conversation_id, role, content, content_type)
            VALUES ($1::uuid, 'assistant', $2, 'text')
            """,
            conv_id,
            reply,
        )
    else:
        if not content:
            raise HTTPException(400, "Message content required")
        recruiter_turn_count += 1
        if role["jd_text"] and not history:
            user_message = f"JD:\n{role['jd_text']}\n\nRecruiter says: {content}"
        else:
            user_message = content
        await db.execute(
            """
            INSERT INTO public.messages (conversation_id, role, content, content_type)
            VALUES ($1::uuid, 'user', $2, 'text')
            """,
            conv_id,
            content,
        )

        llm = ChatOpenAI(
            model=settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.4,
            max_tokens=2048,
            default_headers={
                "HTTP-Referer": "https://hireschema.com",
                "X-Title": "Hireschema - Nitya Recruiter Chat",
            },
        )

        if brief_complete:
            ran_search = False
            if wants_candidate_search(content):
                try:
                    sr = await search_candidates_for_role(
                        db,
                        role_id=role_id,
                        limit=25,
                        public_profiles=True,
                        openrouter_api_key=settings.openrouter_api_key,
                    )
                    candidates = sr.candidates
                    search_meta = {
                        "diagnostic": sr.diagnostic,
                        "message": sr.diagnostic_message,
                        "published": sr.published,
                    }
                    ran_search = True
                    await db.execute(
                        """
                        INSERT INTO public.agent_actions
                          (agent, user_id, session_id, action_type, payload, result)
                        VALUES ('nitya', $1::uuid, $2::uuid, 'candidate_search', '{}'::jsonb,
                                $3::jsonb)
                        """,
                        current_user["id"],
                        conv_id,
                        json.dumps({"count": len(candidates)}),
                    )
                except Exception as exc:
                    logger.exception(
                        "nitya_candidate_search_failed_chat",
                        role_id=str(role_id),
                        error=str(exc)[:300],
                    )
                    search_meta = {
                        "diagnostic": "search_failed",
                        "message": (
                            "Candidate search hit a snag. Try again in a moment or publish the role."
                        ),
                        "published": published,
                    }
                    ran_search = True
            elif wants_shortlist(content):
                n = shortlist_count_from_text(content)
                moved = await shortlist_top_candidates(db, role_id=role_id, count=n)
                candidates = await load_pipeline_candidates_for_chat(db, role_id=role_id)
                await db.execute(
                    """
                    INSERT INTO public.agent_actions
                      (agent, user_id, session_id, action_type, payload, result)
                    VALUES ('nitya', $1::uuid, $2::uuid, 'shortlist_candidates', $3::jsonb,
                            $4::jsonb)
                    """,
                    current_user["id"],
                    conv_id,
                    json.dumps({"count": n}),
                    json.dumps({"moved": moved}),
                )
            else:
                candidates = await load_pipeline_candidates_for_chat(db, role_id=role_id)

            try:
                reply, chips = await run_nitya_post_brief_turn(
                    db,
                    llm=llm,
                    user_id=current_user["id"],
                    conversation_id=conv_id,
                    user_message=user_message,
                    history=history,
                    role_context=_format_role_context(role_dict),
                    candidate_count=len(candidates),
                )
            except Exception as exc:
                logger.exception(
                    "nitya_post_brief_chat_failed", role_id=str(role_id), error=str(exc)[:300]
                )
                raise HTTPException(
                    status_code=502,
                    detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
                ) from exc
            if ran_search and candidates:
                reply = (
                    f"Refreshed your matches — {len(candidates)} candidates in the pipeline. "
                    "Use the cards below to request intros."
                )
            elif ran_search and search_meta and search_meta.get("diagnostic") == "no_matches":
                reply = search_meta.get("message") or (
                    "No strong matches yet. Try publishing the role or relaxing must-haves."
                )
            elif ran_search and search_meta and search_meta.get("diagnostic") == "search_failed":
                reply = search_meta.get("message") or reply
            elif wants_shortlist(content):
                reply = (
                    "Shortlisted your top match"
                    + ("es" if shortlist_count_from_text(content) > 1 else "")
                    + ". Request an intro when you're ready."
                )
        else:
            try:
                reply, brief, chips = await run_nitya_turn(
                    db,
                    llm=llm,
                    user_id=current_user["id"],
                    conversation_id=conv_id,
                    user_message=user_message,
                    history=history,
                    role_context=_format_role_context(role_dict),
                    role=role_dict,
                    recruiter_turn_count=recruiter_turn_count,
                )
            except Exception as exc:
                logger.exception(
                    "nitya_chat_turn_failed", role_id=str(role_id), error=str(exc)[:300]
                )
                raise HTTPException(
                    status_code=502,
                    detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
                ) from exc

        await db.execute(
            """
            INSERT INTO public.messages (conversation_id, role, content, content_type)
            VALUES ($1::uuid, 'assistant', $2, 'text')
            """,
            conv_id,
            reply,
        )

    if brief:
        await persist_role_from_brief(
            db,
            recruiter_id=recruiter["id"],
            company_id=role["company_id"],
            role_id=role_id,
            brief=brief,
        )
        try:
            sr = await search_candidates_for_role(
                db,
                role_id=role_id,
                limit=25,
                public_profiles=True,
                openrouter_api_key=settings.openrouter_api_key,
            )
            candidates = sr.candidates
            search_meta = {
                "diagnostic": sr.diagnostic,
                "message": sr.diagnostic_message,
                "published": sr.published,
            }
            await db.execute(
                """
                INSERT INTO public.agent_actions
                  (agent, user_id, session_id, action_type, payload, result)
                VALUES ('nitya', $1::uuid, $2::uuid, 'candidate_search', '{}'::jsonb, $3::jsonb)
                """,
                current_user["id"],
                conv_id,
                json.dumps({"count": len(candidates)}),
            )
        except Exception as exc:
            logger.exception(
                "nitya_candidate_search_failed",
                role_id=str(role_id),
                error=str(exc)[:300],
            )
            search_meta = {
                "diagnostic": "search_failed",
                "message": (
                    "Your hiring brief is saved, but candidate search hit a snag. "
                    "Try again from the pipeline or ask me to refresh matches."
                ),
                "published": published,
            }
        if candidates:
            reply = (
                f"Brief saved. I found {len(candidates)} strong matches — "
                "review them below and request intros in chat."
            )
            chips = list(POST_BRIEF_CHIPS)
            await db.execute(
                """
                UPDATE public.messages SET content = $2
                WHERE conversation_id = $1::uuid AND role = 'assistant'
                  AND id = (
                    SELECT id FROM public.messages
                    WHERE conversation_id = $1::uuid AND role = 'assistant'
                    ORDER BY created_at DESC LIMIT 1
                  )
                """,
                conv_id,
                reply,
            )
        elif search_meta and search_meta.get("diagnostic") in ("search_failed", "no_matches"):
            reply = search_meta.get("message") or reply
            chips = list(POST_BRIEF_CHIPS)
            await db.execute(
                """
                UPDATE public.messages SET content = $2
                WHERE conversation_id = $1::uuid AND role = 'assistant'
                  AND id = (
                    SELECT id FROM public.messages
                    WHERE conversation_id = $1::uuid AND role = 'assistant'
                    ORDER BY created_at DESC LIMIT 1
                  )
                """,
                conv_id,
                reply,
            )

    action_rows = await db.fetch(
        """
        SELECT action_type, created_at
        FROM public.agent_actions
        WHERE session_id = $1::uuid AND agent = 'nitya'
        ORDER BY created_at DESC
        LIMIT 20
        """,
        conv_id,
    )

    updated_row = await db.fetchrow("SELECT * FROM public.roles WHERE id = $1", role_id)
    serialized = _serialize_role(updated_row)
    published = await is_role_published(db, role_id=role_id)

    return {
        "reply": reply,
        "brief_generated": brief is not None,
        "brief_complete": bool(serialized.get("hiring_brief")),
        "chip_suggestions": chips,
        "turn_count": recruiter_turn_count,
        "max_turns": MAX_RECRUITER_TURNS,
        "readiness": serialized["readiness"],
        "role": serialized,
        "action_count": len(action_rows),
        "actions": [
            {
                "type": r["action_type"],
                "at": r["created_at"].isoformat()
                if hasattr(r["created_at"], "isoformat")
                else str(r["created_at"]),
            }
            for r in action_rows
        ],
        "candidates": candidates,
        "published": published,
        "search_meta": search_meta,
    }


@router.get("/roles/{role_id}/chat/messages")
async def get_nitya_chat_history(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Persisted Nitya conversation for a role."""
    recruiter = current_user["recruiter"]
    try:
        role = await db.fetchrow(
            "SELECT id, title, hiring_brief FROM public.roles WHERE id = $1 AND recruiter_id = $2",
            role_id,
            recruiter["id"],
        )
    except Exception as exc:
        logger.exception(
            "nitya_chat_history_role_fetch_failed", role_id=str(role_id), error=str(exc)[:300]
        )
        raise HTTPException(
            status_code=502,
            detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
        ) from exc
    if not role:
        raise HTTPException(404, "Role not found")

    try:
        conv_id = await ensure_nitya_conversation(
            db,
            recruiter_id=recruiter["id"],
            role_id=role_id,
            title=role["title"] or "Role",
        )
        rows = await db.fetch(
            """
            SELECT role, content, created_at
            FROM public.messages
            WHERE conversation_id = $1::uuid
            ORDER BY created_at ASC
            """,
            conv_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "nitya_chat_history_fetch_failed", role_id=str(role_id), error=str(exc)[:300]
        )
        raise HTTPException(
            status_code=502,
            detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
        ) from exc
    messages = [
        {
            "role": r["role"],
            "content": r["content"],
            "created_at": r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat")
            else str(r["created_at"]),
        }
        for r in rows
    ]
    try:
        candidates = await load_pipeline_candidates_for_chat(db, role_id=role_id)
        published = await is_role_published(db, role_id=role_id)
    except Exception as exc:
        logger.exception(
            "nitya_chat_history_extras_failed", role_id=str(role_id), error=str(exc)[:300]
        )
        raise HTTPException(
            status_code=502,
            detail="Nitya chat is temporarily unavailable. Please try again in ~30 seconds.",
        ) from exc
    return {
        "conversation_id": str(conv_id),
        "messages": messages,
        "candidates": candidates,
        "published": published,
        "brief_complete": bool(role.get("hiring_brief")),
    }


@router.post("/roles/{role_id}/search")
async def run_role_search(
    role_id: uuid.UUID,
    body: RunSearchRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rank candidates for this role (P17)."""
    recruiter = current_user["recruiter"]
    role = await db.fetchrow(
        """
        SELECT id, title, evaluation_criteria, hiring_brief
        FROM public.roles WHERE id = $1 AND recruiter_id = $2
        """,
        role_id,
        recruiter["id"],
    )
    if not role:
        raise HTTPException(404, "Role not found")

    sr = await search_candidates_for_role(
        db,
        role_id=role_id,
        limit=body.limit,
        public_profiles=body.public_profiles,
        openrouter_api_key=settings.openrouter_api_key,
    )

    return {
        "role_id": str(role_id),
        "candidates": sr.candidates,
        "count": sr.count,
        "search_meta": {
            "diagnostic": sr.diagnostic,
            "message": sr.diagnostic_message,
            "published": sr.published,
        },
    }


@router.get("/roles/{role_id}/pipeline")
async def get_pipeline(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    recruiter = current_user["recruiter"]
    rows = await db.fetch(
        """
        SELECT p.id, p.stage, p.match_score, p.criterion_scores, p.notes,
               p.activity_status, p.is_public_search, p.moved_at,
               c.id AS candidate_id,
               'platform'::text AS source_type,
               NULL::uuid AS inbound_applicant_id,
               CASE WHEN p.stage IN ('intro_made', 'hired')
                    THEN u.full_name ELSE 'Candidate' END AS display_name,
               CASE WHEN p.stage IN ('intro_made', 'hired') THEN u.email ELSE NULL END AS email,
               c.headline, c.current_title, c.years_experience,
               NULL::text[] AS skills_matched, NULL::text[] AS skills_gap
        FROM public.role_pipeline p
        JOIN public.candidates c ON c.id = p.candidate_id
        JOIN public.users u ON u.id = c.user_id
        JOIN public.roles r ON r.id = p.role_id
        WHERE p.role_id = $1 AND r.recruiter_id = $2

        UNION ALL

        SELECT ia.id, ia.stage, ia.match_score, ia.criterion_scores, ia.notes,
               'active'::text AS activity_status, FALSE AS is_public_search, ia.moved_at,
               NULL::uuid AS candidate_id,
               'inbound'::text AS source_type,
               ia.id AS inbound_applicant_id,
               ia.full_name AS display_name,
               ia.email,
               ia.parsed_profile->>'headline' AS headline,
               ia.parsed_profile->>'current_title' AS current_title,
               (ia.parsed_profile->>'years_experience')::smallint AS years_experience,
               ia.skills_matched, ia.skills_gap
        FROM public.role_inbound_applicants ia
        JOIN public.roles r ON r.id = ia.role_id
        WHERE ia.role_id = $1 AND r.recruiter_id = $2

        ORDER BY match_score DESC NULLS LAST
        """,
        role_id,
        recruiter["id"],
    )
    return [dict(r) for r in rows]


@router.patch("/roles/{role_id}/pipeline/{pipeline_id}")
async def move_pipeline_candidate(
    role_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    body: PipelineMoveRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    if not body.stage and body.notes is None:
        raise HTTPException(400, "Provide stage and/or notes to update")

    updated_stage = body.stage
    if body.stage:
        result = await db.execute(
            """
            UPDATE public.role_pipeline p SET
              stage = $4,
              notes = COALESCE($5, notes),
              moved_at = NOW(),
              updated_at = NOW()
            FROM public.roles r
            WHERE p.id = $1 AND p.role_id = $2 AND r.id = p.role_id AND r.recruiter_id = $3
            """,
            pipeline_id,
            role_id,
            recruiter["id"],
            body.stage,
            body.notes,
        )
    else:
        result = await db.execute(
            """
            UPDATE public.role_pipeline p SET
              notes = $4,
              updated_at = NOW()
            FROM public.roles r
            WHERE p.id = $1 AND p.role_id = $2 AND r.id = p.role_id AND r.recruiter_id = $3
            """,
            pipeline_id,
            role_id,
            recruiter["id"],
            body.notes,
        )

    if result == "UPDATE 0":
        if body.stage:
            result = await db.execute(
                """
                UPDATE public.role_inbound_applicants ia SET
                  stage = $4,
                  notes = COALESCE($5, notes),
                  moved_at = NOW(),
                  updated_at = NOW()
                FROM public.roles r
                WHERE ia.id = $1 AND ia.role_id = $2 AND r.id = ia.role_id AND r.recruiter_id = $3
                """,
                pipeline_id,
                role_id,
                recruiter["id"],
                body.stage,
                body.notes,
            )
        else:
            result = await db.execute(
                """
                UPDATE public.role_inbound_applicants ia SET
                  notes = $4,
                  updated_at = NOW()
                FROM public.roles r
                WHERE ia.id = $1 AND ia.role_id = $2 AND r.id = ia.role_id AND r.recruiter_id = $3
                """,
                pipeline_id,
                role_id,
                recruiter["id"],
                body.notes,
            )
        if result == "UPDATE 0":
            raise HTTPException(404, "Pipeline entry not found")

    if body.stage == "hired":
        pipe = await db.fetchrow(
            "SELECT candidate_id FROM public.role_pipeline WHERE id = $1",
            pipeline_id,
        )
        role = await db.fetchrow(
            "SELECT company_id FROM public.roles WHERE id = $1",
            role_id,
        )
        if pipe and pipe.get("candidate_id") and role:
            await db.execute(
                """
                INSERT INTO public.placements (role_id, candidate_id, company_id, status)
                VALUES ($1, $2, $3, 'hired_unbilled')
                ON CONFLICT DO NOTHING
                """,
                role_id,
                pipe["candidate_id"],
                role["company_id"],
            )

    return {"ok": True, "stage": updated_stage}


# ── Publish a role into the candidate jobs feed + recruiter→candidate intros ──


class RequestIntroRequest(BaseModel):
    candidate_id: uuid.UUID
    message: str | None = None


@router.post("/roles/{role_id}/publish", status_code=201)
async def publish_role(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Mirror this role into the candidate-facing jobs feed so candidates can
    discover it and request intros. Embeds the job (off-request) so it ranks in
    the candidate match feed."""
    from hireloop_api.services.background_jobs import JOB_EMBED, JOB_SCORE, enqueue_job
    from hireloop_api.services.intro_service import publish_role_to_jobs

    recruiter = current_user["recruiter"]
    result = await publish_role_to_jobs(db, role_id=str(role_id), recruiter_id=str(recruiter["id"]))
    if result.get("error"):
        raise HTTPException(404, result["error"])

    job_id = result.get("job_id")
    if job_id:
        await enqueue_job(
            db,
            kind=JOB_EMBED,
            payload={"job_id": str(job_id)},
            idempotency_key=f"job_embed:{job_id}",
        )
        await enqueue_job(
            db,
            kind=JOB_SCORE,
            payload={"job_id": str(job_id)},
            idempotency_key=f"job_score:{job_id}",
        )
    return result


@router.post("/roles/{role_id}/intro", status_code=201)
async def request_candidate_intro(
    role_id: uuid.UUID,
    body: RequestIntroRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Recruiter requests an intro to a specific candidate for this role."""
    from hireloop_api.services.intro_service import create_recruiter_intro

    result = await create_recruiter_intro(
        db,
        user_id=str(current_user["id"]),
        role_id=str(role_id),
        candidate_id=str(body.candidate_id),
        message=body.message,
    )
    if result.get("error"):
        code = 409 if result.get("code") == "role_not_published" else 404
        raise HTTPException(code, result["error"])
    return result


@router.post("/intros/{intro_id}/respond", status_code=200)
async def recruiter_respond_intro(
    intro_id: uuid.UUID,
    accept: bool = True,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Recruiter accepts or declines a candidate→recruiter intro request."""
    recruiter = current_user["recruiter"]
    new_status = "accepted" if accept else "declined"
    result = await db.execute(
        """
        UPDATE public.intro_requests
        SET status = $3, updated_at = NOW()
        WHERE id = $1::uuid
          AND recruiter_id = $2::uuid
          AND direction = 'candidate_to_recruiter'
          AND status IN ('pending', 'invited')
        """,
        intro_id,
        recruiter["id"],
        new_status,
    )
    if result == "UPDATE 0":
        raise HTTPException(409, "Nothing to respond to for this recruiter.")

    intro = await db.fetchrow(
        """
        SELECT ir.candidate_id, ir.job_id, j.title AS job_title, co.name AS company_name,
               cu.id AS candidate_user_id, cu.full_name AS candidate_name, cu.email
        FROM public.intro_requests ir
        JOIN public.candidates c ON c.id = ir.candidate_id
        JOIN public.users cu ON cu.id = c.user_id
        JOIN public.jobs j ON j.id = ir.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        WHERE ir.id = $1::uuid
        """,
        intro_id,
    )
    if intro and accept:
        await db.execute(
            """
            UPDATE public.role_pipeline
            SET stage = 'intro_made', moved_at = NOW(), updated_at = NOW()
            WHERE candidate_id = $1::uuid
              AND role_id IN (SELECT role_id FROM public.jobs WHERE id = $2::uuid)
            """,
            intro["candidate_id"],
            intro["job_id"],
        )

    if intro:
        from hireloop_api.config import get_settings
        from hireloop_api.services.notifications import notify_intro_lifecycle

        settings = get_settings()
        event = "accepted" if accept else "declined"
        await notify_intro_lifecycle(
            db,
            settings,
            intro_id=str(intro_id),
            event=event,
            recipient_user_id=str(intro["candidate_user_id"]),
            title=f"Intro {event}",
            body=(
                f"Your intro request for {intro['job_title']} was {event}."
                if accept
                else f"The recruiter declined your intro for {intro['job_title']}."
            ),
            email_template_data={
                "full_name": intro["candidate_name"] or "there",
                "hm_name": "the recruiter",
                "company_name": intro["company_name"] or "the company",
                "job_title": intro["job_title"] or "the role",
                "status": event,
                "status_message": f"Your intro was {event}.",
                "cta_url": f"{settings.allowed_origins[0] if settings.allowed_origins else 'https://hireschema.com'}/intros",
            },
        )

    return {"intro_id": str(intro_id), "status": new_status}


# ── Recruiter package layers (intelligence, triage, ops) ─────────────────────


async def _fetch_role_for_recruiter(
    db: asyncpg.Connection,
    *,
    role_id: uuid.UUID,
    recruiter_id: uuid.UUID,
) -> asyncpg.Record | None:
    return await db.fetchrow(
        """
        SELECT r.*, co.name AS company_name
        FROM public.roles r
        LEFT JOIN public.companies co ON co.id = r.company_id
        WHERE r.id = $1 AND r.recruiter_id = $2 AND r.deleted_at IS NULL
        """,
        role_id,
        recruiter_id,
    )


@router.get("/nudges")
async def recruiter_nudges(
    role_id: uuid.UUID | None = None,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    nudges = await compute_recruiter_nudges(
        db,
        recruiter_id=str(recruiter["id"]),
        role_id=str(role_id) if role_id else None,
    )
    return {"nudges": nudges}


@router.post("/roles/{role_id}/jd-bias-check")
async def role_jd_bias_check(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    row = await _fetch_role_for_recruiter(db, role_id=role_id, recruiter_id=recruiter["id"])
    if not row:
        raise HTTPException(404, "Role not found")
    report = scan_jd_bias(row.get("jd_text"))
    await db.execute(
        """
        UPDATE public.roles SET jd_bias_report = $2::jsonb, updated_at = NOW()
        WHERE id = $1
        """,
        role_id,
        json.dumps(report),
    )
    updated = await db.fetchrow("SELECT * FROM public.roles WHERE id = $1", role_id)
    return {"report": report, "role": _serialize_role(updated)}


@router.get("/roles/{role_id}/salary-suggestion")
async def role_salary_suggestion(
    role_id: uuid.UUID,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    row = await _fetch_role_for_recruiter(db, role_id=role_id, recruiter_id=recruiter["id"])
    if not row:
        raise HTTPException(404, "Role not found")
    role_dict = dict(row)
    intel = await compute_role_market_intel(db, role_dict, market="IN")
    return {
        "comp_min": role_dict.get("comp_min"),
        "comp_max": role_dict.get("comp_max"),
        "suggestion": intel.get("comp"),
    }


@router.get("/roles/{role_id}/market-intel")
async def role_market_intel(
    role_id: uuid.UUID,
    refresh: bool = False,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    row = await _fetch_role_for_recruiter(db, role_id=role_id, recruiter_id=recruiter["id"])
    if not row:
        raise HTTPException(404, "Role not found")
    role_dict = dict(row)
    cache = role_dict.get("market_intel_cache")
    if isinstance(cache, str):
        try:
            cache = json.loads(cache)
        except (ValueError, TypeError):
            cache = None
    if cache and not refresh:
        return {"intel": cache, "cached": True}

    intel = await compute_role_market_intel(db, role_dict, market="IN")
    await db.execute(
        """
        UPDATE public.roles
        SET market_intel_cache = $2::jsonb, market_intel_cached_at = NOW(), updated_at = NOW()
        WHERE id = $1
        """,
        role_id,
        json.dumps(intel),
    )
    return {"intel": intel, "cached": False}


@router.get("/roles/{role_id}/interview-kit")
async def role_interview_kit(
    role_id: uuid.UUID,
    refresh: bool = False,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    row = await _fetch_role_for_recruiter(db, role_id=role_id, recruiter_id=recruiter["id"])
    if not row:
        raise HTTPException(404, "Role not found")
    role_dict = dict(row)
    kit = role_dict.get("interview_kit")
    if isinstance(kit, str):
        try:
            kit = json.loads(kit)
        except (ValueError, TypeError):
            kit = None
    if kit and not refresh:
        return {"kit": kit, "cached": True}

    kit = generate_interview_kit(role_dict)
    await db.execute(
        """
        UPDATE public.roles SET interview_kit = $2::jsonb, updated_at = NOW()
        WHERE id = $1
        """,
        role_id,
        json.dumps(kit),
    )
    return {"kit": kit, "cached": False}


@router.put("/roles/{role_id}/calibration")
async def set_role_calibration(
    role_id: uuid.UUID,
    body: SetCalibrationRequest,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    recruiter = current_user["recruiter"]
    row = await _fetch_role_for_recruiter(db, role_id=role_id, recruiter_id=recruiter["id"])
    if not row:
        raise HTTPException(404, "Role not found")

    entries = []
    for e in body.entries:
        entry: dict[str, Any] = {"verdict": e.verdict}
        if e.candidate_id:
            entry["candidate_id"] = str(e.candidate_id)
        if e.inbound_applicant_id:
            entry["inbound_applicant_id"] = str(e.inbound_applicant_id)
        entries.append(entry)

    await db.execute(
        """
        UPDATE public.roles SET calibration_candidates = $2::jsonb, updated_at = NOW()
        WHERE id = $1
        """,
        role_id,
        json.dumps(entries),
    )
    updated = await db.fetchrow("SELECT * FROM public.roles WHERE id = $1", role_id)
    return {"calibration": entries, "role": _serialize_role(updated)}


@router.post("/roles/{role_id}/applicants", status_code=201)
async def add_role_applicant(
    role_id: uuid.UUID,
    full_name: str = Form(...),
    email: str | None = Form(default=None),
    linkedin_url: str | None = Form(default=None),
    resume: UploadFile | None = File(default=None),
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Recruiter adds external candidate — scored and added to pipeline."""
    recruiter = current_user["recruiter"]
    row = await _fetch_role_for_recruiter(db, role_id=role_id, recruiter_id=recruiter["id"])
    if not row:
        raise HTTPException(404, "Role not found")

    resume_bytes = None
    filename = "resume.pdf"
    mime_type = None
    if resume and resume.filename:
        resume_bytes = await resume.read()
        filename = resume.filename
        mime_type = resume.content_type

    try:
        result = await add_external_candidate(
            db,
            role_id=role_id,
            recruiter_id=recruiter["id"],
            full_name=full_name.strip(),
            email=email,
            linkedin_url=linkedin_url,
            resume_bytes=resume_bytes,
            filename=filename,
            mime_type=mime_type,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.get("/invite/{token}")
async def preview_invite(
    token: str,
    current_user: dict = Depends(get_current_user),  # any authed user
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Preview an intro invite (who's inviting, which candidate / job)."""
    row = await db.fetchrow(
        """
        SELECT inv.status, inv.email, inv.invited_name, inv.expires_at,
               j.title AS job_title, co.name AS company_name,
               cu.full_name AS candidate_name, c.headline AS candidate_headline
        FROM public.recruiter_invites inv
        LEFT JOIN public.jobs j ON j.id = inv.job_id
        LEFT JOIN public.companies co ON co.id = inv.company_id
        LEFT JOIN public.candidates c ON c.id = inv.candidate_id
        LEFT JOIN public.users cu ON cu.id = c.user_id
        WHERE inv.token = $1
        """,
        token,
    )
    if not row:
        raise HTTPException(404, "Invite not found")
    d = dict(row)
    d["expires_at"] = d["expires_at"].isoformat() if d["expires_at"] else None
    return d


@router.post("/invite/{token}/accept", status_code=200)
async def accept_invite_route(
    token: str,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Recruiter claims an email invite → activates the candidate's intro."""
    from hireloop_api.services.intro_service import accept_invite

    result = await accept_invite(db, user_id=str(current_user["id"]), token=token)
    if result.get("error"):
        code = 409 if result.get("code") == "inactive" else 404
        raise HTTPException(code, result["error"])
    return result


@router.get("/intros/{intro_id}/messages")
async def list_recruiter_intro_messages(
    intro_id: str,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Recruiter reads the direct chat thread for an intro."""
    from hireloop_api.services.intro_chat import list_messages

    try:
        return await list_messages(db, intro_id=intro_id, user_id=str(current_user["id"]))
    except ValueError as e:
        raise HTTPException(404, str(e)) from None


@router.post("/intros/{intro_id}/messages", status_code=201)
async def send_recruiter_intro_message(
    intro_id: str,
    body: dict,
    current_user: dict = Depends(get_recruiter_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Recruiter posts a message in an accepted intro thread."""
    from hireloop_api.services.intro_chat import post_message

    try:
        return await post_message(
            db, intro_id=intro_id, user_id=str(current_user["id"]), body=body.get("body", "")
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except PermissionError as e:
        raise HTTPException(409, str(e)) from None
