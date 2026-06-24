"""Integration: career path prioritize golden path."""

from __future__ import annotations

import json
import uuid

import asyncpg
import pytest
from httpx import AsyncClient

from hireloop_api.services.career_path import CareerPathService


@pytest.mark.asyncio
async def test_prioritize_career_path_via_api(
    api_client: AsyncClient,
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    path_id = uuid.uuid4()
    await db_conn.execute(
        """
        INSERT INTO public.career_paths
          (id, candidate_id, current_role, summary, steps, target_titles,
           target_locations, model)
        VALUES ($1, $2::uuid, 'Engineer', 'Growing', $3::jsonb, $4::text[], $5::text[], 'test')
        """,
        path_id,
        uuid.UUID(candidate_user["candidate_id"]),
        json.dumps(
            [
                {
                    "title": "Staff Engineer",
                    "level": "next",
                    "timeframe": "6-12 months",
                    "rationale": "Natural progression",
                    "skills_to_build": ["system design"],
                }
            ]
        ),
        ["Staff Engineer", "Senior Engineer"],
        ["Bengaluru"],
    )

    res = await api_client.post(
        "/api/v1/career/path/prioritize",
        json={"title": "Staff Engineer"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["path"]["prioritized_title"] == "Staff Engineer"

    path = await CareerPathService.get_latest(db_conn, candidate_user["candidate_id"])
    assert path is not None
    assert path["prioritized_title"] == "Staff Engineer"

    looking_for = await db_conn.fetchval(
        "SELECT looking_for FROM public.candidates WHERE id = $1::uuid",
        uuid.UUID(candidate_user["candidate_id"]),
    )
    assert looking_for == "Staff Engineer"


@pytest.mark.asyncio
async def test_find_jobs_requires_prioritized_path(
    api_client: AsyncClient,
    db_conn: asyncpg.Connection,
    candidate_user: dict[str, str],
) -> None:
    path_id = uuid.uuid4()
    await db_conn.execute(
        """
        INSERT INTO public.career_paths
          (id, candidate_id, current_role, summary, steps, target_titles,
           target_locations, model)
        VALUES ($1, $2::uuid, 'Engineer', 'Growing', '[]'::jsonb, $3::text[], $4::text[], 'test')
        """,
        path_id,
        uuid.UUID(candidate_user["candidate_id"]),
        ["Senior Engineer"],
        ["Bengaluru"],
    )

    res = await api_client.post("/api/v1/career/path/find-jobs")
    assert res.status_code == 400
    assert "prioritize" in res.json()["detail"].lower()
