"""
FastAPI dependency functions.

Shared across all routers:
  - get_settings: app config (cached)
  - get_db: asyncpg connection pool
  - get_current_user: validate Supabase JWT + return user row
"""

import hmac
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

import asyncpg
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hireloop_api.config import Settings, get_settings

logger = structlog.get_logger()

# ── DB connection pool ────────────────────────────────────────────────────────

_pool: asyncpg.Pool | None = None


def reset_db_pool() -> None:
    """Test helper — drop the cached pool so the next request reconnects."""
    global _pool
    _pool = None


async def get_db_pool(settings: Settings) -> asyncpg.Pool:
    """Initialise asyncpg pool on first use."""
    global _pool
    if _pool is None:
        # Convert SQLAlchemy-style URL to plain asyncpg URL
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        pool_kwargs: dict[str, Any] = {
            "min_size": 2,
            "max_size": 10,
            "command_timeout": 30,
        }
        # Supabase transaction pooler (port 6543) requires statement cache off.
        if ":6543/" in dsn or dsn.rstrip("/").endswith(":6543"):
            pool_kwargs["statement_cache_size"] = 0
        _pool = await asyncpg.create_pool(dsn, **pool_kwargs)
    return _pool


async def get_db(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[asyncpg.Connection, None]:
    """Yield a DB connection from the pool."""
    pool = await get_db_pool(settings)
    async with pool.acquire() as conn:
        yield conn


async def get_db_optional(
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[asyncpg.Connection | None, None]:
    """Yield a DB connection, or None when Postgres is unreachable."""
    try:
        pool = await get_db_pool(settings)
    except Exception as exc:
        logger.warning("db_pool_unavailable", error=str(exc)[:200])
        yield None
        return

    conn: asyncpg.Connection | None = None
    try:
        conn = await pool.acquire()
    except Exception as exc:
        logger.warning("db_acquire_unavailable", error=str(exc)[:200])
        yield None
        return

    try:
        yield conn
    finally:
        if conn is not None:
            await pool.release(conn)


# ── Auth ──────────────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def _is_pgproto_uuid(val: object) -> bool:
    cls = type(val)
    return cls.__module__ == "asyncpg.pgproto.pgproto" and cls.__name__ == "UUID"


def coerce_uuid(value: str | uuid.UUID | object) -> uuid.UUID:
    """asyncpg returns pgproto.UUID — stdlib uuid.UUID() cannot parse those directly."""
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def serialize_row(row: asyncpg.Record | None) -> dict[str, Any] | None:
    """JSON-safe dict from an asyncpg row (UUID → str, datetime → ISO)."""
    if row is None:
        return None
    out: dict[str, Any] = {}
    for key, val in dict(row).items():
        if isinstance(val, uuid.UUID) or _is_pgproto_uuid(val):
            out[key] = str(val)
        elif isinstance(val, datetime):
            out[key] = val.isoformat()
        else:
            out[key] = val
    return out


async def _fetch_supabase_user(token: str, settings: Settings) -> dict[str, Any]:
    """Validate the JWT with Supabase and return the Supabase user payload."""
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_service_key,
            },
            timeout=5.0,
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    supabase_user: dict[str, Any] = resp.json()
    user_id = supabase_user.get("id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    return supabase_user


async def get_supabase_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Validated Supabase JWT identity only (no Postgres lookup)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _fetch_supabase_user(credentials.credentials, settings)


async def _load_app_user(
    settings: Settings,
    db: asyncpg.Connection | None,
    supabase_user: dict[str, Any],
) -> dict[str, Any] | None:
    """Load public.users via Postgres, falling back to Supabase REST."""
    user_id = supabase_user["id"]

    if db is not None:
        try:
            user = await db.fetchrow(
                """
                SELECT id, email, phone, full_name, avatar_url, role, india_verified
                FROM public.users
                WHERE id = $1 AND deleted_at IS NULL
                """,
                user_id,
            )
            if user:
                return serialize_row(user)
            provisioned = await _provision_user_row(db, supabase_user)
            if provisioned:
                return provisioned
        except Exception as exc:
            logger.warning("asyncpg_user_lookup_failed", error=str(exc)[:200])

    from hireloop_api.services import supabase_users as rest_users

    row = await rest_users.fetch_user(settings, user_id)
    if not row:
        row = await rest_users.provision_user(settings, supabase_user)
    return row


async def _provision_user_row(
    db: asyncpg.Connection, supabase_user: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Self-heal a missing public.users row from a validated Supabase identity.

    The on_auth_user_created trigger is supposed to provision public.users on
    signup, but it can miss: not installed in an environment, or not yet
    committed when the freshly-signed-up client fires its first authenticated
    request (the onboarding phone step). Rather than dead-ending new users on
    "User not found", we mirror the trigger's logic here and create the row.

    Mirrors supabase/migrations/20240101001200_auth_user_trigger.sql.
    Returns the serialized live row, or None if it exists but is soft-deleted
    (we never resurrect a soft-deleted account).
    """
    user_id = coerce_uuid(supabase_user["id"])
    email = str(supabase_user.get("email") or "")
    meta = supabase_user.get("user_metadata") or {}

    # SECURITY: `user_metadata` (raw_user_meta_data) is attacker-controlled at
    # signup, so only non-privileged self-select roles may come from it. 'admin'
    # is NEVER assignable here — it is granted solely via the audited super-admin
    # endpoint or out-of-band by an operator. Mirrors the handle_new_user()
    # trigger hardened in migration 20240101002300.
    role = meta.get("role") or "candidate"
    if role not in ("candidate", "recruiter"):
        role = "candidate"

    full_name = (
        meta.get("full_name") or meta.get("name") or (email.split("@", 1)[0] if email else "")
    )
    avatar = meta.get("avatar_url") or meta.get("picture") or None

    row = await db.fetchrow(
        """
        INSERT INTO public.users (id, email, full_name, avatar_url, role, india_verified)
        VALUES ($1::uuid, $2, $3, $4, $5, FALSE)
        ON CONFLICT (id) DO NOTHING
        RETURNING id, email, phone, full_name, avatar_url, role, india_verified
        """,
        user_id,
        email,
        full_name,
        avatar,
        role,
    )

    if row is None:
        # Conflict: a row already exists for this id. Re-select the live row —
        # if it's soft-deleted this returns None (we don't auto-resurrect).
        row = await db.fetchrow(
            """
            SELECT id, email, phone, full_name, avatar_url, role, india_verified
            FROM public.users
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            user_id,
        )

    return serialize_row(row)


async def _resolve_user_role(
    db: asyncpg.Connection,
    user_id: uuid.UUID,
    stored_role: str,
) -> str:
    """
    Return the effective app role. Recruiters row wins over a stale users.role
    (bootstrap with the wrong signup tab can mark recruiters as candidate).
    Self-heals public.users.role when we detect a recruiters row.
    """
    if stored_role == "admin":
        return "admin"
    is_recruiter = await db.fetchval(
        """
        SELECT 1 FROM public.recruiters
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        user_id,
    )
    if is_recruiter:
        if stored_role != "recruiter":
            await db.execute(
                """
                UPDATE public.users
                SET role = 'recruiter', updated_at = NOW()
                WHERE id = $1::uuid AND deleted_at IS NULL
                """,
                user_id,
            )
        return "recruiter"
    return stored_role


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection | None = Depends(get_db_optional),
) -> dict[str, Any]:
    """
    Validate the Supabase JWT from the Authorization header.
    Returns the user row from public.users.

    Raises HTTP 401 if token is missing/invalid.
    Phone verification is enforced by get_india_verified_user when configured.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    supabase_user = await _fetch_supabase_user(token, settings)

    row = await _load_app_user(settings, db, supabase_user)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    uid = coerce_uuid(row["id"])
    if db is not None:
        try:
            row["role"] = await _resolve_user_role(db, uid, str(row.get("role") or "candidate"))
        except Exception as exc:
            logger.warning("resolve_user_role_failed", error=str(exc)[:200])
    return row


async def get_current_user_with_supabase(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection | None = Depends(get_db_optional),
) -> dict[str, Any]:
    """
    Like get_current_user, but also returns the raw Supabase user payload under
    the `_supabase_user` key (used for onboarding/profile bootstrap flows).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    supabase_user = await _fetch_supabase_user(token, settings)

    base = await _load_app_user(settings, db, supabase_user)
    if not base:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if db is not None:
        uid = coerce_uuid(base["id"])
        try:
            base["role"] = await _resolve_user_role(db, uid, str(base.get("role") or "candidate"))
        except Exception as exc:
            logger.warning("resolve_user_role_failed", error=str(exc)[:200])
    return {**base, "_supabase_user": supabase_user}


async def get_india_verified_user(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Like get_current_user, with optional +91 phone verification enforcement."""
    if settings.require_phone_verification and not current_user.get("india_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phone verification required. Please verify your +91 number.",
        )
    return current_user


async def get_recruiter_user(
    current_user: dict = Depends(get_india_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Requires recruiter or admin role and an active recruiters row."""
    if current_user.get("role") not in ("recruiter", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recruiter access required",
        )
    recruiter = await db.fetchrow(
        """
        SELECT r.id, r.company_id, r.user_id, r.title, r.nitya_state
        FROM public.recruiters r
        WHERE r.user_id = $1 AND r.deleted_at IS NULL
        """,
        current_user["id"],
    )
    if not recruiter and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Complete recruiter onboarding first",
        )
    return {**current_user, "recruiter": dict(recruiter) if recruiter else None}


async def get_admin_user(
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Admin-only routes (compliance + super-admin panels).

    Access is granted by, in order:
      1. users.role == 'admin' — set ONLY server-side via the audited super-admin
         endpoint (requires an existing admin) or by an operator out-of-band
         (`UPDATE public.users SET role='admin' …` / Supabase app_metadata).
      2. email in Settings.super_admin_emails — an operator-controlled allow-list
         used to bootstrap the first admin.

    SECURITY: admin is NEVER derived from any user-editable field. A previous
    version granted admin when the candidate's self-asserted
    `candidates.linkedin_url` slug matched a configured value — but that column
    is freely writable by the user (PATCH /me/linkedin-url), so anyone could set
    it to a privileged slug and escalate. That path has been removed.

    NOTE: the email allow-list is only as trustworthy as Supabase email
    confirmation — keep "Confirm email" enabled so an attacker can't sign up
    under a configured address without controlling the inbox.
    """
    if current_user.get("role") == "admin":
        return current_user

    emails = [e.lower() for e in (settings.super_admin_emails or []) if e]
    if emails and str(current_user.get("email") or "").lower() in emails:
        return current_user

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


async def get_super_admin_user(
    current_user: dict = Depends(get_admin_user),
) -> dict[str, Any]:
    """
    Super-admin routes.

    Currently identical to get_admin_user (admin role OR configured LinkedIn slug).
    """
    return current_user


async def verify_service_secret(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Validate X-Service-Secret for webhooks (MSG91, etc.), timing-safe."""
    secret = request.headers.get("X-Service-Secret", "")
    expected = settings.service_secret or ""
    # Reject when the server secret is unset/default so an empty or guessed
    # header can never authenticate (defence in depth alongside the prod guard).
    if not secret or not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service secret",
        )
