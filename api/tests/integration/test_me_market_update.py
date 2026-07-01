import uuid

import asyncpg
from httpx import AsyncClient


async def test_patch_me_market_updates_user_and_candidate(
    api_client: AsyncClient,
    candidate_user: dict[str, str],
    db_conn: asyncpg.Connection,
) -> None:
    res = await api_client.patch("/api/v1/me/market", json={"market": "US"})
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["market"] == "US"

    user_row = await db_conn.fetchrow(
        "SELECT market, phone_country FROM public.users WHERE id = $1::uuid",
        uuid.UUID(candidate_user["user_id"]),
    )
    assert user_row is not None
    assert user_row["market"] == "US"
    assert user_row["phone_country"] == "US"

    cand_row = await db_conn.fetchrow(
        "SELECT market FROM public.candidates WHERE id = $1::uuid",
        uuid.UUID(candidate_user["candidate_id"]),
    )
    assert cand_row is not None
    assert cand_row["market"] == "US"

