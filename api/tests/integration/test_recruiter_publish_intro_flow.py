"""Integration: recruiter publish role → background jobs → candidate intro request."""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from httpx import AsyncClient

from hireloop_api.services.intro_service import create_candidate_intro


@pytest.mark.asyncio
async def test_publish_role_enqueues_jobs_and_candidate_intro(
    recruiter_api_client: AsyncClient,
    api_client: AsyncClient,
    db_conn: asyncpg.Connection,
    recruiter_user: dict[str, str],
    candidate_user: dict[str, str],
) -> None:
    create_res = await recruiter_api_client.post(
        "/api/v1/recruiter/roles",
        json={
            "title": "Senior Backend Engineer",
            "jd_text": "Build APIs with Python and Postgres.",
            "location_city": "Bengaluru",
            "location_state": "Karnataka",
            "remote_policy": "hybrid",
            "comp_min_lpa": 20,
            "comp_max_lpa": 35,
        },
    )
    assert create_res.status_code == 201, create_res.text
    role_id = create_res.json()["role_id"]

    publish_res = await recruiter_api_client.post(f"/api/v1/recruiter/roles/{role_id}/publish")
    assert publish_res.status_code == 201, publish_res.text
    publish_body = publish_res.json()
    job_id = publish_body.get("job_id")
    assert job_id
    assert publish_body.get("public_slug")
    assert publish_body.get("public_role_url", "").startswith("/r/")

    job_rows = await db_conn.fetch(
        """
        SELECT kind, status FROM public.background_jobs
        WHERE payload->>'job_id' = $1
        ORDER BY created_at ASC
        """,
        job_id,
    )
    kinds = {row["kind"] for row in job_rows}
    assert "job_embed" in kinds
    assert "job_score" in kinds

    intro = await create_candidate_intro(
        db_conn,
        user_id=candidate_user["user_id"],
        job_id=job_id,
        message="Interested in this role.",
    )
    assert intro.get("intro_id")
    assert intro.get("direction") == "candidate_to_recruiter"

    intro_row = await db_conn.fetchrow(
        """
        SELECT status, recruiter_id, candidate_id, job_id
        FROM public.intro_requests
        WHERE id = $1::uuid
        """,
        uuid.UUID(intro["intro_id"]),
    )
    assert intro_row is not None
    assert intro_row["status"] == "pending"
    assert str(intro_row["recruiter_id"]) == recruiter_user["recruiter_id"]
    assert str(intro_row["candidate_id"]) == candidate_user["candidate_id"]
    assert str(intro_row["job_id"]) == job_id

    list_res = await api_client.get("/api/v1/intros")
    assert list_res.status_code == 200
    intro_ids = {item["id"] for item in list_res.json()}
    assert intro["intro_id"] in intro_ids
