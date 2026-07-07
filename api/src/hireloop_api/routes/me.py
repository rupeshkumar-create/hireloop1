"""
User account routes — DPDP export/delete, notification prefs (P19, P23).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_db_optional, get_phone_verified_user
from hireloop_api.market_db import fetch_candidate_market, infer_market_from_geo_country
from hireloop_api.markets import (
    MARKET_LABELS,
    SUPPORTED_MARKETS,
    dial_prefix_for_market,
    job_visible_for_market_sql,
    normalize_market,
    phone_matches_market,
)
from hireloop_api.services.consent import log_consent
from hireloop_api.services.display_name import pick_display_name, sanitize_display_name
from hireloop_api.services.job_preferences import (
    VALID_REMOTE_PREFERENCES,
    apply_negative_preference,
    extract_negative_preferences,
    normalize_remote_preference,
)
from hireloop_api.services.job_present import serialize_job_card
from hireloop_api.services.linkedin_oauth import (
    extract_linkedin_display_name,
    heal_candidate_headline_from_linkedin,
)
from hireloop_api.services.notifications import default_notification_prefs
from hireloop_api.services.profile_experience import (
    build_merged_education,
    build_merged_experience,
    reconcile_candidate_overview,
)
from hireloop_api.services.rate_limit import check_rate_limit

logger = structlog.get_logger()
router = APIRouter(prefix="/me", tags=["me"])


class NotificationPrefsUpdate(BaseModel):
    prefs: dict[str, dict[str, bool]]


class OnboardingConsentRequest(BaseModel):
    tos_accepted: bool
    marketing_emails: bool = False


class CompleteOnboardingRequest(BaseModel):
    skipped_voice: bool = False
    skipped_resume: bool = False
    market: str | None = None


class MarketUpdateRequest(BaseModel):
    market: str


async def _schedule_post_consent_enrichment(
    db: asyncpg.Connection,
    settings: Settings,
    *,
    user_id: uuid.UUID,
    candidate_id: str,
) -> dict[str, Any]:
    """Run LinkedIn enrichment + CI only after explicit DPDP consent."""
    from hireloop_api.services.background_jobs import (
        CAREER_INTELLIGENCE_UPDATE,
        CAREER_PATH_UPDATE,
        MATCH_EMBED_CANDIDATE,
        enqueue_job,
    )
    from hireloop_api.services.linkedin_oauth import extract_linkedin_profile_url

    row = await db.fetchrow(
        "SELECT linkedin_data, linkedin_url FROM public.candidates WHERE id = $1::uuid",
        uuid.UUID(candidate_id),
    )
    linkedin_url = (row["linkedin_url"] if row else None) or (
        extract_linkedin_profile_url(row["linkedin_data"]) if row else None
    )
    linkedin_enrichment_scheduled = bool(
        linkedin_url and (settings.apify_token or settings.linkdapi_key)
    )
    if linkedin_enrichment_scheduled:
        # Full scrape runs immediately via asyncio.create_task in onboarding-consent
        # (run_linkedin_profile_enrichment → Apify first, LinkDAPI fallback).
        pass
    else:
        await enqueue_job(
            db,
            kind=CAREER_INTELLIGENCE_UPDATE,
            payload={"candidate_id": candidate_id, "only_if_missing": True},
            idempotency_key=f"career_intel:{candidate_id}",
        )
        await enqueue_job(
            db,
            kind=CAREER_PATH_UPDATE,
            payload={"candidate_id": candidate_id},
            idempotency_key=f"career_path_update:{candidate_id}",
        )
        await enqueue_job(
            db,
            kind=MATCH_EMBED_CANDIDATE,
            payload={"candidate_id": candidate_id},
            idempotency_key=f"match_embed_candidate:{candidate_id}",
        )
    await log_consent(
        db,
        user_id=user_id,
        purpose="linkedin_oauth_profile",
        granted=True,
    )
    return {
        "linkedin_url": linkedin_url,
        "linkedin_enrichment_scheduled": linkedin_enrichment_scheduled,
    }


_VISIBILITY_VALUES = {"open_to_matches", "exceptional_only", "private"}


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    headline: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    years_experience: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    skills: list[str] | None = None
    visibility: str | None = None
    looking_for: str | None = None
    remote_preference: str | None = None
    open_to_relocation: bool | None = None
    location_scope: str | None = None
    expected_ctc_min: int | None = None
    expected_ctc_max: int | None = None
    current_ctc: int | None = None
    notice_period_days: int | None = None
    display_currency: str | None = None
    public_profile_enabled: bool | None = None
    hide_contact_public: bool | None = None
    share_with_recruiters: bool | None = None
    tailored_resume_enabled: bool | None = None


def _serialize_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_row(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _serialize_value(val) for key, val in dict(row).items()}


async def _ensure_candidate_row(
    db: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    headline: str = "New candidate",
) -> asyncpg.Record:
    existing = await db.fetchrow(
        """
        SELECT id, market, headline, summary, current_title, current_company,
               years_experience, location_city, location_state, skills,
               profile_complete, onboarding_complete, visibility, looking_for, remote_preference,
               open_to_relocation, location_scope, expected_ctc_min, expected_ctc_max,
               current_ctc, notice_period_days,
               display_currency, public_slug, public_profile_enabled,
               hide_contact_public, share_with_recruiters, tailored_resume_enabled,
               is_active, linkedin_url, linkedin_data, career_profile, career_analysis
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    if existing:
        return existing

    row = await db.fetchrow(
        """
        INSERT INTO public.candidates (
          user_id, market, headline, profile_complete,
          hide_contact_public, share_with_recruiters, public_profile_enabled,
          tailored_resume_enabled
        )
        VALUES ($1::uuid, 'IN', $2, FALSE, TRUE, TRUE, TRUE, FALSE)
        RETURNING id, market, headline, summary, current_title, current_company,
                  years_experience, location_city, location_state, skills,
                  profile_complete, onboarding_complete, visibility, looking_for, remote_preference,
                  open_to_relocation, location_scope, expected_ctc_min, expected_ctc_max,
                  current_ctc, notice_period_days,
                  display_currency, public_slug, public_profile_enabled,
                  hide_contact_public, share_with_recruiters, tailored_resume_enabled,
                  is_active, linkedin_url, linkedin_data, career_profile, career_analysis
        """,
        user_id,
        headline,
    )
    from hireloop_api.services.public_profile import bootstrap_candidate_public_profile

    user_row = await db.fetchrow(
        "SELECT full_name FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        user_id,
    )
    await bootstrap_candidate_public_profile(
        db,
        row["id"],
        user_id=user_id,
        display_name=user_row["full_name"] if user_row else None,
    )
    refreshed = await db.fetchrow(
        """
        SELECT id, market, headline, summary, current_title, current_company,
               years_experience, location_city, location_state, skills,
               profile_complete, onboarding_complete, visibility, looking_for, remote_preference,
               open_to_relocation, location_scope, expected_ctc_min, expected_ctc_max,
               current_ctc, notice_period_days,
               display_currency, public_slug, public_profile_enabled,
               hide_contact_public, share_with_recruiters, tailored_resume_enabled,
               is_active, linkedin_url, linkedin_data, career_profile, career_analysis
        FROM public.candidates
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        row["id"],
    )
    return refreshed or row


@router.get("/access")
async def get_access_status(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Returns whether the user has unlocked the jobs/matches feed.
    Unlocked when the candidate has uploaded a resume OR completed
    a voice session with Aarya.
    """
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        current_user["id"],
    )
    if not candidate:
        return {"unlocked": False, "has_resume": False, "has_voice_session": False}

    has_resume = await db.fetchval(
        "SELECT EXISTS(SELECT 1 FROM public.resumes WHERE candidate_id = $1)",
        candidate["id"],
    )
    has_voice = await db.fetchval(
        """
        SELECT EXISTS(
          SELECT 1 FROM public.voice_sessions
          WHERE candidate_id = $1 AND status = 'completed'
        )
        """,
        candidate["id"],
    )

    return {
        "unlocked": bool(has_resume or has_voice),
        "has_resume": bool(has_resume),
        "has_voice_session": bool(has_voice),
    }


