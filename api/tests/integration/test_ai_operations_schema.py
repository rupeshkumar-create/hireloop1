"""Schema contract and PostgreSQL integration tests for durable AI operations."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import asyncpg
import pytest

MIGRATION = Path(__file__).parents[3] / "supabase/migrations/20260722173000_ai_operations.sql"


@pytest.fixture(autouse=True)
def _require_integration_db(
    request: pytest.FixtureRequest,
    bootstrap_integration_db: None,
) -> None:
    """Keep the SQL contract runnable when the optional local database is absent."""
    from conftest import INTEGRATION_DB_READY

    if "db_conn" in request.fixturenames and not INTEGRATION_DB_READY:
        pytest.skip("Integration database not configured")


def _normalized_migration() -> str:
    return re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8")).lower()


def test_ai_operations_migration_contract() -> None:
    """Exercise the migration contract even without a local PostgreSQL service."""
    sql = _normalized_migration()

    required_fragments = {
        "create table public.ai_operations",
        "id uuid primary key default gen_random_uuid()",
        "user_id uuid not null references public.users(id) on delete cascade",
        "candidate_id uuid references public.candidates(id) on delete cascade",
        "recruiter_id uuid references public.recruiters(id) on delete cascade",
        "kind text not null",
        "resource_type text",
        "resource_id uuid",
        "background_job_id uuid references public.background_jobs(id) on delete set null",
        "retry_of uuid references public.ai_operations(id) on delete set null",
        "idempotency_key text not null",
        "progress_percent smallint not null default 0",
        "stage text not null",
        "message text not null",
        "result_type text",
        "result_id uuid",
        "error_code text",
        "error_message text",
        "attempts integer not null default 0",
        "started_at timestamptz",
        "completed_at timestamptz",
        "expires_at timestamptz",
        "created_at timestamptz not null default now()",
        "updated_at timestamptz not null default now()",
        "deleted_at timestamptz",
        "check (candidate_id is null or recruiter_id is null)",
        "check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled'))",
        "check (progress_percent between 0 and 100)",
        "status = 'succeeded' and progress_percent = 100 and completed_at is not null",
        "status in ('failed', 'cancelled') and completed_at is not null",
        "create index idx_ai_operations_owner_status_recency",
        "create index idx_ai_operations_background_job",
        "create index idx_ai_operations_expiry_cleanup",
        "create unique index idx_ai_operations_active_idempotency",
        "where status in ('queued', 'running') and deleted_at is null",
        "for each row execute function public.set_updated_at()",
        "alter table public.ai_operations enable row level security",
        'create policy "ai_operations: read own"',
        "using (auth.uid() = user_id and deleted_at is null)",
        'create policy "ai_operations: admin read all"',
        "role = 'admin'",
    }
    missing = sorted(fragment for fragment in required_fragments if fragment not in sql)
    assert not missing, f"Missing migration contracts: {missing}"

    assert "for insert" not in sql
    assert "for update" not in sql
    assert "for delete" not in sql


@pytest.mark.asyncio
async def test_ai_operations_schema_and_rls(db_conn: asyncpg.Connection) -> None:
    columns = await db_conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_operations'
        """
    )
    assert {row["column_name"] for row in columns} >= {
        "id",
        "user_id",
        "kind",
        "background_job_id",
        "idempotency_key",
        "status",
        "progress_percent",
        "stage",
        "message",
        "error_code",
        "result_type",
        "result_id",
        "expires_at",
        "deleted_at",
    }
    assert (
        await db_conn.fetchval(
            """
            SELECT relrowsecurity
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'ai_operations'
            """
        )
        is True
    )


async def _create_user(
    db_conn: asyncpg.Connection,
    *,
    role: str = "candidate",
) -> uuid.UUID:
    user_id = uuid.uuid4()
    email = f"ai-operation-schema-{user_id.hex[:10]}@hireloop.test"
    await db_conn.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
        user_id,
        email,
    )
    # auth.users trigger may already create public.users — upsert role/market.
    await db_conn.execute(
        """
        INSERT INTO public.users
          (id, email, full_name, role, phone_verified, market, phone_country)
        VALUES ($1, $2, 'AI Operation Schema', $3, TRUE, 'IN', 'IN')
        ON CONFLICT (id) DO UPDATE SET
          email = EXCLUDED.email,
          full_name = EXCLUDED.full_name,
          role = EXCLUDED.role,
          phone_verified = TRUE,
          market = 'IN',
          phone_country = 'IN'
        """,
        user_id,
        email,
        role,
    )
    return user_id


