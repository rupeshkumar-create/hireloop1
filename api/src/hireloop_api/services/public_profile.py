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


def _redact_public_fields(
    cand: dict[str, Any],
    *,
    hide_contact: bool,
    display_name: str | None,
) -> dict[str, Any]:
    """Strip identifying contact fields from the world-readable payload."""
    if not hide_contact:
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
            },
        }

    return {
        "display_name": None,
        "avatar_url": None,
        "headline": cand.get("headline"),
        "summary": cand.get("summary"),
        "current_title": cand.get("current_title"),
        "current_company": cand.get("current_company"),
        "years_experience": cand.get("years_experience"),
        "location_city": None,
        "location_state": None,
        "looking_for": cand.get("looking_for"),
        "linkedin_url": None,
        "contact": {
            "email": None,
            "phone": None,
            "hidden": True,
        },
    }


async def fetch_public_profile(db: asyncpg.Connection, slug: str) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT c.id, c.headline, c.summary, c.current_title, c.current_company,
               c.years_experience, c.location_city, c.location_state, c.skills,
               c.looking_for, c.market, c.display_currency,
               c.public_profile_enabled, c.hide_contact_public,
               c.linkedin_url, c.career_profile, c.linkedin_data,
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
        career_intelligence=None,
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
    public_fields = _redact_public_fields(
        reconciled,
        hide_contact=hide_contact,
        display_name=display_name,
    )

    return {
        "slug": slug,
        "skills": list(cand.get("skills") or []),
        "experience": experience[:8],
        "education": education[:6],
        **public_fields,
        **currency,
    }
