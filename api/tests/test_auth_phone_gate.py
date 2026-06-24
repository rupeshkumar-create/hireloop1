import pytest
from fastapi import HTTPException

from hireloop_api.config import Settings
from hireloop_api.deps import get_india_verified_user


def make_settings(**overrides: object) -> Settings:
    values = {
        "environment": "development",
        "require_phone_verification": False,
        # Non-default secrets so the production secret guard passes when a test
        # builds Settings(environment="production").
        "secret_key": "test-secret-key",
        "service_secret": "test-service-secret",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_development_allows_unverified_user_when_phone_gate_disabled() -> None:
    user = {"id": "user-id", "india_verified": False}

    result = await get_india_verified_user(
        current_user=user,
        settings=make_settings(environment="development", require_phone_verification=False),
    )

    assert result == user


@pytest.mark.asyncio
async def test_production_blocks_unverified_user_when_phone_gate_enabled() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_india_verified_user(
            current_user={"id": "user-id", "india_verified": False},
            settings=make_settings(environment="production", require_phone_verification=True),
        )

    assert exc.value.status_code == 403
