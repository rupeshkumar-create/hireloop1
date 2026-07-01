"""
Super admin API — internal user management.

Access: users.role = 'admin' OR email in Settings.super_admin_emails
(see deps.get_admin_user).

All mutations are soft-delete / reversible (except DPDP purge after 30 days).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from hireloop_api.deps import get_admin_user, get_db

logger = structlog.get_logger()
router = APIRouter(prefix="/super-admin", tags=["super-admin"])


# ── Models ────────────────────────────────────────────────────────────────────


class UserSummary(BaseModel):
    id: str
    email: str
    full_name: str | None
    phone: str | None
    role: Literal["candidate", "recruiter", "admin"]
    phone_verified: bool
    created_at: str
    deleted_at: str | None

    candidate_id: str | None = None
    candidate_is_active: bool | None = None

    recruiter_id: str | None = None
    recruiter_deleted_at: str | None = None


class UserUpdateRequest(BaseModel):
    role: Literal["candidate", "recruiter", "admin"] | None = None
    phone_verified: bool | None = None
    restore: bool | None = Field(
        default=None,
        description="When true, clears users.deleted_at (does not restore candidate/recruiter).",
    )


class CandidateSummary(BaseModel):
    id: str
    user_id: str
    headline: str | None = None
    current_title: str | None = None
    location_city: str | None = None
    years_experience: int | None = None
    is_active: bool
    deleted_at: str | None = None
    user_email: str
    user_name: str | None = None


class CandidateUpdateRequest(BaseModel):
    is_active: bool


class RecruiterSummary(BaseModel):
    id: str
    user_id: str
    title: str | None = None
    company_id: str | None = None
    deleted_at: str | None = None
    user_email: str
    user_name: str | None = None


class RecruiterUpdateRequest(BaseModel):
    enabled: bool = True


# ── Helpers ──────────────────────────────────────────────────────────────────


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ── Users ────────────────────────────────────────────────────────────────────


@router.get("/users", response_model=list[UserSummary])
async def list_users(
    q: str | None = Query(default=None, description="Search by email or name"),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    where = ["1=1"]
    params: list[object] = []
    idx = 1

    if not include_deleted:
        where.append("u.deleted_at IS NULL")

    if q:
        where.append(f"(u.email ILIKE ${idx} OR u.full_name ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    params.extend([limit, offset])
    # Safe: only constant fragments and $-placeholders are interpolated; all
    # user input (q, limit, offset) is bound as asyncpg parameters via *params.
    query = f"""
      SELECT
        u.id, u.email, u.full_name, u.phone, u.role, u.phone_verified,
        u.created_at, u.deleted_at,
        c.id AS candidate_id, c.is_active AS candidate_is_active,
        r.id AS recruiter_id, r.deleted_at AS recruiter_deleted_at
      FROM public.users u
      LEFT JOIN public.candidates c ON c.user_id = u.id
      LEFT JOIN public.recruiters r ON r.user_id = u.id
      WHERE {" AND ".join(where)}
      ORDER BY u.created_at DESC
      LIMIT ${idx} OFFSET ${idx + 1}
    """

    rows = await db.fetch(query, *params)
    out: list[dict] = []
    for r in rows:
        out.append(
            {
                "id": str(r["id"]),
                "email": r["email"],
                "full_name": r["full_name"],
                "phone": r["phone"],
                "role": r["role"],
                "phone_verified": bool(r["phone_verified"]),
                "created_at": r["created_at"].isoformat(),
                "deleted_at": _iso(r["deleted_at"]),
                "candidate_id": str(r["candidate_id"]) if r["candidate_id"] else None,
                "candidate_is_active": (
                    bool(r["candidate_is_active"]) if r["candidate_id"] else None
                ),
                "recruiter_id": str(r["recruiter_id"]) if r["recruiter_id"] else None,
                "recruiter_deleted_at": _iso(r["recruiter_deleted_at"]),
            }
        )
    return out


@router.patch("/users/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    current_admin: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    # Safety: don't let an admin lock themselves out accidentally
    if str(current_admin.get("id")) == user_id and body.role and body.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    sets: list[str] = []
    params: list[object] = [uid]
    idx = 2
    if body.role is not None:
        sets.append(f"role = ${idx}")
        params.append(body.role)
        idx += 1
    if body.phone_verified is not None:
        sets.append(f"phone_verified = ${idx}")
        params.append(body.phone_verified)
        idx += 1
    if body.restore:
        sets.append("deleted_at = NULL")
    if sets:
        sets.append("updated_at = NOW()")
        # Safe: `sets` holds only constant column assignments with $-placeholders;
        # all values are bound as asyncpg parameters via *params.
        await db.execute(
            f"UPDATE public.users SET {', '.join(sets)} WHERE id = $1",
            *params,
        )

    row = await db.fetchrow(
        """
        SELECT
          u.id, u.email, u.full_name, u.phone, u.role, u.phone_verified,
          u.created_at, u.deleted_at,
          c.id AS candidate_id, c.is_active AS candidate_is_active,
          r.id AS recruiter_id, r.deleted_at AS recruiter_deleted_at
        FROM public.users u
        LEFT JOIN public.candidates c ON c.user_id = u.id
        LEFT JOIN public.recruiters r ON r.user_id = u.id
        WHERE u.id = $1
        """,
        uid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": str(row["id"]),
        "email": row["email"],
        "full_name": row["full_name"],
        "phone": row["phone"],
        "role": row["role"],
        "phone_verified": bool(row["phone_verified"]),
        "created_at": row["created_at"].isoformat(),
        "deleted_at": _iso(row["deleted_at"]),
        "candidate_id": str(row["candidate_id"]) if row["candidate_id"] else None,
        "candidate_is_active": bool(row["candidate_is_active"]) if row["candidate_id"] else None,
        "recruiter_id": str(row["recruiter_id"]) if row["recruiter_id"] else None,
        "recruiter_deleted_at": _iso(row["recruiter_deleted_at"]),
    }


@router.delete("/users/{user_id}", status_code=200)
async def delete_user(
    user_id: str,
    current_admin: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Hard-delete a user (admin forced deletion) — complete erasure.

    A super-admin delete must actually *remove* the account, not just stamp
    `deleted_at`. A soft-delete is the wrong tool here for two reasons:
      1. The Supabase Auth identity (auth.users) keeps a valid login. The
         "deleted" person can still sign in and reach onboarding, then dead-end
         on every authenticated action (the public.users row is filtered out by
         `deleted_at IS NULL`) — e.g. "Couldn't save your number" at the phone
         step. The account is unusable but un-leavable.
      2. The unique email/phone stay claimed, so the same person can never
         re-register and our signup trigger would hit a unique violation.

    We delete the row in `auth.users` instead. Two cascade chains then fan out
    from a single delete (verified against the live schema):
      - auth.users → auth.identities / sessions / mfa_factors / one_time_tokens
        / oauth_* / webauthn_* (all ON DELETE CASCADE), killing the login.
      - auth.users → public.users (FK ON DELETE CASCADE) → candidates,
        recruiters, consent_log, agent_actions, notifications, whatsapp_messages,
        dpdp_export_jobs (all ON DELETE CASCADE), erasing the PII.
    This frees the email/phone for a clean re-signup.

    Note: user-initiated deletion (routes/me.py) keeps the DPDP soft-delete +
    30-day grace model. Admin forced deletion is immediate and irreversible.
    """
    if str(current_admin.get("id")) == user_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete your own account from super-admin",
        )

    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    exists = await db.fetchrow("SELECT id, email FROM public.users WHERE id = $1", uid)
    if not exists:
        raise HTTPException(status_code=404, detail="User not found")

    async with db.transaction():
        # role_versions.created_by references public.users with NO ACTION (not
        # CASCADE), so it would block the cascade. Null it first to preserve the
        # role-version history while detaching the deleted author.
        await db.execute(
            "UPDATE public.role_versions SET created_by = NULL WHERE created_by = $1",
            uid,
        )
        # Single delete; CASCADE removes the auth identity AND all public PII.
        result = await db.execute("DELETE FROM auth.users WHERE id = $1", uid)

    deleted_auth = not result.endswith(" 0")
    if not deleted_auth:
        # No auth.users row (rare: orphaned public.users). Fall back to removing
        # the public row directly so the email/phone are still freed.
        async with db.transaction():
            await db.execute(
                "UPDATE public.role_versions SET created_by = NULL WHERE created_by = $1",
                uid,
            )
            await db.execute("DELETE FROM public.users WHERE id = $1", uid)

    logger.info(
        "super_admin_deleted_user",
        user_id=user_id,
        original_email=exists["email"],
        deleted_auth_identity=deleted_auth,
    )
    return {"ok": True, "erased": True, "deleted_auth_identity": deleted_auth}


