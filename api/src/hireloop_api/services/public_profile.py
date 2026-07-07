"""Public candidate profile — world-readable when published."""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Any

import asyncpg

from hireloop_api.services.display_currency import currency_fields_for_candidate
from hireloop_api.services.display_name import pick_display_name, sanitize_display_name
from hireloop_api.services.profile_experience import (
    build_merged_education,
    build_merged_experience,
    reconcile_candidate_overview,
)
from hireloop_api.services.public_profile_intelligence import (
    build_public_intelligence_snapshot,
    scrub_profile_for_privacy,
)

_ANONYMOUS_SLUG_RE = re.compile(r"^c-[a-f0-9]{8}$")


def _slug_base(name: str | None) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (name or "candidate").lower()).strip("-")
    return (raw[:28] or "candidate").strip("-")


def _new_anonymous_slug() -> str:
    return f"c-{secrets.token_hex(4)}"


def slug_needs_anonymization(slug: str | None, *, hide_contact: bool) -> bool:
    """True when a published slug still embeds identity but contact should stay hidden."""
    if not hide_contact or not slug:
        return False
    return _ANONYMOUS_SLUG_RE.fullmatch(slug.strip()) is None


async def _persist_public_slug(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    slug: str,
) -> str:
    for _ in range(8):
        try:
            await db.execute(
                """
                UPDATE public.candidates
                SET public_slug = $2, updated_at = NOW()
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                candidate_id,
                slug,
            )
            row = await db.fetchval(
                "SELECT public_slug FROM public.candidates WHERE id = $1::uuid",
                candidate_id,
            )
            if row:
                return str(row)
        except asyncpg.UniqueViolationError:
            slug = _new_anonymous_slug()
    fallback = _new_anonymous_slug()
    await db.execute(
        "UPDATE public.candidates SET public_slug = $2 WHERE id = $1::uuid",
        candidate_id,
        fallback,
    )
    return fallback


async def ensure_public_slug(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    *,
    display_name: str | None,
    hide_contact: bool = False,
) -> str:
    """Ensure a shareable slug exists; use opaque slug when contact is hidden."""
    row = await db.fetchrow(
        """
        SELECT public_slug, hide_contact_public
        FROM public.candidates
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        candidate_id,
    )
    hide = hide_contact or bool(row and row["hide_contact_public"])
    existing = str(row["public_slug"]) if row and row["public_slug"] else None

    if existing and not slug_needs_anonymization(existing, hide_contact=hide):
        return existing

    if hide:
        return await _persist_public_slug(db, candidate_id, _new_anonymous_slug())

    if existing:
        return existing

    named = f"{_slug_base(sanitize_display_name(display_name))}-{secrets.token_hex(3)}"
    return await _persist_public_slug(db, candidate_id, named)


async def sync_public_slug_privacy(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    *,
    hide_contact: bool,
    display_name: str | None,
) -> str | None:
    """Rotate slug when privacy mode changes so old name-bearing links stop working."""
    row = await db.fetchrow(
        "SELECT public_slug FROM public.candidates WHERE id = $1::uuid AND deleted_at IS NULL",
        candidate_id,
    )
    if not row:
        return None
    if hide_contact:
        if not row["public_slug"] or slug_needs_anonymization(
            str(row["public_slug"]), hide_contact=True
        ):
            return await ensure_public_slug(
                db,
                candidate_id,
                display_name=display_name,
                hide_contact=True,
            )
        return str(row["public_slug"])
    if not row["public_slug"]:
        return await ensure_public_slug(
            db,
            candidate_id,
            display_name=display_name,
            hide_contact=False,
        )
    return str(row["public_slug"])


