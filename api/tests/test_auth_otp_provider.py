import pytest
from fastapi import HTTPException

from hireloop_api.config import Settings
from hireloop_api.routes import auth
from hireloop_api.routes.auth import SendOTPRequest, _select_otp_provider, send_otp

FAKE_TWILIO_TOKEN = "fake-token"

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
        "twilio_account_sid": "",
        "twilio_auth_token": "",
        "twilio_verify_service_sid": "",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_development_uses_msg91_when_configured() -> None:
    settings = make_settings(environment="development", **MSG91_SETTINGS)

    assert _select_otp_provider(settings) == "msg91"


def test_development_uses_local_when_no_provider_configured() -> None:
    settings = make_settings(environment="development")

    assert _select_otp_provider(settings) == "local"


def test_production_prefers_msg91_over_twilio() -> None:
    settings = make_settings(
        environment="production",
        **MSG91_SETTINGS,
        twilio_account_sid="AC123",
        twilio_auth_token=FAKE_TWILIO_TOKEN,
        twilio_verify_service_sid="VA123",
    )

    assert _select_otp_provider(settings) == "msg91"


def test_production_uses_twilio_when_msg91_missing() -> None:
    settings = make_settings(
        environment="production",
        twilio_account_sid="AC123",
        twilio_auth_token=FAKE_TWILIO_TOKEN,
        twilio_verify_service_sid="VA123",
    )

    assert _select_otp_provider(settings) == "twilio"


@pytest.mark.asyncio
async def test_development_falls_back_to_local_otp_when_twilio_trial_blocks_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(
        environment="development",
        twilio_account_sid="AC123",
        twilio_auth_token=FAKE_TWILIO_TOKEN,
        twilio_verify_service_sid="VA123",
    )
    phone = "+919876543210"

    class _FakeDB:
        def __init__(self) -> None:
            self.executed = 0

        async def fetchrow(self, query: str, *args: object) -> None:
            return None

        async def execute(self, query: str, *args: object) -> str:
            self.executed += 1
            return "INSERT 0 1"

    async def blocked_by_trial_account(_: str, __: Settings) -> None:
        raise HTTPException(
            status_code=503,
            detail=(
                "This number isn't authorised on our SMS trial account. "
                "Use a verified test number, or contact support to enable this number."
            ),
        )

    monkeypatch.setattr(auth, "_send_twilio_verify_otp", blocked_by_trial_account)

    db = _FakeDB()
    response = await send_otp(
        SendOTPRequest(phone=phone),
        request=None,  # type: ignore[arg-type]
        settings=settings,
        current_user={"id": "user-id"},
        db=db,  # type: ignore[arg-type]
    )

    assert response.delivery_channel == "local_dev"
    assert response.dev_otp is not None
    assert db.executed >= 1
