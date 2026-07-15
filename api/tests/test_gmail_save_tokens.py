from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hireloop_api.services.email.gmail_oauth import GmailOAuthService


@pytest.mark.asyncio
async def test_save_oauth_tokens_preserves_refresh_when_missing() -> None:
    db = AsyncMock()
    svc = GmailOAuthService("client", "secret", db)
    try:
        ok = await svc.save_oauth_tokens(
            candidate_id="00000000-0000-0000-0000-000000000001",
            access_token="access",
            refresh_token="",
            expires_in=3600,
            gmail_email="you@example.com",
            scopes=[],
        )
    finally:
        await svc.close()

    assert ok is True
    sql = db.execute.await_args.args[0]
    assert "COALESCE(NULLIF(EXCLUDED.refresh_token, '')" in sql
    # Empty scopes fall back to gmail.send
    assert db.execute.await_args.args[6] == [
        "https://www.googleapis.com/auth/gmail.send"
    ]