@router.patch("/market")
async def update_my_market(
    body: MarketUpdateRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """
    Update the user's home market (IN / US / GB).

    This controls job visibility/scoping. We also mirror the value onto the candidate row.
    """
    raw = (body.market or "").strip()
    market = normalize_market(raw)
    if market not in SUPPORTED_MARKETS:
        raise HTTPException(status_code=400, detail="Unsupported market")

    user_id = uuid.UUID(str(current_user["id"]))

    user_row = await db.fetchrow(
        """
        SELECT phone, phone_verified
        FROM public.users
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    if user_row and user_row["phone_verified"] and user_row["phone"]:
        if not phone_matches_market(str(user_row["phone"]), market):
            label = MARKET_LABELS.get(market, market)
            dial = dial_prefix_for_market(market)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Your verified phone doesn't match {label}. "
                    f"Re-verify with a {dial} number before switching markets."
                ),
            )

    await db.execute(
        """
        UPDATE public.users
        SET market = $2, phone_country = $2, updated_at = NOW()
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        market,
    )
    await db.execute(
        """
        UPDATE public.candidates
        SET market = $2, updated_at = NOW()
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        market,
    )

    candidate_row = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        user_id,
    )
    if candidate_row:
        from hireloop_api.services.background_jobs import MATCH_EMBED_CANDIDATE, enqueue_job

        await enqueue_job(
            db,
            kind=MATCH_EMBED_CANDIDATE,
            payload={"candidate_id": str(candidate_row["id"])},
            idempotency_key=f"match_embed_market:{candidate_row['id']}:{market}",
        )

    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1::uuid, 'market_update', TRUE)
        """,
        user_id,
    )

    return {"ok": True, "market": market}


@router.post("/market/from-geo")
async def infer_market_from_geo(
    request: Request,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """
    Infer home market from CDN geo headers (Cloudflare / Vercel).
    Only updates when the user is still on the default IN market.
    """
    geo = (
        request.headers.get("cf-ipcountry")
        or request.headers.get("x-vercel-ip-country")
        or request.headers.get("x-country-code")
    )
    inferred = infer_market_from_geo_country(geo)
    if not inferred:
        return {"ok": False, "market": None, "reason": "unsupported_geo"}

    user_id = uuid.UUID(str(current_user["id"]))
    row = await db.fetchrow(
        "SELECT market FROM public.users WHERE id = $1::uuid AND deleted_at IS NULL",
        user_id,
    )
    current = normalize_market(row["market"] if row else None)
    if current not in {None, "", "IN"} and current != inferred:
        return {"ok": True, "market": current, "updated": False}

    await db.execute(
        """
        UPDATE public.users
        SET market = $2, phone_country = $2, updated_at = NOW()
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        inferred,
    )
    await db.execute(
        """
        UPDATE public.candidates
        SET market = $2, updated_at = NOW()
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        inferred,
    )
    return {"ok": True, "market": inferred, "updated": True}


@router.post("/public-profile/publish")
async def publish_public_profile(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Enable the public profile page and ensure a shareable slug exists."""
    user_id = uuid.UUID(str(current_user["id"]))
    candidate = await _ensure_candidate_row(db, user_id)
    user_row = await db.fetchrow(
        "SELECT full_name FROM public.users WHERE id = $1::uuid",
        user_id,
    )
    from hireloop_api.services.public_profile import ensure_public_slug

    hide_contact = bool(candidate.get("hide_contact_public"))
    slug = await ensure_public_slug(
        db,
        candidate["id"],
        display_name=user_row["full_name"] if user_row else None,
        hide_contact=hide_contact,
    )
    await db.execute(
        """
        UPDATE public.candidates
        SET public_profile_enabled = TRUE, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        candidate["id"],
    )
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1::uuid, 'public_profile_publish', TRUE)
        """,
        user_id,
    )
    return {"ok": True, "slug": slug, "public_profile_url": f"/p/{slug}"}


@router.get("/profile")
async def get_my_profile(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = uuid.UUID(str(current_user["id"]))

    user_row = await db.fetchrow(
        """
        SELECT id, email, phone, full_name, role, phone_verified, avatar_url, market, phone_country
        FROM public.users
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    candidate_row = await db.fetchrow(
        """
        SELECT id, market, headline, summary, current_title, current_company,
               years_experience, location_city, location_state, skills,
               profile_complete, onboarding_complete, visibility, looking_for, remote_preference,
               open_to_relocation, location_scope, expected_ctc_min, expected_ctc_max,
               current_ctc, notice_period_days,
               display_currency, public_slug, public_profile_enabled,
               hide_contact_public, share_with_recruiters, tailored_resume_enabled,
               is_active, linkedin_url, linkedin_data, career_profile, career_analysis
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        user_id,
    )
    if candidate_row is None:
        if user_row["role"] == "recruiter":
            user_payload = _serialize_row(user_row) or {}
            _allow = {e.lower() for e in (getattr(settings, "super_admin_emails", []) or []) if e}
            user_payload["is_admin"] = (
                user_payload.get("role") == "admin"
                or str(user_payload.get("email") or "").lower() in _allow
            )
            return {
                "user": user_payload,
                "candidate": None,
                "experience": [],
                "education": [],
                "resume_filename": None,
            }
        candidate_row = await _ensure_candidate_row(
            db,
            user_id,
            headline="New candidate",
        )

    user_payload = _serialize_row(user_row) or {}
    candidate_payload = _serialize_row(candidate_row) or {}

    from hireloop_api.services.onboarding_grandfather import (
        maybe_grandfather_onboarding_complete,
    )

    if await maybe_grandfather_onboarding_complete(db, candidate=candidate_row):
        candidate_payload["onboarding_complete"] = True

    # Admin status mirrors deps.get_admin_user: DB role OR the operator allow-list
    # (so a founder bootstrapped via SUPER_ADMIN_EMAILS — whose DB role is still
    # 'candidate' — still sees the Admin entry point). Never user-editable.
    _allow = {e.lower() for e in (getattr(settings, "super_admin_emails", []) or []) if e}
    user_payload["is_admin"] = (
        user_payload.get("role") == "admin"
        or str(user_payload.get("email") or "").lower() in _allow
    )

    linkedin_name = extract_linkedin_display_name(candidate_row.get("linkedin_data"))

    try:
        healed = await heal_candidate_headline_from_linkedin(
            db,
            user_id=user_id,
            linkedin_data=candidate_row.get("linkedin_data"),
            user_full_name=user_payload.get("full_name"),
        )
        if healed:
            candidate_payload["headline"] = healed
    except Exception as exc:
        logger.warning("linkedin_headline_heal_failed", user_id=str(user_id), error=str(exc))

    # ── Work experience + education from the primary (latest) resume ──────────
    experience: list[dict[str, Any]] = []
    education: list[dict[str, Any]] = []
    resume_education: list[dict[str, Any]] = []
    candidate_id = candidate_row.get("id")
    resume_filename: str | None = None
    resume_full_name: str | None = None
    if candidate_id is not None:
        resume_row = await db.fetchrow(
            """
            SELECT parsed_data, file_name
            FROM public.resumes
            WHERE candidate_id = $1
            ORDER BY is_primary DESC, version DESC, created_at DESC
            LIMIT 1
            """,
            candidate_id,
        )
        parsed = resume_row["parsed_data"] if resume_row else None
        resume_filename = resume_row.get("file_name") if resume_row else None
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (ValueError, TypeError):
                parsed = None
        if isinstance(parsed, dict):
            raw_resume_name = parsed.get("full_name")
            if isinstance(raw_resume_name, str) and raw_resume_name.strip():
                resume_full_name = raw_resume_name.strip()
            raw_exp = parsed.get("work_experience")
            if isinstance(raw_exp, list):
                experience = [e for e in raw_exp if isinstance(e, dict)]
            raw_edu = parsed.get("education")
            if isinstance(raw_edu, list):
                resume_education = [e for e in raw_edu if isinstance(e, dict)]

        career_intel = None
        try:
            from hireloop_api.services.career_intelligence import CareerIntelligenceService

            career_intel = await CareerIntelligenceService.get(db, str(candidate_id))
        except Exception:
            career_intel = None

        cp_raw = candidate_row.get("career_profile")
        career_profile = cp_raw if isinstance(cp_raw, dict) else None
        if isinstance(cp_raw, str):
            try:
                career_profile = json.loads(cp_raw)
            except (ValueError, TypeError):
                career_profile = None

        experience = build_merged_experience(
            resume_experience=experience,
            linkedin_data=candidate_row.get("linkedin_data"),
            career_profile=career_profile if isinstance(career_profile, dict) else None,
            career_intelligence=career_intel,
            candidate=candidate_payload,
            skills=list(candidate_payload.get("skills") or []),
        )

        reconciled, overview_fixes = reconcile_candidate_overview(
            candidate_payload,
            experience,
            linkedin_data=candidate_row.get("linkedin_data"),
        )
        candidate_payload.update(
            {
                k: reconciled[k]
                for k in (
                    "headline",
                    "summary",
                    "current_title",
                    "current_company",
                    "looking_for",
                    "years_experience",
                )
                if k in reconciled
            }
        )
        if overview_fixes and candidate_id is not None:
            set_parts = [f"{col} = ${i + 2}" for i, col in enumerate(overview_fixes)]
            await db.execute(
                f"""
                UPDATE public.candidates
                SET {", ".join(set_parts)}, updated_at = NOW()
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                candidate_id,
                *overview_fixes.values(),
            )
            from hireloop_api.services.background_jobs import (
                CAREER_INTELLIGENCE_UPDATE,
                enqueue_job,
            )

            await enqueue_job(
                db,
                kind=CAREER_INTELLIGENCE_UPDATE,
                payload={
                    "candidate_id": str(candidate_id),
                    "only_if_missing": False,
                },
                idempotency_key=f"career_intel_refresh:{candidate_id}:{len(overview_fixes)}",
            )

        # Education merges the same three persisted sources as experience so it
        # surfaces from CV, LinkedIn, OR resume — whichever the candidate gave.
        education = build_merged_education(
            resume_education=resume_education,
            linkedin_data=candidate_row.get("linkedin_data"),
            career_profile=career_profile if isinstance(career_profile, dict) else None,
        )

        if career_intel is None:
            from hireloop_api.services.background_jobs import (
                CAREER_INTELLIGENCE_UPDATE,
                enqueue_job,
            )

            await enqueue_job(
                db,
                kind=CAREER_INTELLIGENCE_UPDATE,
                payload={
                    "candidate_id": str(candidate_id),
                    "only_if_missing": True,
                },
                idempotency_key=f"career_intel:{candidate_id}",
            )

    display_name = pick_display_name(
        user_full_name=user_payload.get("full_name"),
        email=user_payload.get("email"),
        resume_full_name=resume_full_name,
        linkedin_full_name=linkedin_name,
    )
    if display_name:
        user_payload["full_name"] = display_name
        stored_name = sanitize_display_name(user_row.get("full_name"))
        if stored_name != display_name:
            await db.execute(
                """
                UPDATE public.users
                SET full_name = $2, updated_at = NOW()
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                user_id,
                display_name,
            )

    from hireloop_api.services.display_currency import currency_fields_for_candidate

    candidate_payload.update(currency_fields_for_candidate(candidate_payload))
    from hireloop_api.services.public_profile import bootstrap_candidate_public_profile

    slug = await bootstrap_candidate_public_profile(
        db,
        candidate_row["id"],
        user_id=user_id,
        display_name=user_payload.get("full_name"),
    )
    if not slug:
        slug = candidate_payload.get("public_slug")
    if candidate_payload.get("public_profile_enabled") and slug:
        candidate_payload["public_profile_url"] = f"/p/{slug}"
    else:
        candidate_payload["public_profile_url"] = None

    return {
        "user": user_payload,
        "candidate": candidate_payload,
        "experience": experience,
        "education": education,
        "resume_filename": resume_filename,
    }


class LinkedInUrlRequest(BaseModel):
    linkedin_url: str


@router.post("/linkedin")
async def set_linkedin_url(
    body: LinkedInUrlRequest,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Save / confirm the candidate's LinkedIn URL and (re)run Apify/LinkDAPI enrichment
    so the dashboard pre-fills. Fallback when OAuth didn't return a vanity URL.
    """
    from hireloop_api.services.background_jobs import LINKDAPI_ENRICH, enqueue_job
    from hireloop_api.services.linkdapi_profile import extract_linkedin_username

    # Each save kicks off an Apify/LinkDAPI scrape (external cost) — cap it.
    check_rate_limit(str(current_user["id"]), "linkedin_enrich", max_per_hour=5)

    url = (body.linkedin_url or "").strip()
    if not extract_linkedin_username(url):
        raise HTTPException(400, "Enter a valid LinkedIn profile URL (linkedin.com/in/…).")

    user_id = uuid.UUID(str(current_user["id"]))
    await _ensure_candidate_row(db, user_id)
    await db.execute(
        """
        UPDATE public.candidates
        SET linkedin_url = $2, updated_at = NOW()
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        url,
    )

    scheduled = bool(settings.apify_token or settings.linkdapi_key)
    if scheduled:
        await enqueue_job(
            db,
            kind=LINKDAPI_ENRICH,
            payload={"user_id": str(user_id), "linkedin_url": url},
            idempotency_key=f"linkdapi:{user_id}",
        )
    return {"ok": True, "linkedin_url": url, "enrichment_scheduled": scheduled}


@router.patch("/profile")
async def update_my_profile(
    body: ProfileUpdateRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection | None = Depends(get_db_optional),
    settings: Settings = Depends(get_settings),
) -> dict:
    user_id = uuid.UUID(str(current_user["id"]))
    updates = body.model_dump(exclude_unset=True)

    async def _rest_fallback(reason: str) -> dict:
        from hireloop_api.services import supabase_users as rest_users

        logger.warning("profile_update_via_rest", user_id=str(user_id), reason=reason)
        if "full_name" in updates:
            await rest_users.patch_user(
                settings,
                user_id,
                {
                    "full_name": updates["full_name"].strip()
                    if isinstance(updates["full_name"], str) and updates["full_name"].strip()
                    else None
                },
            )
        candidate_fields = {
            k: updates[k]
            for k in (
                "headline",
                "summary",
                "current_title",
                "current_company",
                "years_experience",
                "location_city",
                "location_state",
                "looking_for",
                "open_to_relocation",
                "expected_ctc_min",
                "expected_ctc_max",
                "current_ctc",
                "notice_period_days",
                "visibility",
            )
            if k in updates
        }
        if "skills" in updates:
            candidate_fields["skills"] = updates["skills"] or []
        if "remote_preference" in updates:
            pref = normalize_remote_preference(updates["remote_preference"])
            if pref not in VALID_REMOTE_PREFERENCES:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Invalid remote_preference. "
                        f"Expected one of: {', '.join(sorted(VALID_REMOTE_PREFERENCES))}."
                    ),
                )
            candidate_fields["remote_preference"] = pref
        if "location_scope" in updates:
            scope = str(updates["location_scope"]).lower().strip()
            if scope not in {"city", "state", "country", "global"}:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Invalid location_scope. Expected one of: city, state, country, global."
                    ),
                )
            candidate_fields["location_scope"] = scope
            candidate_fields["open_to_relocation"] = scope in {"country", "global"}
        if candidate_fields:
            candidate = await rest_users.ensure_candidate(settings, user_id)
            await rest_users.patch_candidate(settings, candidate["id"], candidate_fields)
        try:
            await rest_users.log_consent_rest(
                settings, user_id=user_id, purpose="profile_update_manual", granted=True
            )
        except Exception as exc:
            logger.error("consent_log_rest_failed", user_id=str(user_id), error=str(exc))
        return {"ok": True}

    if db is None:
        return await _rest_fallback("db_pool_unavailable")

    try:
        if "full_name" in updates:
            raw_name = updates.pop("full_name")
            await db.execute(
                """
                UPDATE public.users
                SET full_name = $2, updated_at = NOW()
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                user_id,
                raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None,
            )

        if updates:
            candidate = await _ensure_candidate_row(db, user_id)
            set_clauses: list[str] = []
            values: list[Any] = [candidate["id"]]
            param_idx = 2

            column_map = {
                "headline": "headline",
                "summary": "summary",
                "current_title": "current_title",
                "current_company": "current_company",
                "years_experience": "years_experience",
                "location_city": "location_city",
                "location_state": "location_state",
                "looking_for": "looking_for",
                "open_to_relocation": "open_to_relocation",
                "expected_ctc_min": "expected_ctc_min",
                "expected_ctc_max": "expected_ctc_max",
                "current_ctc": "current_ctc",
                "notice_period_days": "notice_period_days",
                "display_currency": "display_currency",
                "public_profile_enabled": "public_profile_enabled",
                "hide_contact_public": "hide_contact_public",
                "share_with_recruiters": "share_with_recruiters",
                "tailored_resume_enabled": "tailored_resume_enabled",
            }
            if "display_currency" in updates:
                from hireloop_api.services.display_currency import VALID_DISPLAY_CURRENCIES

                cur = str(updates["display_currency"] or "auto").lower().strip()
                if cur not in {c.lower() for c in VALID_DISPLAY_CURRENCIES}:
                    raise HTTPException(
                        status_code=422,
                        detail="Invalid display_currency. Use auto, INR, USD, GBP, or EUR.",
                    )
                updates["display_currency"] = cur
            if "remote_preference" in updates:
                pref = normalize_remote_preference(updates["remote_preference"])
                if pref not in VALID_REMOTE_PREFERENCES:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Invalid remote_preference. "
                            f"Expected one of: {', '.join(sorted(VALID_REMOTE_PREFERENCES))}."
                        ),
                    )
                set_clauses.append(f"remote_preference = ${param_idx}")
                values.append(pref)
                param_idx += 1
                updates.pop("remote_preference", None)

            if "location_scope" in updates:
                scope = str(updates["location_scope"]).lower().strip()
                if scope not in {"city", "state", "country", "global"}:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "Invalid location_scope. Expected one of: city, state, country, global."
                        ),
                    )
                set_clauses.append(f"location_scope = ${param_idx}")
                values.append(scope)
                param_idx += 1
                set_clauses.append(f"open_to_relocation = ${param_idx}")
                values.append(scope in {"country", "global"})
                param_idx += 1
                updates.pop("location_scope", None)

            for field, column in column_map.items():
                if field not in updates:
                    continue
                set_clauses.append(f"{column} = ${param_idx}")
                values.append(updates[field])
                param_idx += 1

            if "skills" in updates:
                set_clauses.append(f"skills = ${param_idx}::text[]")
                values.append(updates["skills"] or [])
                param_idx += 1

            if "visibility" in updates:
                vis = updates["visibility"]
                if vis not in _VISIBILITY_VALUES:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Invalid visibility '{vis}'. "
                        f"Expected one of: {', '.join(sorted(_VISIBILITY_VALUES))}.",
                    )
                set_clauses.append(f"visibility = ${param_idx}::candidate_visibility")
                values.append(vis)
                param_idx += 1

            if set_clauses:
                set_clauses.append("updated_at = NOW()")
                if "current_title" in updates or "years_experience" in updates:
                    set_clauses.append(
                        """
                        profile_complete = CASE
                          WHEN COALESCE(current_title, '') <> ''
                           AND COALESCE(years_experience, 0) > 0
                          THEN TRUE
                          ELSE profile_complete
                        END
                        """.strip()
                    )
                query = (
                    f"UPDATE public.candidates SET {', '.join(set_clauses)} "
                    "WHERE id = $1::uuid AND deleted_at IS NULL"
                )
                await db.execute(query, *values)

            if "hide_contact_public" in updates or updates.get("public_profile_enabled"):
                from hireloop_api.services.public_profile import sync_public_slug_privacy

                name_row = await db.fetchrow(
                    "SELECT full_name FROM public.users WHERE id = $1::uuid",
                    user_id,
                )
                hide_row = await db.fetchval(
                    "SELECT hide_contact_public FROM public.candidates WHERE id = $1::uuid",
                    candidate["id"],
                )
                await sync_public_slug_privacy(
                    db,
                    candidate["id"],
                    hide_contact=bool(hide_row),
                    display_name=name_row["full_name"] if name_row else None,
                )

        await db.execute(
            """
            INSERT INTO public.consent_log (user_id, purpose, granted)
            VALUES ($1::uuid, 'profile_update_manual', TRUE)
            """,
            user_id,
        )

        candidate_row = await db.fetchrow(
            "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
            user_id,
        )
        if candidate_row:
            from hireloop_api.services.background_jobs import (
                MATCH_EMBED_CANDIDATE,
                PROFILE_COMPLETENESS,
                enqueue_job,
            )

            await enqueue_job(
                db,
                kind=PROFILE_COMPLETENESS,
                payload={"candidate_id": str(candidate_row["id"])},
                idempotency_key=f"profile_completeness:{candidate_row['id']}",
            )

            preference_fields = {
                "remote_preference",
                "location_scope",
                "location_city",
                "location_state",
                "open_to_relocation",
                "expected_ctc_min",
                "expected_ctc_max",
                "current_title",
                "current_company",
                "years_experience",
                "skills",
                "looking_for",
            }
            if preference_fields & set(body.model_dump(exclude_unset=True).keys()):
                await enqueue_job(
                    db,
                    kind=MATCH_EMBED_CANDIDATE,
                    payload={"candidate_id": str(candidate_row["id"])},
                    idempotency_key=f"match_embed:{candidate_row['id']}",
                )

        return {"ok": True}
    except Exception as exc:
        err = str(exc)
        if "ECIRCUITBREAKER" in err or "authentication failed" in err.lower():
            return await _rest_fallback(err[:120])
        raise


