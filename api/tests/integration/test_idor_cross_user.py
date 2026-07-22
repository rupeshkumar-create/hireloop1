"""Integration: horizontal access control (IDOR).

Proves candidate A cannot read candidate B's owned resources by id. This is the
single most important B2B-safety test for this app: the backend connects as a
privileged role (RLS bypassed), so app-level ownership filters are the ONLY
access control. If any route drops its `WHERE … user_id/candidate_id = caller`
filter, these tests should fail.

Runs in the integration suite (real Postgres). api_client is authed as
candidate A (the `candidate_user` fixture); we seed candidate B directly and
confirm A is denied (404) on B's resources.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from httpx import AsyncClient


async def _seed_victim_candidate(db: asyncpg.Connection) -> str:
    """Create a second candidate (B). Returns the candidate id."""
    user_b = uuid.uuid4()
    email_b = f"idor-b-{user_b.hex[:8]}@hireloop.test"
    await db.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user_b,
        email_b,
    )
    await db.execute(
        """
        INSERT INTO public.users (id, email, full_name, role, phone_verified)
        VALUES ($1, $2, 'Victim B', 'candidate', TRUE)
        ON CONFLICT (id) DO NOTHING
        """,
        user_b,
        email_b,
    )
    return str(
        await db.fetchval(
            "INSERT INTO public.candidates (user_id, headline) VALUES ($1, 'Victim B') "
            "RETURNING id",
            user_b,
        )
    )


@pytest.mark.asyncio
async def test_candidate_cannot_read_another_candidates_tailored_resume(
    api_client: AsyncClient,  # authed as candidate A
    db_conn: asyncpg.Connection,
) -> None:
    cand_b = await _seed_victim_candidate(db_conn)
    job_id = await db_conn.fetchval(
        "INSERT INTO public.jobs (title) VALUES ('IDOR Test Role') RETURNING id"
    )
    resume_b = await db_conn.fetchval(
        """
        INSERT INTO public.tailored_resumes
          (candidate_id, job_id, template, file_path, status, html_content)
        VALUES ($1::uuid, $2::uuid, 'modern', 'idor/x', 'ready', '<html>B private</html>')
        RETURNING id
        """,
        cand_b,
        job_id,
    )

    meta = await api_client.get(f"/api/v1/tailored-resumes/tailored/{resume_b}")
    assert meta.status_code == 404, f"IDOR: A read B's resume metadata (got {meta.status_code})"
    dl = await api_client.get(f"/api/v1/tailored-resumes/tailored/{resume_b}/download")
    assert dl.status_code == 404, f"IDOR: A downloaded B's resume HTML (got {dl.status_code})"


@pytest.mark.asyncio
async def test_candidate_cannot_read_another_candidates_mock_interview(
    api_client: AsyncClient,  # authed as candidate A
    db_conn: asyncpg.Connection,
) -> None:
    cand_b = await _seed_victim_candidate(db_conn)
    mock_b = await db_conn.fetchval(
        "INSERT INTO public.mock_interviews (candidate_id) VALUES ($1::uuid) RETURNING id",
        cand_b,
    )

    res = await api_client.get(f"/api/v1/mock-interview/sessions/{mock_b}")
    assert res.status_code == 404, (
        f"IDOR: A read B's mock interview session (got {res.status_code})"
    )


@pytest.mark.asyncio
async def test_candidate_cannot_access_another_users_ai_operations(
    api_client: AsyncClient,
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    """Operation status, mutations, and result references are owner-private."""
    cand_b = await _seed_victim_candidate(db_conn)
    user_b = await db_conn.fetchval(
        "SELECT user_id FROM public.candidates WHERE id = $1::uuid",
        cand_b,
    )
    private_result_id = uuid.uuid4()
    completed_b = await db_conn.fetchval(
        """
        INSERT INTO public.ai_operations
          (user_id, candidate_id, kind, idempotency_key, status,
           progress_percent, stage, message, result_type, result_id, completed_at)
        VALUES
          ($1, $2::uuid, 'application_kit', $3, 'succeeded',
           100, 'ready', 'Your result is ready.', 'application_kit', $4, NOW())
        RETURNING id
        """,
        user_b,
        cand_b,
        f"idor-b-completed:{uuid.uuid4()}",
        private_result_id,
    )

    for action in ("", "/cancel", "/retry"):
        method = api_client.get if not action else api_client.post
        response = await method(f"/api/v1/ai-operations/{completed_b}{action}")
        assert response.status_code == 404
        assert response.json() == {"detail": "AI operation not found"}
        assert str(private_result_id) not in response.text

    active_a = await db_conn.fetchval(
        """
        INSERT INTO public.ai_operations
          (user_id, candidate_id, kind, idempotency_key, status, stage, message)
        VALUES
          ($1::uuid, $2::uuid, 'career_path_generate', $3, 'queued', 'queued', 'Queued.')
        RETURNING id
        """,
        candidate_user["user_id"],
        candidate_user["candidate_id"],
        f"idor-a-active:{uuid.uuid4()}",
    )
    active_b = await db_conn.fetchval(
        """
        INSERT INTO public.ai_operations
          (user_id, candidate_id, kind, idempotency_key, status, stage, message)
        VALUES
          ($1, $2::uuid, 'career_path_generate', $3, 'queued', 'queued', 'Queued.')
        RETURNING id
        """,
        user_b,
        cand_b,
        f"idor-b-active:{uuid.uuid4()}",
    )

    listed = await api_client.get("/api/v1/ai-operations?status=active")
    assert listed.status_code == 200
    listed_ids = {item["id"] for item in listed.json()}
    assert str(active_a) in listed_ids
    assert str(active_b) not in listed_ids