async def _insert_operation(
    db_conn: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    idempotency_key: str,
    status: str = "queued",
    progress_percent: int = 0,
    completed: bool = False,
) -> uuid.UUID:
    return await db_conn.fetchval(
        """
        INSERT INTO public.ai_operations
          (user_id, kind, idempotency_key, status, progress_percent, stage,
           message, completed_at)
        VALUES ($1, 'schema_test', $2, $3, $4, 'queued', 'Test operation',
                CASE WHEN $5 THEN NOW() ELSE NULL END)
        RETURNING id
        """,
        user_id,
        idempotency_key,
        status,
        progress_percent,
        completed,
    )


@pytest.mark.asyncio
async def test_ai_operations_enforces_active_idempotency_and_progress_bounds(
    db_conn: asyncpg.Connection,
) -> None:
    transaction = db_conn.transaction()
    await transaction.start()
    try:
        user_id = await _create_user(db_conn)
        key = f"schema-idempotency-{uuid.uuid4()}"
        await _insert_operation(db_conn, user_id, idempotency_key=key)

        with pytest.raises(asyncpg.UniqueViolationError):
            async with db_conn.transaction():
                await _insert_operation(db_conn, user_id, idempotency_key=key)

        await db_conn.execute(
            """
            UPDATE public.ai_operations
            SET status = 'cancelled', completed_at = NOW()
            WHERE user_id = $1 AND idempotency_key = $2
            """,
            user_id,
            key,
        )
        await _insert_operation(db_conn, user_id, idempotency_key=key)

        for invalid_progress in (-1, 101):
            with pytest.raises(asyncpg.CheckViolationError):
                async with db_conn.transaction():
                    await _insert_operation(
                        db_conn,
                        user_id,
                        idempotency_key=f"{key}-{invalid_progress}",
                        progress_percent=invalid_progress,
                    )
    finally:
        await transaction.rollback()


@pytest.mark.asyncio
async def test_ai_operations_enforces_lifecycle_shapes(
    db_conn: asyncpg.Connection,
) -> None:
    transaction = db_conn.transaction()
    await transaction.start()
    try:
        user_id = await _create_user(db_conn)
        invalid_shapes = (
            ("succeeded", 99, True),
            ("succeeded", 100, False),
            ("failed", 25, False),
            ("cancelled", 0, False),
            ("queued", 0, True),
            ("running", 50, True),
        )
        for status, progress, completed in invalid_shapes:
            with pytest.raises(asyncpg.CheckViolationError):
                async with db_conn.transaction():
                    await _insert_operation(
                        db_conn,
                        user_id,
                        idempotency_key=f"lifecycle-{uuid.uuid4()}",
                        status=status,
                        progress_percent=progress,
                        completed=completed,
                    )

        await _insert_operation(
            db_conn,
            user_id,
            idempotency_key=f"success-{uuid.uuid4()}",
            status="succeeded",
            progress_percent=100,
            completed=True,
        )
    finally:
        await transaction.rollback()


