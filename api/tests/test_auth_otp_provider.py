import pytest
from pydantic import ValidationError

from hireloop_api.config import Settings
from hireloop_api.routes.auth import SendOTPRequest, _select_otp_provider

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
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_uses_msg91_for_india_when_configured() -> None:
    settings = make_settings(environment="development", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "IN") == "msg91"


def test_non_india_market_normalises_to_india_otp() -> None:
    """India-only product: US/GB codes normalise to IN for provider selection."""
    settings = make_settings(environment="development", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "US") == "msg91"
    assert _select_otp_provider(settings, "DE") == "msg91"


def test_development_uses_local_when_no_provider_configured() -> None:
    settings = make_settings(environment="development")
    assert _select_otp_provider(settings) == "local"


def test_production_uses_msg91_for_india_when_configured() -> None:
    settings = make_settings(environment="production", **MSG91_SETTINGS)
    assert _select_otp_provider(settings, "IN") == "msg91"


def test_production_unconfigured_without_msg91() -> None:
    settings = make_settings(environment="production")
    assert _select_otp_provider(settings, "IN") == "unconfigured"


def test_send_otp_rejects_non_india_phone() -> None:
    with pytest.raises(ValidationError) as exc:
        SendOTPRequest(phone="+14155550100", market="IN")
    assert "Indian" in str(exc.value) or "+91" in str(exc.value)


def test_send_otp_accepts_india_phone() -> None:
    req = SendOTPRequest(phone="+919876543210", market="IN")
    assert req.phone == "+919876543210"
    assert req.market == "IN"
