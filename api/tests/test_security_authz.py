"""
Security regression tests for authorization & secret handling.

These lock in fixes for two CRITICAL privilege-escalation holes and the
production secret guard:

  * role must NEVER be taken as 'admin' from attacker-controlled signup metadata
    (deps._provision_user_row + the handle_new_user trigger).
  * get_admin_user must NOT grant admin from any user-editable field
    (the old self-asserted LinkedIn-slug path is gone).
  * Settings must refuse to boot in production with default/empty secrets.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from hireloop_api.config import Settings
from hireloop_api.deps import _provision_user_row, get_admin_user

# ── Fake asyncpg connection ───────────────────────────────────────────────────


class _FakeConn:
    """Records queries and echoes back the row an INSERT ... RETURNING would."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.queries.append(" ".join(query.split()))
        if "INSERT INTO public.users" in " ".join(query.split()):
            # args = (id, email, full_name, avatar, role)
            return {
                "id": args[0],
                "email": args[1],
                "phone": None,
                "full_name": args[2],
                "avatar_url": args[3],
                "role": args[4],
                "india_verified": False,
            }
        return None

    async def execute(self, query: str, *args: object) -> str:
        self.queries.append(" ".join(query.split()))
        return "OK"


def _supabase_user(role: str) -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "email": "attacker@example.com",
        "user_metadata": {"role": role, "full_name": "Mallory"},
    }


# ── #1: role escalation via signup metadata ───────────────────────────────────


async def test_provision_never_assigns_admin_from_metadata() -> None:
    conn = _FakeConn()
    row = await _provision_user_row(conn, _supabase_user("admin"))  # type: ignore[arg-type]
    assert row is not None
    assert row["role"] == "candidate"  # 'admin' from metadata is dropped


async def test_provision_allows_self_select_recruiter() -> None:
    conn = _FakeConn()
    row = await _provision_user_row(conn, _supabase_user("recruiter"))  # type: ignore[arg-type]
    assert row is not None
    assert row["role"] == "recruiter"


async def test_provision_defaults_unknown_role_to_candidate() -> None:
    conn = _FakeConn()
    row = await _provision_user_row(conn, _supabase_user("superuser"))  # type: ignore[arg-type]
    assert row is not None
    assert row["role"] == "candidate"


# ── #2: admin must not come from user-editable fields ──────────────────────────


def _dev_settings(**kw: object) -> Settings:
    return Settings(environment="development", **kw)  # type: ignore[arg-type]


async def test_get_admin_denies_non_admin() -> None:
    with pytest.raises(Exception) as exc:  # HTTPException(403)
        await get_admin_user(
            current_user={"id": str(uuid.uuid4()), "role": "candidate", "email": "x@y.com"},
            settings=_dev_settings(super_admin_emails=[]),
        )
    assert "403" in str(exc.value) or "Admin access required" in str(exc.value)


async def test_get_admin_allows_role_admin() -> None:
    user = {"id": str(uuid.uuid4()), "role": "admin", "email": "x@y.com"}
    assert await get_admin_user(current_user=user, settings=_dev_settings()) is user


async def test_get_admin_allows_configured_email_allowlist() -> None:
    user = {"id": str(uuid.uuid4()), "role": "candidate", "email": "Founder@Hireloop.in"}
    out = await get_admin_user(
        current_user=user,
        settings=_dev_settings(super_admin_emails=["founder@hireloop.in"]),
    )
    assert out is user


# ── #3: production secret guard ────────────────────────────────────────────────


def test_production_rejects_default_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="change-me", service_secret="strong-value")


def test_production_rejects_empty_service_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="strong-value", service_secret="")


def test_production_accepts_strong_secrets() -> None:
    cfg = Settings(
        environment="production",
        secret_key="a-strong-random-secret",
        service_secret="another-strong-random-secret",
    )
    assert cfg.is_production
