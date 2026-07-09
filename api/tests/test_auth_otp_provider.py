import pytest
from fastapi import HTTPException

from hireloop_api.config import Settings
from hireloop_api.routes.auth import SendOTPRequest, _select_otp_provider, send_otp

MSG91_SETTINGS = {
    "msg91_auth_key": "msg91-key",
    "msg91_otp_template_id": "otp-template-id",
}


def make_settings(**overrides: object) -> Settings:
    values = {
        "environment": "development",
        "secret_key": "test-secret-key",
        "service_secret": "test-service-secret",
        "msg91_auth_key": "",
        "msg91_otp_template_id": "",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_development_uses_msg91_for_india_when_configured() -> None:
    settings = make_settings(environment="development", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "IN") == "msg91"


def test_development_uses_local_for_non_india() -> None:
    settings = make_settings(environment="development", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "US") == "local"
    assert _select_otp_provider(settings, "DE") == "local"


def test_development_uses_local_when_no_provider_configured() -> None:
    settings = make_settings(environment="development")
    assert _select_otp_provider(settings) == "local"


def test_production_uses_msg91_for_india_when_configured() -> None:
    settings = make_settings(environment="production", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "IN") == "msg91"


def test_production_unconfigured_for_non_india() -> None:
    settings = make_settings(environment="production", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "US") == "unconfigured"
    assert _select_otp_provider(settings, "GB") == "unconfigured"


@pytest.mark.asyncio
async def test_send_otp_unconfigured_in_production_for_us() -> None:
    settings = make_settings(environment="production", **MSG91_SETTINGS)
    phone = "+14155550100"

    class _FakeDB:
        async def fetchrow(self, query: str, *args: object) -> None:
            return None

    with pytest.raises(HTTPException) as exc:
        await send_otp(
            SendOTPRequest(phone=phone, market="US"),
            request=None,  # type: ignore[arg-type]
            settings=settings,
            current_user={"id": "user-id"},
            db=_FakeDB(),  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 503
    assert "India" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_development_local_otp_for_us(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(environment="development")
    phone = "+14155550100"

    class _FakeDB:
        def __init__(self) -> None:
            self.executed = 0

        async def fetchrow(self, query: str, *args: object) -> None:
            return None

        async def execute(self, query: str, *args: object) -> str:
            self.executed += 1
            return "INSERT 0 1"

    db = _FakeDB()
    response = await send_otp(
        SendOTPRequest(phone=phone, market="US"),
        request=None,  # type: ignore[arg-type]
        settings=settings,
        current_user={"id": "user-id"},
        db=db,  # type: ignore[arg-type]
    )

    assert response.delivery_channel == "local_dev"
    assert response.dev_otp is not None
    assert db.executed >= 1
