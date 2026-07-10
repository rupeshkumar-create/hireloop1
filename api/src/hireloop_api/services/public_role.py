"""Public recruiter role listings — world-readable when published."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from typing import Any

import asyncpg

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _slug_base(title: str | None) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (title or "role").lower()).strip("-")
    return (raw[:40] or "role").strip("-")


def _new_role_slug() -> str:
    return f"r-{secrets.token_hex(4)}"


def public_role_path(slug: str | None) -> str | None:
    if not slug:
        return None
    return f"/r/{slug}"


async def _persist_public_slug(
    db: asyncpg.Connection,
    role_id: uuid.UUID,
    slug: str,
) -> str:
    for _ in range(8):
        try:
            await db.execute(
                """
                UPDATE public.roles
                SET public_slug = $2, updated_at = NOW()
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                role_id,
                slug,
            )
            row = await db.fetchval(
                "SELECT public_slug FROM public.roles WHERE id = $1::uuid",
                role_id,
            )
            if row:
                return str(row)
        except asyncpg.UniqueViolationError:
            slug = _new_role_slug()
    fallback = _new_role_slug()
    await db.execute(
        "UPDATE public.roles SET public_slug = $2 WHERE id = $1::uuid",
        role_id,
        fallback,
    )
    return fallback


async def ensure_public_slug(
    db: asyncpg.Connection,
    role_id: uuid.UUID,
    *,
    title: str | None,
) -> str:
    """Ensure a shareable slug exists for this role."""
    row = await db.fetchrow(
        "SELECT public_slug FROM public.roles WHERE id = $1::uuid AND deleted_at IS NULL",
        role_id,
    )
    if not row:
        raise ValueError("Role not found")
    existing = str(row["public_slug"]) if row["public_slug"] else None
    if existing and _SLUG_RE.fullmatch(existing):
        return existing
    named = f"{_slug_base(title)}-{secrets.token_hex(3)}"
    return await _persist_public_slug(db, role_id, named)


async def enable_public_listing(
    db: asyncpg.Connection,
    *,
    role_id: str,
    recruiter_id: str,
) -> dict[str, Any]:
    """Turn on the public listing and ensure a slug exists."""
    role = await db.fetchrow(
        """
        SELECT id, title, status
        FROM public.roles
        WHERE id = $1::uuid AND recruiter_id = $2::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(str(role_id)),
        uuid.UUID(str(recruiter_id)),
    )
    if not role:
        return {"error": "Role not found for this recruiter"}

    slug = await ensure_public_slug(db, role["id"], title=role["title"])
    await db.execute(
        """
        UPDATE public.roles
        SET public_listing_enabled = TRUE,
            status = CASE WHEN status = 'draft' THEN 'hiring' ELSE status END,
            updated_at = NOW()
        WHERE id = $1::uuid
        """,
        role["id"],
    )
    return {
        "public_slug": slug,
        "public_role_url": public_role_path(slug),
        "public_listing_enabled": True,
    }


def _format_remote_policy(policy: str | None) -> str | None:
    if not policy:
        return None
    labels = {
        "onsite": "On-site",
        "hybrid": "Hybrid",
        "remote": "Remote",
        "flex": "Flexible",
    }
    return labels.get(policy, policy.replace("_", " ").title())


async def fetch_public_role(db: asyncpg.Connection, slug: str) -> dict[str, Any] | None:
    row = await db.fetchrow(
        """
        SELECT r.id, r.title, r.jd_text, r.comp_min, r.comp_max,
               r.location_city, r.location_state, r.remote_policy,
               r.must_haves, r.nice_to_haves, r.candidate_pitch,
               r.hiring_brief, r.status, r.public_slug, r.public_listing_enabled,
               r.updated_at, r.recruiter_id,
               c.name AS company_name, c.logo_url AS company_logo_url,
               (
                 SELECT j.id FROM public.jobs j
                 WHERE j.role_id = r.id AND j.deleted_at IS NULL
                 ORDER BY j.is_active DESC, j.created_at DESC
                 LIMIT 1
               ) AS job_id
        FROM public.roles r
        JOIN public.companies c ON c.id = r.company_id
        WHERE r.public_slug = $1
          AND r.public_listing_enabled = TRUE
          AND r.status = 'hiring'
          AND r.deleted_at IS NULL
        """,
        slug.strip(),
    )
    if not row:
        return None

    must = row.get("must_haves") or []
    nice = row.get("nice_to_haves") or []
    if isinstance(must, str):
        try:
            must = json.loads(must)
        except (ValueError, TypeError):
            must = []
    if isinstance(nice, str):
        try:
            nice = json.loads(nice)
        except (ValueError, TypeError):
            nice = []

    description = row.get("candidate_pitch") or row.get("jd_text") or row.get("hiring_brief")
    location = ", ".join(
        part for part in (row.get("location_city"), row.get("location_state")) if part
    )

    return {
        "role_id": str(row["id"]),
        "job_id": str(row["job_id"]) if row.get("job_id") else None,
        "slug": slug,
        "title": row["title"],
        "company_name": row.get("company_name"),
        "company_logo_url": row.get("company_logo_url"),
        "description": description,
        "comp_min": row.get("comp_min"),
        "comp_max": row.get("comp_max"),
        "location": location or None,
        "remote_policy": _format_remote_policy(row.get("remote_policy")),
        "must_haves": [str(s) for s in must if s][:20],
        "nice_to_haves": [str(s) for s in nice if s][:20],
        "status": row["status"],
        "market": "IN",
        "updated_at": row["updated_at"].isoformat()
        if row.get("updated_at") and hasattr(row["updated_at"], "isoformat")
        else None,
    }
