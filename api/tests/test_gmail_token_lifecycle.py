from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from hireloop_api.services.email.gmail_oauth import GmailOAuthService
from hireloop_api.services.token_crypto import encrypt_token


@pytest.mark.asyncio
async def test_expired_gmail_token_refreshes_with_valid_expiry() -> None:
    db = AsyncMock()
    db.fetchrow.return_value = {
        "access_token": encrypt_token("expired"),
        "refresh_token": encrypt_token("refresh"),
        "token_expiry": datetime(2020, 1, 1, tzinfo=UTC),
    }
    svc = GmailOAuthService("client", "secret", db)
    response = MagicMock()
    response.raise_for_status = lambda: None
    response.json.return_value = {"access_token": "fresh", "expires_in": 3600}
    svc._http.post = AsyncMock(return_value=response)  # type: ignore[method-assign]

    try:
        assert await svc._get_token("00000000-0000-0000-0000-000000000001") == "fresh"
    finally:
        await svc.close()

    args = db.execute.await_args.args
    assert args[2] > datetime.now(UTC)