# ── Candidates ───────────────────────────────────────────────────────────────


@router.get("/candidates", response_model=list[CandidateSummary])
async def list_candidates(
    q: str | None = Query(default=None, description="Search by email or name"),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    where = ["1=1"]
    params: list[object] = []
    idx = 1

    if not include_deleted:
        where.append("c.deleted_at IS NULL")

    if q:
        where.append(f"(u.email ILIKE ${idx} OR u.full_name ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    params.extend([limit, offset])

    # Safe: only constant fragments and $-placeholders are interpolated; all
    # user input (q, limit, offset) is bound as asyncpg parameters via *params.
    query = f"""
      SELECT
        c.id, c.user_id, c.headline, c.current_title, c.location_city,
        c.years_experience, c.is_active, c.deleted_at,
        u.email AS user_email, u.full_name AS user_name
      FROM public.candidates c
      JOIN public.users u ON u.id = c.user_id
      WHERE {" AND ".join(where)}
      ORDER BY c.created_at DESC
      LIMIT ${idx} OFFSET ${idx + 1}
    """
    rows = await db.fetch(query, *params)
    return [
        {
            "id": str(r["id"]),
            "user_id": str(r["user_id"]),
            "headline": r["headline"],
            "current_title": r["current_title"],
            "location_city": r["location_city"],
            "years_experience": r["years_experience"],
            "is_active": bool(r["is_active"]),
            "deleted_at": _iso(r["deleted_at"]),
            "user_email": r["user_email"],
            "user_name": r["user_name"],
        }
        for r in rows
    ]


@router.patch("/candidates/{candidate_id}", response_model=CandidateSummary)
async def update_candidate(
    candidate_id: str,
    body: CandidateUpdateRequest,
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    try:
        cid = uuid.UUID(candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid candidate id") from exc

    await db.execute(
        """
        UPDATE public.candidates
        SET is_active = $2, updated_at = NOW()
        WHERE id = $1 AND deleted_at IS NULL
        """,
        cid,
        body.is_active,
    )
    row = await db.fetchrow(
        """
        SELECT
          c.id, c.user_id, c.headline, c.current_title, c.location_city,
          c.years_experience, c.is_active, c.deleted_at,
          u.email AS user_email, u.full_name AS user_name
        FROM public.candidates c
        JOIN public.users u ON u.id = c.user_id
        WHERE c.id = $1
        """,
        cid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "headline": row["headline"],
        "current_title": row["current_title"],
        "location_city": row["location_city"],
        "years_experience": row["years_experience"],
        "is_active": bool(row["is_active"]),
        "deleted_at": _iso(row["deleted_at"]),
        "user_email": row["user_email"],
        "user_name": row["user_name"],
    }


# ── Recruiters ───────────────────────────────────────────────────────────────


@router.get("/recruiters", response_model=list[RecruiterSummary])
async def list_recruiters(
    q: str | None = Query(default=None, description="Search by email or name"),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    where = ["1=1"]
    params: list[object] = []
    idx = 1

    if not include_deleted:
        where.append("r.deleted_at IS NULL")

    if q:
        where.append(f"(u.email ILIKE ${idx} OR u.full_name ILIKE ${idx})")
        params.append(f"%{q}%")
        idx += 1

    params.extend([limit, offset])
    # Safe: only constant fragments and $-placeholders are interpolated; all
    # user input (q, limit, offset) is bound as asyncpg parameters via *params.
    query = f"""
      SELECT
        r.id, r.user_id, r.title, r.company_id, r.deleted_at,
        u.email AS user_email, u.full_name AS user_name
      FROM public.recruiters r
      JOIN public.users u ON u.id = r.user_id
      WHERE {" AND ".join(where)}
      ORDER BY r.created_at DESC
      LIMIT ${idx} OFFSET ${idx + 1}
    """
    rows = await db.fetch(query, *params)
    return [
        {
            "id": str(r["id"]),
            "user_id": str(r["user_id"]),
            "title": r["title"],
            "company_id": str(r["company_id"]) if r["company_id"] else None,
            "deleted_at": _iso(r["deleted_at"]),
            "user_email": r["user_email"],
            "user_name": r["user_name"],
        }
        for r in rows
    ]


@router.patch("/recruiters/{recruiter_id}", response_model=RecruiterSummary)
async def update_recruiter(
    recruiter_id: str,
    body: RecruiterUpdateRequest,
    _: dict = Depends(get_admin_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    try:
        rid = uuid.UUID(recruiter_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid recruiter id") from exc

    if body.enabled:
        await db.execute(
            "UPDATE public.recruiters SET deleted_at = NULL, updated_at = NOW() WHERE id = $1",
            rid,
        )
    else:
        await db.execute(
            "UPDATE public.recruiters SET deleted_at = NOW(), updated_at = NOW() WHERE id = $1",
            rid,
        )

    row = await db.fetchrow(
        """
        SELECT
          r.id, r.user_id, r.title, r.company_id, r.deleted_at,
          u.email AS user_email, u.full_name AS user_name
        FROM public.recruiters r
        JOIN public.users u ON u.id = r.user_id
        WHERE r.id = $1
        """,
        rid,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Recruiter not found")
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "title": row["title"],
        "company_id": str(row["company_id"]) if row["company_id"] else None,
        "deleted_at": _iso(row["deleted_at"]),
        "user_email": row["user_email"],
        "user_name": row["user_name"],
    }