@pytest.mark.asyncio
async def test_ai_operations_has_expected_select_policies_and_indexes(
    db_conn: asyncpg.Connection,
) -> None:
    policies = await db_conn.fetch(
        """
        SELECT policyname, cmd
        FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_operations'
        """
    )
    assert {(row["policyname"], row["cmd"]) for row in policies} == {
        ("ai_operations: read own", "SELECT"),
        ("ai_operations: admin read all", "SELECT"),
    }

    indexes = await db_conn.fetch(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'ai_operations'
        """
    )
    index_names = {row["indexname"] for row in indexes}
    assert index_names >= {
        "idx_ai_operations_owner_status_recency",
        "idx_ai_operations_background_job",
        "idx_ai_operations_expiry_cleanup",
        "idx_ai_operations_active_idempotency",
    }
    active_index = next(
        row["indexdef"]
        for row in indexes
        if row["indexname"] == "idx_ai_operations_active_idempotency"
    )
    assert "UNIQUE" in active_index
    assert "queued" in active_index and "running" in active_index


async def _set_authenticated_identity(
    db_conn: asyncpg.Connection,
    user_id: uuid.UUID,
) -> None:
    await db_conn.execute("RESET ROLE")
    await db_conn.execute("SELECT set_config('request.jwt.claim.sub', $1, TRUE)", str(user_id))
    await db_conn.execute("SELECT set_config('request.jwt.claim.role', 'authenticated', TRUE)")
    await db_conn.execute("SET LOCAL ROLE authenticated")


@pytest.mark.asyncio
async def test_ai_operations_rls_enforces_read_visibility_and_denies_mutations(
    db_conn: asyncpg.Connection,
) -> None:
    transaction = db_conn.transaction()
    await transaction.start()
    try:
        owner_id = await _create_user(db_conn)
        other_candidate_id = await _create_user(db_conn)
        admin_id = await _create_user(db_conn, role="admin")
        visible_operation_id = await _insert_operation(
            db_conn,
            owner_id,
            idempotency_key=f"rls-owner-visible-{uuid.uuid4()}",
        )
        deleted_operation_id = await _insert_operation(
            db_conn,
            owner_id,
            idempotency_key=f"rls-owner-deleted-{uuid.uuid4()}",
        )
        other_operation_id = await _insert_operation(
            db_conn,
            other_candidate_id,
            idempotency_key=f"rls-other-visible-{uuid.uuid4()}",
        )
        await db_conn.execute(
            "UPDATE public.ai_operations SET deleted_at = NOW() WHERE id = $1",
            deleted_operation_id,
        )

        # The plain-Postgres integration prelude does not install Supabase's
        # authenticated table grants. Add them transactionally so RLS, rather
        # than a table-level privilege failure, decides each operation.
        await db_conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON public.ai_operations TO authenticated"
        )
        await db_conn.execute("GRANT SELECT ON public.users TO authenticated")

        await _set_authenticated_identity(db_conn, owner_id)
        owner_visible_ids = {
            row["id"]
            for row in await db_conn.fetch(
                "SELECT id FROM public.ai_operations ORDER BY created_at, id"
            )
        }
        assert owner_visible_ids == {visible_operation_id}

        await _set_authenticated_identity(db_conn, other_candidate_id)
        assert (
            await db_conn.fetchval(
                "SELECT id FROM public.ai_operations WHERE id = $1",
                visible_operation_id,
            )
            is None
        )
        assert (
            await db_conn.fetchval(
                "SELECT id FROM public.ai_operations WHERE id = $1",
                other_operation_id,
            )
            == other_operation_id
        )

        await _set_authenticated_identity(db_conn, admin_id)
        admin_visible_ids = {
            row["id"]
            for row in await db_conn.fetch(
                "SELECT id FROM public.ai_operations ORDER BY created_at, id"
            )
        }
        assert admin_visible_ids == {visible_operation_id, other_operation_id}
        assert deleted_operation_id not in admin_visible_ids

        await _set_authenticated_identity(db_conn, owner_id)
        assert (
            await db_conn.fetchval(
                "SELECT id FROM public.ai_operations WHERE id = $1",
                deleted_operation_id,
            )
            is None
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with db_conn.transaction():
                await db_conn.execute(
                    """
                    INSERT INTO public.ai_operations
                      (user_id, kind, idempotency_key, status, stage, message)
                    VALUES ($1, 'rls_test', $2, 'queued', 'queued', 'Denied insert')
                    """,
                    owner_id,
                    f"rls-denied-insert-{uuid.uuid4()}",
                )
        assert (
            await db_conn.execute(
                "UPDATE public.ai_operations SET message = 'Denied update' WHERE id = $1",
                visible_operation_id,
            )
            == "UPDATE 0"
        )
        assert (
            await db_conn.execute(
                "DELETE FROM public.ai_operations WHERE id = $1",
                visible_operation_id,
            )
            == "DELETE 0"
        )
    finally:
        await transaction.rollback()