async def bootstrap_candidate_public_profile(
    db: asyncpg.Connection,
    candidate_id: uuid.UUID,
    *,
    user_id: uuid.UUID,
    display_name: str | None,
) -> str | None:
    """Ensure a slug exists when public sharing is enabled (default for new candidates)."""
    row = await db.fetchrow(
        """
        SELECT public_profile_enabled, hide_contact_public, public_slug
        FROM public.candidates
        WHERE id = $1::uuid AND deleted_at IS NULL
        """,
        candidate_id,
    )
    if not row or not row.get("public_profile_enabled"):
        return str(row["public_slug"]) if row and row["public_slug"] else None

    hide_contact = bool(row["hide_contact_public"])
    slug = str(row["public_slug"]) if row["public_slug"] else None
    if not slug:
        slug = await ensure_public_slug(
            db,
            candidate_id,
            display_name=display_name,
            hide_contact=hide_contact,
        )
        await db.execute(
            """
            INSERT INTO public.consent_log (user_id, purpose, granted)
            VALUES ($1::uuid, 'public_profile_publish', TRUE)
            """,
            user_id,
        )
    return slug


def _contact_access(
    *,
    hide_contact: bool,
    viewer: dict[str, Any] | None,
    owner_user_id: uuid.UUID,
) -> tuple[bool, bool]:
    """
    Return (may_view_contact, requires_registration).

    Contact is visible only to authenticated Hireschema users (or the profile
    owner). Anonymous visitors must sign up before email, phone, or LinkedIn.
    """
    if hide_contact:
        return False, False
    if viewer is None:
        return False, True
    return True, False


def _redact_public_fields(
    cand: dict[str, Any],
    *,
    hide_contact: bool,
    display_name: str | None,
    viewer: dict[str, Any] | None = None,
    owner_user_id: uuid.UUID,
) -> dict[str, Any]:
    """Strip identifying contact fields from the world-readable payload."""
    may_view, requires_registration = _contact_access(
        hide_contact=hide_contact,
        viewer=viewer,
        owner_user_id=owner_user_id,
    )

    if hide_contact:
        return {
            "display_name": None,
            "avatar_url": None,
            "headline": cand.get("headline"),
            "summary": cand.get("summary"),
            "current_title": cand.get("current_title"),
            "current_company": None,
            "years_experience": cand.get("years_experience"),
            "location_city": None,
            "location_state": None,
            "looking_for": cand.get("looking_for"),
            "linkedin_url": None,
            "contact": {
                "email": None,
                "phone": None,
                "hidden": True,
                "requires_registration": False,
            },
            "privacy_mode": True,
            "viewer_authenticated": viewer is not None,
        }

    if not may_view:
        return {
            "display_name": display_name,
            "avatar_url": None,
            "headline": cand.get("headline"),
            "summary": cand.get("summary"),
            "current_title": cand.get("current_title"),
            "current_company": cand.get("current_company"),
            "years_experience": cand.get("years_experience"),
            "location_city": cand.get("location_city"),
            "location_state": cand.get("location_state"),
            "looking_for": cand.get("looking_for"),
            "linkedin_url": None,
            "contact": {
                "email": None,
                "phone": None,
                "hidden": False,
                "requires_registration": requires_registration,
            },
            "privacy_mode": False,
            "viewer_authenticated": False,
        }

    return {
        "display_name": display_name,
        "avatar_url": cand.get("avatar_url"),
        "headline": cand.get("headline"),
        "summary": cand.get("summary"),
        "current_title": cand.get("current_title"),
        "current_company": cand.get("current_company"),
        "years_experience": cand.get("years_experience"),
        "location_city": cand.get("location_city"),
        "location_state": cand.get("location_state"),
        "looking_for": cand.get("looking_for"),
        "linkedin_url": cand.get("linkedin_url"),
        "contact": {
            "email": cand.get("email"),
            "phone": cand.get("phone"),
            "hidden": False,
            "requires_registration": False,
        },
        "privacy_mode": False,
        "viewer_authenticated": True,
    }


