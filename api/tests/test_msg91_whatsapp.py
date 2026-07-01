import pytest

from hireloop_api.config import Settings
from hireloop_api.services.whatsapp.msg91 import (
    Msg91Client,
    normalize_india_mobile,
    resolve_msg91_template_name,
)


def test_normalize_india_mobile() -> None:
    assert normalize_india_mobile("+919876543210") == "919876543210"
    assert normalize_india_mobile("9876543210") == "919876543210"


def test_resolve_msg91_template_name() -> None:
    settings = Settings(
        _env_file=None,
        msg91_whatsapp_otp_template="otp_tpl",
        msg91_job_match_template="match_tpl",
    )
    assert resolve_msg91_template_name(settings, "job_match_alert") == "match_tpl"
    assert resolve_msg91_template_name(settings, "hireloop_otp") == "otp_tpl"
    assert resolve_msg91_template_name(settings, "custom-id") == "custom-id"


@pytest.mark.asyncio
async def test_send_whatsapp_template_posts_to_msg91(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_post(self, url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured["json"] = kwargs.get("json")

        class _Resp:
            status_code = 200
            content = b'{"message_uuid":"abc"}'

            def json(self) -> dict[str, str]:
                return {"message_uuid": "abc"}

        return _Resp()

    monkeypatch.setattr(
        "hireloop_api.services.whatsapp.msg91.httpx.AsyncClient.post",
        fake_post,
    )

    wa = Msg91Client("auth-key", whatsapp_number="919111111111")
    try:
        result = await wa.send_whatsapp_template(
            to_phone="+919876543210",
            template_name="job_match_alert",
            body_params=["Alice", "Engineer"],
        )
    finally:
        await wa.close()

    assert result["sent"] is True
    assert (
        captured["url"] == "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"
    )
    assert captured["json"]["recipient_whatsapp"] == "919876543210"


@pytest.mark.asyncio
async def test_send_whatsapp_unconfigured_returns_mock() -> None:
    wa = Msg91Client("", whatsapp_number="")
    try:
        result = await wa.send_whatsapp_template(
            to_phone="+919876543210",
            template_name="job_match_alert",
        )
    finally:
        await wa.close()
    assert result["sent"] is False
    assert result.get("mock") is True
