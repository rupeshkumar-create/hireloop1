"""Integration: horizontal access control (IDOR).

Proves candidate A cannot read candidate B's owned resources by id. This is the
single most important B2B-safety test for this app: the backend connects as a
privileged role (RLS bypassed), so app-level ownership filters are the ONLY
access control. If any route drops its `WHERE … user_id = caller` filter, this
test should fail.

Runs in the integration suite (real Postgres). api_client is authed as
candidate A (the `candidate_user` fixture); we seed candidate B directly.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from httpx import AsyncClient


async def _seed_victim_with_resume(db: asyncpg.Connection) -> str:
    """Create a second candidate (B) who owns a tailored resume. Returns its id."""
    user_b = uuid.uuid4()
    email_b = f"idor-b-{user_b.hex[:8]}@hireloop.test"
    await db.execute(
        "INSERT INTO auth.users (id, email) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        user_b,
        email_b,
    )
    await db.execute(
        """
        INSERT INTO public.users (id, email, full_name, role, india_verified)
        VALUES ($1, $2, 'Victim B', 'candidate', TRUE)
        ON CONFLICT (id) DO NOTHING
        """,
        user_b,
        email_b,
    )
    cand_b = await db.fetchval(
        "INSERT INTO public.candidates (user_id, headline) VALUES ($1, 'Victim B') RETURNING id",
        user_b,
    )
    job_id = await db.fetchval(
        "INSERT INTO public.jobs (title) VALUES ('IDOR Test Role') RETURNING id"
    )
    resume_b = await db.fetchval(
        """
        INSERT INTO public.tailored_resumes
          (candidate_id, job_id, template, file_path, status, html_content)
        VALUES ($1::uuid, $2::uuid, 'modern', 'idor/x', 'ready', '<html>B private resume</html>')
        RETURNING id
        """,
        cand_b,
        job_id,
    )
    return str(resume_b)


@pytest.mark.asyncio
async def test_candidate_cannot_read_another_candidates_tailored_resume(
    api_client: AsyncClient,  # authed as candidate A
    db_conn: asyncpg.Connection,
) -> None:
    resume_b = await _seed_victim_with_resume(db_conn)

    # A requests B's resume metadata by id → must be denied (ownership scoping).
    meta = await api_client.get(f"/api/v1/tailored-resumes/tailored/{resume_b}")
    assert meta.status_code == 404, (
        f"IDOR: candidate A read candidate B's resume metadata (got {meta.status_code})"
    )

    # A requests B's resume download (the actual PII payload) → must be denied.
    dl = await api_client.get(f"/api/v1/tailored-resumes/tailored/{resume_b}/download")
    assert dl.status_code == 404, (
        f"IDOR: candidate A downloaded candidate B's resume HTML (got {dl.status_code})"
    )
