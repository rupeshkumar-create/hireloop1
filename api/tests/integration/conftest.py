"""
Integration test fixtures — real Postgres schema + HTTP client with auth overrides.

Run after ``scripts/bootstrap_integration_db.py`` (CI does this automatically).
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import (
    get_current_user,
    get_phone_verified_user,
    get_recruiter_user,
    reset_db_pool,
)
from hireloop_api.main import app

API_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = API_ROOT / "scripts" / "bootstrap_integration_db.py"

INTEGRATION_DB_READY = False


def _dsn() -> str:
    raw = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/hireloop_test",
    )
    return raw.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session", autouse=True)
def bootstrap_integration_db() -> None:
    """Apply migrations once per test session (idempotent)."""
    global INTEGRATION_DB_READY
    if os.environ.get("SKIP_INTEGRATION_BOOTSTRAP") == "1":
        return
    env = {**os.environ}
    if not env.get("DATABASE_URL"):
        return
    try:
        import asyncio

        async def _ping() -> None:
            conn = await asyncpg.connect(_dsn())
            await conn.close()

        asyncio.run(_ping())
    except Exception:
        return

    result = subprocess.run(
        [sys.executable, str(BOOTSTRAP)],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return
    INTEGRATION_DB_READY = True


@pytest.fixture(autouse=True)
def _require_integration_db() -> None:
    if not INTEGRATION_DB_READY:
        if os.environ.get("REQUIRE_INTEGRATION_DB") == "1":
            pytest.fail("Integration database required but not bootstrapped")
        pytest.skip("Integration database not bootstrapped")


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        database_url=os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/hireloop_test",
        ),
        background_worker_enabled=False,
        require_phone_verification=False,
        supabase_url="https://placeholder.supabase.co",
        supabase_service_key="placeholder",
        openrouter_api_key="placeholder",
        secret_key="test-secret-key-not-for-production-use",
    )


@pytest_asyncio.fixture
async def db_conn(integration_settings: Settings) -> AsyncIterator[asyncpg.Connection]:
    reset_db_pool()
    conn = await asyncpg.connect(_dsn())
    try:
        yield conn
    finally:
        await conn.close()
        reset_db_pool()


@pytest_asyncio.fixture
async def candidate_user(db_conn: asyncpg.Connection) -> dict[str, str]:
    """Seed auth.users + public.users + candidates for integration flows."""
    user_id = uuid.uuid4()
    email = f"int-{user_id.hex[:8]}@hireloop.test"
    await db_conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user_id,
        email,
    )
    await db_conn.execute(
        """
        INSERT INTO public.users (id, email, full_name, role, phone_verified, market, phone_country)
        VALUES ($1, $2, 'Integration Tester', 'candidate', TRUE, 'IN', 'IN')
        ON CONFLICT (id) DO UPDATE SET phone_verified = TRUE, market = 'IN', phone_country = 'IN'
        """,
        user_id,
        email,
    )
    cand_id = await db_conn.fetchval(
        """
        INSERT INTO public.candidates (user_id, headline, current_title, skills)
        VALUES ($1, 'Integration test', 'Software Engineer', ARRAY['python'])
        ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
        RETURNING id
        """,
        user_id,
    )
    return {
        "user_id": str(user_id),
        "candidate_id": str(cand_id),
        "email": email,
    }


@pytest_asyncio.fixture
async def api_client(
    integration_settings: Settings,
    candidate_user: dict[str, str],
) -> AsyncIterator[AsyncClient]:
    """HTTP client with auth deps overridden to the seeded candidate."""

    async def _user() -> dict[str, object]:
        return {
            "id": candidate_user["user_id"],
            "email": candidate_user["email"],
            "role": "candidate",
            "phone_verified": True,
        }

    app.dependency_overrides[get_settings] = lambda: integration_settings
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_phone_verified_user] = _user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    reset_db_pool()


@pytest_asyncio.fixture
async def recruiter_user(db_conn: asyncpg.Connection) -> dict[str, str]:
    """Seed auth.users + public.users + recruiters for recruiter flows."""
    user_id = uuid.uuid4()
    email = f"rec-{user_id.hex[:8]}@hireloop.test"
    await db_conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user_id,
        email,
    )
    await db_conn.execute(
        """
        INSERT INTO public.users (id, email, full_name, role, phone_verified)
        VALUES ($1, $2, 'Recruiter Tester', 'recruiter', TRUE)
        ON CONFLICT (id) DO UPDATE SET role = 'recruiter', phone_verified = TRUE
        """,
        user_id,
        email,
    )
    company_id = await db_conn.fetchval(
        """
        INSERT INTO public.companies (name, country_code)
        VALUES ('Integration Co', 'IN')
        RETURNING id
        """
    )
    recruiter_id = await db_conn.fetchval(
        """
        INSERT INTO public.recruiters (user_id, company_id, title)
        VALUES ($1, $2, 'Hiring Manager')
        ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
        RETURNING id
        """,
        user_id,
        company_id,
    )
    return {
        "user_id": str(user_id),
        "recruiter_id": str(recruiter_id),
        "company_id": str(company_id),
        "email": email,
    }


@pytest_asyncio.fixture
async def recruiter_api_client(
    integration_settings: Settings,
    recruiter_user: dict[str, str],
    db_conn: asyncpg.Connection,
) -> AsyncIterator[AsyncClient]:
    """HTTP client with recruiter auth deps overridden."""

    recruiter_row = await db_conn.fetchrow(
        "SELECT id, company_id, user_id, title, nitya_state FROM public.recruiters WHERE id = $1",
        uuid.UUID(recruiter_user["recruiter_id"]),
    )

    async def _user() -> dict[str, object]:
        return {
            "id": recruiter_user["user_id"],
            "email": recruiter_user["email"],
            "role": "recruiter",
            "phone_verified": True,
            "recruiter": dict(recruiter_row) if recruiter_row else None,
        }

    app.dependency_overrides[get_settings] = lambda: integration_settings
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_phone_verified_user] = _user
    app.dependency_overrides[get_recruiter_user] = _user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    reset_db_pool()