async def _fetch_role_context(
    db: asyncpg.Connection,
    role_slug: str,
) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT r.id, r.title, r.public_slug,
               c.name AS company_name,
               u.full_name AS recruiter_name
        FROM public.roles r
        JOIN public.companies c ON c.id = r.company_id
        JOIN public.recruiters rec ON rec.id = r.recruiter_id AND rec.deleted_at IS NULL
        JOIN public.users u ON u.id = rec.user_id AND u.deleted_at IS NULL
        WHERE r.public_slug = $1
          AND r.public_listing_enabled = TRUE
          AND r.status = 'hiring'
          AND r.deleted_at IS NULL
        """,
        role_slug.strip(),
    )
    if not row:
        return None
    from hireloop_api.services.display_name import pick_display_name

    recruiter_name = pick_display_name(user_full_name=row.get("recruiter_name"))
    return {
        "role_id": str(row["id"]),
        "role_slug": row["public_slug"],
        "title": row["title"],
        "company_name": row.get("company_name"),
        "recruiter_name": recruiter_name,
    }


async def fetch_public_profile(
    db: asyncpg.Connection,
    slug: str,
    *,
    viewer: dict[str, Any] | None = None,
    role_slug: str | None = None,
) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT c.id, c.user_id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, c.market, c.display_currency,
               c.public_profile_enabled, c.hide_contact_public,
               c.linkedin_url, c.career_profile, c.linkedin_data, c.career_intelligence,
               u.full_name, u.email, u.phone, u.avatar_url
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
        WHERE c.public_slug = $1
          AND c.public_profile_enabled = TRUE
          AND c.deleted_at IS NULL
        """,
        slug.strip(),
    )
    if not row:
        return None

    cand = dict(row)
    display_name = pick_display_name(
        user_full_name=cand.get("full_name"),
        email=cand.get("email"),
    )
    hide_contact = bool(cand.get("hide_contact_public"))

    experience = build_merged_experience(
        resume_experience=[],
        linkedin_data=cand.get("linkedin_data"),
        career_profile=cand.get("career_profile")
        if isinstance(cand.get("career_profile"), dict)
        else None,
        career_intelligence=cand.get("career_intelligence")
        if isinstance(cand.get("career_intelligence"), dict)
        else None,
        candidate=cand,
        skills=list(cand.get("skills") or []),
    )
    reconciled, _ = reconcile_candidate_overview(
        cand,
        experience,
        linkedin_data=cand.get("linkedin_data"),
    )

    education = build_merged_education(
        resume_education=[],
        linkedin_data=cand.get("linkedin_data"),
        career_profile=cand.get("career_profile")
        if isinstance(cand.get("career_profile"), dict)
        else None,
    )

    currency = currency_fields_for_candidate(cand)
    owner_user_id = uuid.UUID(str(cand["user_id"]))
    public_fields = _redact_public_fields(
        reconciled,
        hide_contact=hide_contact,
        display_name=display_name,
        viewer=viewer,
        owner_user_id=owner_user_id,
    )
    public_fields, experience = scrub_profile_for_privacy(
        public_fields,
        experience[:8],
        hide_contact=hide_contact,
    )
    intelligence = build_public_intelligence_snapshot(cand.get("career_intelligence"))

    job_context = None
    if role_slug:
        job_context = await _fetch_role_context(db, role_slug)

    payload: dict[str, Any] = {
        "slug": slug,
        "skills": list(cand.get("skills") or []),
        "experience": experience,
        "education": education[:6],
        "intelligence": intelligence,
        "market": cand.get("market"),
        **public_fields,
        **currency,
    }
    if job_context:
        payload["job_context"] = job_context

    if viewer:
        recruiter_row = await db.fetchrow(
            """
            SELECT id FROM public.recruiters
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(str(viewer["id"])),
        )
        if recruiter_row:
            payload["viewer_is_recruiter"] = True
            payload["candidate_id"] = str(cand["id"])

    return payload