def _pipeline_stage(
    *,
    saved_at: object | None,
    kit_id: object | None,
    application_status: str | None,
    intro_status: str | None,
) -> str:
    if intro_status == "accepted":
        return "intro_accepted"
    if intro_status in (
        "pending",
        "invited",
        "recruiter_notified",
        "enriching",
        "drafting",
        "draft_ready",
        "sent",
        "opened",
        "replied",
    ):
        return "intro_in_progress"
    if application_status in (
        "applied",
        "screening",
        "interview",
        "offer",
        "hired",
        "rejected",
        "withdrawn",
    ):
        return application_status
    if kit_id:
        return "kit_ready"
    if saved_at:
        return "saved"
    return "tracked"


@router.get("/job-pipeline")
async def get_job_pipeline(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Unified job tracker — saved, kits, applications, and intros."""
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(current_user["id"])),
    )
    if not candidate:
        return {"items": []}

    cid = candidate["id"]
    market = await fetch_candidate_market(db, cid)
    vis = job_visible_for_market_sql(market_param="$2")

    rows = await db.fetch(
        f"""
        WITH my_jobs AS (
            SELECT job_id FROM public.saved_jobs WHERE candidate_id = $1::uuid
            UNION
            SELECT job_id FROM public.job_application_kits WHERE candidate_id = $1::uuid
            UNION
            SELECT job_id FROM public.job_applications WHERE candidate_id = $1::uuid
            UNION
            SELECT job_id FROM public.intro_requests WHERE candidate_id = $1::uuid
        )
        SELECT
            j.id AS job_id,
            j.title,
            co.name AS company_name,
            j.location_city,
            j.location_state,
            j.is_remote,
            j.apply_url,
            sj.saved_at,
            k.id AS kit_id,
            k.updated_at AS kit_updated_at,
            k.tailored_resume_id,
            k.mock_interview_id,
            ja.status AS application_status,
            ja.applied_at,
            ir.id AS intro_id,
            ir.status AS intro_status,
            ir.direction AS intro_direction,
            GREATEST(
                sj.saved_at,
                k.updated_at,
                ja.applied_at,
                ir.updated_at
            ) AS last_activity_at
        FROM my_jobs mj
        JOIN public.jobs j ON j.id = mj.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.saved_jobs sj
          ON sj.job_id = j.id AND sj.candidate_id = $1::uuid
        LEFT JOIN public.job_application_kits k
          ON k.job_id = j.id AND k.candidate_id = $1::uuid
        LEFT JOIN LATERAL (
            SELECT status, applied_at
            FROM public.job_applications
            WHERE job_id = j.id AND candidate_id = $1::uuid
            ORDER BY applied_at DESC
            LIMIT 1
        ) ja ON TRUE
        LEFT JOIN LATERAL (
            SELECT id, status, direction, updated_at
            FROM public.intro_requests
            WHERE job_id = j.id AND candidate_id = $1::uuid
            ORDER BY updated_at DESC
            LIMIT 1
        ) ir ON TRUE
        WHERE j.deleted_at IS NULL
          AND {vis}
        ORDER BY last_activity_at DESC NULLS LAST
        """,
        cid,
        market,
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        stage = _pipeline_stage(
            saved_at=d.get("saved_at"),
            kit_id=d.get("kit_id"),
            application_status=d.get("application_status"),
            intro_status=d.get("intro_status"),
        )
        items.append(
            {
                "job_id": str(d["job_id"]),
                "title": d["title"],
                "company_name": d.get("company_name"),
                "location_city": d.get("location_city"),
                "location_state": d.get("location_state"),
                "is_remote": d.get("is_remote"),
                "apply_url": d.get("apply_url"),
                "stage": stage,
                "saved": d.get("saved_at") is not None,
                "saved_at": d["saved_at"].isoformat() if d.get("saved_at") else None,
                "kit_id": str(d["kit_id"]) if d.get("kit_id") else None,
                "kit_updated_at": d["kit_updated_at"].isoformat()
                if d.get("kit_updated_at")
                else None,
                "tailored_resume_id": str(d["tailored_resume_id"])
                if d.get("tailored_resume_id")
                else None,
                "mock_interview_id": str(d["mock_interview_id"])
                if d.get("mock_interview_id")
                else None,
                "application_status": d.get("application_status"),
                "applied_at": d["applied_at"].isoformat() if d.get("applied_at") else None,
                "intro_id": str(d["intro_id"]) if d.get("intro_id") else None,
                "intro_status": d.get("intro_status"),
                "intro_direction": d.get("intro_direction"),
                "last_activity_at": d["last_activity_at"].isoformat()
                if d.get("last_activity_at")
                else None,
            }
        )

    return {"items": items}


@router.get("/saved-jobs")
async def list_saved_jobs(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return jobs the candidate bookmarked, newest first."""
    candidate = await db.fetchrow(
        """
        SELECT c.id, c.current_title, c.current_company, c.looking_for, c.headline, c.summary,
               c.years_experience, c.skills,
               c.location_city, c.location_state, c.expected_ctc_min, c.expected_ctc_max,
               c.remote_preference, c.open_to_relocation, c.location_scope,
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
        uuid.UUID(str(current_user["id"])),
    )
    if not candidate:
        return []

    rows = await db.fetch(
        """
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
            ms.overall_score,
            ms.skills_score,
            ms.experience_score,
            ms.location_score,
            ms.ctc_score,
            ms.explanation,
            ms.computed_at,
            sj.saved_at
        FROM public.saved_jobs sj
        JOIN public.jobs j ON j.id = sj.job_id
        LEFT JOIN public.companies co ON co.id = j.company_id
        LEFT JOIN public.match_scores ms
          ON ms.job_id = j.id AND ms.candidate_id = sj.candidate_id
        WHERE sj.candidate_id = $1::uuid
          AND j.deleted_at IS NULL
        ORDER BY sj.saved_at DESC
        """,
        candidate["id"],
    )
    from hireloop_api.routes.matches import _serialize_fallback_match_row

    cards: list[dict[str, Any]] = []
    candidate_dict = dict(candidate)
    for row in rows:
        row_dict = dict(row)
        if row_dict.get("overall_score") is None:
            computed = _serialize_fallback_match_row(
                row_dict,
                candidate=candidate_dict,
                allow_low_score=True,
            )
            if computed is not None:
                computed["salary_currency"] = row_dict.get("salary_currency")
                cards.append(computed)
                continue
            row_dict["overall_score"] = 0.0
        cards.append(serialize_job_card(row_dict))
    return cards


@router.get("/saved-jobs/ids")
async def list_saved_job_ids(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, list[str]]:
    """Lightweight list of saved job IDs for heart-button state."""
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(current_user["id"])),
    )
    if not candidate:
        return {"job_ids": []}

    rows = await db.fetch(
        "SELECT job_id FROM public.saved_jobs WHERE candidate_id = $1::uuid",
        candidate["id"],
    )
    return {"job_ids": [str(r["job_id"]) for r in rows]}


@router.post("/saved-jobs/{job_id}", status_code=201)
async def save_job_for_later(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, bool]:
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(current_user["id"])),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    market = await fetch_candidate_market(db, candidate["id"])
    vis = job_visible_for_market_sql(market_param="$2")

    job_exists = await db.fetchval(
        f"""
        SELECT EXISTS(
          SELECT 1 FROM public.jobs j
          WHERE j.id = $1::uuid
            AND j.deleted_at IS NULL
            AND (
              {vis}
              OR EXISTS (
                SELECT 1 FROM public.match_scores ms
                WHERE ms.job_id = j.id
                  AND ms.candidate_id = $3::uuid
              )
            )
        )
        """,
        uuid.UUID(job_id),
        market,
        candidate["id"],
    )
    if not job_exists:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.execute(
        """
        INSERT INTO public.saved_jobs (candidate_id, job_id)
        VALUES ($1::uuid, $2::uuid)
        ON CONFLICT (candidate_id, job_id) DO NOTHING
        """,
        candidate["id"],
        uuid.UUID(job_id),
    )
    return {"saved": True}


@router.delete("/saved-jobs/{job_id}", status_code=200)
async def unsave_job(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, bool]:
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(str(current_user["id"])),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate profile not found")

    await db.execute(
        """
        DELETE FROM public.saved_jobs
        WHERE candidate_id = $1::uuid AND job_id = $2::uuid
        """,
        candidate["id"],
        uuid.UUID(job_id),
    )
    return {"saved": False}


@router.post("/jobs/{job_id}/apply", status_code=201)
async def record_job_application(
    job_id: str,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Log a direct application and bookmark the job for the tracker."""
    from hireloop_api.services.job_pipeline import record_direct_application

    result = await record_direct_application(
        db,
        user_id=str(current_user["id"]),
        job_id=job_id,
        settings=settings,
    )
    if "error" in result:
        detail = result["error"]
        status = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail)
    return result


@router.post("/onboarding-consent")
async def record_onboarding_consent(
    body: OnboardingConsentRequest,
    request: Request,
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection | None = Depends(get_db_optional),
) -> dict:
    """
    Record ToS / privacy + marketing consent during onboarding (DPDP R14).
    Also seeds notification prefs for job alerts and optional marketing email.
    """
    if not body.tos_accepted:
        raise HTTPException(status_code=400, detail="Terms and privacy policy must be accepted")

    user_id = uuid.UUID(str(current_user["id"]))
    prefs = default_notification_prefs(marketing_emails=body.marketing_emails)

    async def _rest_consent() -> dict[str, Any]:
        from hireloop_api.services import supabase_users as rest_users

        for purpose in ("terms_of_service", "privacy_policy", "ai_disclaimer"):
            await rest_users.log_consent_rest(
                settings, user_id=user_id, purpose=purpose, granted=True
            )
        await rest_users.log_consent_rest(
            settings,
            user_id=user_id,
            purpose="marketing_emails",
            granted=body.marketing_emails,
        )
        await rest_users.patch_user(settings, user_id, {"notification_prefs": prefs})
        await rest_users.log_consent_rest(
            settings,
            user_id=user_id,
            purpose="notification_prefs_onboarding",
            granted=True,
        )
        candidate = await rest_users.fetch_candidate(settings, user_id)
        enrichment: dict[str, Any] = {}
        if candidate:
            meta = (current_user.get("_supabase_user") or {}).get("user_metadata") or {}
            linkedin_url = meta.get("linkedin_url") or meta.get("profile_url")
            if linkedin_url:
                from hireloop_api.services.linkedin_enrichment import (
                    run_linkedin_profile_enrichment,
                )

                asyncio.create_task(
                    run_linkedin_profile_enrichment(settings, str(user_id), str(linkedin_url))
                )
                enrichment = {
                    "linkedin_enrichment_scheduled": True,
                    "linkedin_url": linkedin_url,
                }
        return {"ok": True, "prefs": prefs, **enrichment}

    if db is None:
        return await _rest_consent()

    try:
        for purpose in ("terms_of_service", "privacy_policy", "ai_disclaimer"):
            await log_consent(
                db,
                user_id=user_id,
                purpose=purpose,
                granted=True,
                request=request,
            )

        await log_consent(
            db,
            user_id=user_id,
            purpose="marketing_emails",
            granted=body.marketing_emails,
            request=request,
        )

        await db.execute(
            """
            UPDATE public.users SET notification_prefs = $2::jsonb, updated_at = NOW()
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            user_id,
            json.dumps(prefs),
        )
        await log_consent(
            db,
            user_id=user_id,
            purpose="notification_prefs_onboarding",
            granted=True,
            request=request,
        )

        candidate = await db.fetchrow(
            "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
            user_id,
        )
        enrichment: dict[str, Any] = {}
        if candidate:
            enrichment = await _schedule_post_consent_enrichment(
                db,
                settings,
                user_id=user_id,
                candidate_id=str(candidate["id"]),
            )
            try:
                from hireloop_api.services.notifications import schedule_weekly_digest

                await schedule_weekly_digest(db, user_id=str(user_id), first_run_days=7)
            except Exception as exc:
                logger.warning("weekly_digest_schedule_failed", error=str(exc)[:200])
            if enrichment.get("linkedin_enrichment_scheduled") and enrichment.get("linkedin_url"):
                from hireloop_api.services.linkedin_enrichment import (
                    run_linkedin_profile_enrichment,
                )

                asyncio.create_task(
                    run_linkedin_profile_enrichment(
                        settings,
                        str(user_id),
                        str(enrichment["linkedin_url"]),
                    )
                )

        return {"ok": True, "prefs": prefs, **enrichment}
    except Exception as exc:
        err = str(exc)
        if "ECIRCUITBREAKER" in err or "authentication failed" in err.lower():
            return await _rest_consent()
        raise


@router.post("/complete-onboarding")
async def complete_onboarding(
    body: CompleteOnboardingRequest,
    request: Request,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Mark candidate onboarding wizard complete (server-side gate)."""
    user_id = uuid.UUID(str(current_user["id"]))
    consent = await db.fetchval(
        """
        SELECT 1 FROM public.consent_log
        WHERE user_id = $1::uuid AND purpose = 'terms_of_service' AND granted = TRUE
        LIMIT 1
        """,
        user_id,
    )
    if not consent:
        raise HTTPException(
            status_code=400,
            detail="Accept terms and privacy policy before finishing onboarding.",
        )

    market = normalize_market(body.market or current_user.get("market"))
    if body.market and market not in SUPPORTED_MARKETS:
        raise HTTPException(status_code=400, detail="Unsupported market")

    await _ensure_candidate_row(db, user_id)

    await db.execute(
        """
        UPDATE public.users
        SET market = $2, updated_at = NOW()
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        market,
    )
    await db.execute(
        """
        UPDATE public.candidates
        SET market = $2, onboarding_complete = TRUE, updated_at = NOW()
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
        market,
    )
    onboarding_done = await db.fetchval(
        """
        SELECT onboarding_complete
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    if not onboarding_done:
        raise HTTPException(
            status_code=500,
            detail="Could not mark onboarding complete. Please try again.",
        )

    purpose = "onboarding_complete_voice_skip" if body.skipped_voice else "onboarding_complete"
    await log_consent(db, user_id=user_id, purpose=purpose, granted=True, request=request)
    if body.skipped_resume:
        await log_consent(
            db,
            user_id=user_id,
            purpose="resume_upload_skipped",
            granted=True,
            request=request,
        )

    candidate_row = await db.fetchrow(
        """
        SELECT id, looking_for, location_city, location_state
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    if candidate_row:
        candidate_id = str(candidate_row["id"])
        looking_for = str(candidate_row["looking_for"] or "").strip()
        if looking_for:
            from hireloop_api.services.career_path import CareerPathService

            try:
                await CareerPathService.prioritize(
                    db,
                    candidate_id,
                    looking_for,
                    [looking_for],
                )
            except Exception as exc:
                logger.warning(
                    "onboarding_prioritize_path_failed",
                    candidate_id=candidate_id,
                    error=str(exc)[:200],
                )

        from hireloop_api.services.background_jobs import (
            AARYA_AUTO_INGEST,
            CAREER_PATH_INGEST,
            MATCH_EMBED_CANDIDATE,
            enqueue_job,
        )

        await enqueue_job(
            db,
            kind=MATCH_EMBED_CANDIDATE,
            payload={"candidate_id": candidate_id},
            idempotency_key=f"onboarding_match:{candidate_id}",
        )
        await enqueue_job(
            db,
            kind=AARYA_AUTO_INGEST,
            payload={"candidate_id": candidate_id},
            idempotency_key=f"onboarding_ingest:{candidate_id}",
        )
        if looking_for:
            await enqueue_job(
                db,
                kind=CAREER_PATH_INGEST,
                payload={
                    "candidate_id": candidate_id,
                    "derive_from_candidate": True,
                },
                idempotency_key=f"onboarding_path_ingest:{candidate_id}",
            )

    return {"ok": True, "onboarding_complete": True, "market": market}


@router.get("/notification-prefs")
async def get_notification_prefs(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await db.fetchrow(
        "SELECT notification_prefs FROM public.users WHERE id = $1",
        current_user["id"],
    )
    return {"prefs": row["notification_prefs"] if row else {}}


class ExcludePreferenceRequest(BaseModel):
    kind: Literal["companies", "titles"]
    value: str
    remove: bool = False


@router.post("/preferences/exclude")
async def set_negative_preference(
    body: ExcludePreferenceRequest,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Add/remove a "not interested" exclusion (#37) — a company or a title keyword.
    Excluded items are hard-filtered from the candidate's match feed. Stored on
    candidates.aarya_state so it lives alongside the rest of Aarya's memory.
    """
    if not body.value.strip():
        raise HTTPException(status_code=400, detail="value is required")
    row = await db.fetchrow(
        "SELECT id, aarya_state FROM public.candidates "
        "WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Complete your profile first")

    new_state = apply_negative_preference(
        row["aarya_state"], kind=body.kind, value=body.value, remove=body.remove
    )
    await db.execute(
        "UPDATE public.candidates SET aarya_state = $1::jsonb, updated_at = NOW() WHERE id = $2",
        json.dumps(new_state),
        row["id"],
    )
    companies, titles = extract_negative_preferences(new_state)
    return {"ok": True, "excluded": {"companies": sorted(companies), "titles": sorted(titles)}}


@router.patch("/notification-prefs")
async def update_notification_prefs(
    body: NotificationPrefsUpdate,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    await db.execute(
        """
        UPDATE public.users SET notification_prefs = $2::jsonb, updated_at = NOW()
        WHERE id = $1
        """,
        current_user["id"],
        json.dumps(body.prefs),
    )
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1::uuid, 'notification_prefs_update', TRUE)
        """,
        current_user["id"],
    )
    return {"ok": True, "prefs": body.prefs}


def _serialize_notification(row: asyncpg.Record) -> dict[str, Any]:
    data = row["data"]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    created = row["created_at"]
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "data": data,
        "is_read": bool(row["is_read"]),
        "created_at": created.isoformat() if created else None,
    }


@router.get("/notifications")
async def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """In-app notification feed for the bell drawer."""
    user_id = uuid.UUID(str(current_user["id"]))
    limit = max(1, min(limit, 100))
    if unread_only:
        rows = await db.fetch(
            """
            SELECT id, type, title, body, data, is_read, created_at
            FROM public.notifications
            WHERE user_id = $1::uuid AND is_read = FALSE
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    else:
        rows = await db.fetch(
            """
            SELECT id, type, title, body, data, is_read, created_at
            FROM public.notifications
            WHERE user_id = $1::uuid
            ORDER BY is_read ASC, created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    unread_count = await db.fetchval(
        """
        SELECT count(*)::int FROM public.notifications
        WHERE user_id = $1::uuid AND is_read = FALSE
        """,
        user_id,
    )
    return {
        "notifications": [_serialize_notification(r) for r in rows],
        "unread_count": int(unread_count or 0),
    }


class NotificationReadUpdate(BaseModel):
    is_read: bool = True


@router.patch("/notifications/{notification_id}")
async def update_notification(
    notification_id: str,
    body: NotificationReadUpdate,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Mark a notification read (dismiss from the drawer)."""
    result = await db.execute(
        """
        UPDATE public.notifications
        SET is_read = $3
        WHERE id = $1::uuid AND user_id = $2::uuid
        """,
        uuid.UUID(notification_id),
        uuid.UUID(str(current_user["id"])),
        body.is_read,
    )
    if result.split()[-1] == "0":
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True, "is_read": body.is_read}


async def _build_export_payload(db: asyncpg.Connection, user_id: str) -> dict[str, Any]:
    user = await db.fetchrow(
        "SELECT * FROM public.users WHERE id = $1",
        uuid.UUID(user_id),
    )
    candidate = await db.fetchrow(
        "SELECT * FROM public.candidates WHERE user_id = $1",
        uuid.UUID(user_id),
    )
    consents = await db.fetch(
        "SELECT * FROM public.consent_log WHERE user_id = $1 ORDER BY created_at",
        uuid.UUID(user_id),
    )
    messages = []
    if candidate:
        messages = await db.fetch(
            """
            SELECT m.role, m.content, m.created_at
            FROM public.messages m
            JOIN public.conversations c ON c.id = m.conversation_id
            WHERE c.candidate_id = $1
            ORDER BY m.created_at
            LIMIT 5000
            """,
            candidate["id"],
        )
    intros = []
    if candidate:
        intros = await db.fetch(
            "SELECT * FROM public.intro_requests WHERE candidate_id = $1",
            candidate["id"],
        )

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": dict(user) if user else None,
        "candidate": dict(candidate) if candidate else None,
        "consent_log": [dict(c) for c in consents],
        "messages_sample": [dict(m) for m in messages],
        "intro_requests": [dict(i) for i in intros],
        "dpdp_contact": "privacy@hireschema.com",
    }


@router.get("/dpdp/export")
async def dpdp_export(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> JSONResponse:
    """Synchronous export for MVP (<60s for typical user)."""
    payload = await _build_export_payload(db, current_user["id"])
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1::uuid, 'data_export', TRUE)
        """,
        current_user["id"],
    )
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": (
                f'attachment; filename="hireloop-export-{current_user["id"]}.json"'
            ),
        },
    )


@router.delete("")
async def dpdp_delete_account(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Soft-delete user + schedule 30-day purge (R14).
    """
    purge_after = datetime.now(UTC) + timedelta(days=30)
    await db.execute(
        """
        UPDATE public.users SET deleted_at = NOW(), updated_at = NOW()
        WHERE id = $1
        """,
        current_user["id"],
    )
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1",
        current_user["id"],
    )
    if candidate:
        await db.execute(
            "UPDATE public.candidates SET deleted_at = NOW() WHERE id = $1",
            candidate["id"],
        )
    await db.execute(
        """
        INSERT INTO public.dpdp_export_jobs (user_id, status, purge_after)
        VALUES ($1::uuid, 'pending', $2)
        """,
        current_user["id"],
        purge_after,
    )
    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1::uuid, 'account_deletion', TRUE)
        """,
        current_user["id"],
    )
    return {
        "ok": True,
        "message": "Account scheduled for deletion. Data purged after 30 days.",
        "purge_after": purge_after.isoformat(),
    }
