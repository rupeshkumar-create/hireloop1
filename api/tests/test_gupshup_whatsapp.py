import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from hireloop_api.config import Settings
from hireloop_api.services.whatsapp.gupshup import (
    GupshupWhatsApp,
    normalize_india_whatsapp_number,
    resolve_gupshup_template_id,
)


def test_normalize_india_whatsapp_number() -> None:
    assert normalize_india_whatsapp_number("+919876543210") == "919876543210"
    assert normalize_india_whatsapp_number("9876543210") == "919876543210"


def test_resolve_gupshup_template_id() -> None:
    settings = Settings(
        _env_file=None,
        gupshup_otp_template_id="otp-uuid",
        gupshup_job_match_template_id="match-uuid",
    )
    assert resolve_gupshup_template_id(settings, "job_match_alert") == "match-uuid"
    assert resolve_gupshup_template_id(settings, "hireloop_otp") == "otp-uuid"
    assert resolve_gupshup_template_id(settings, "custom-id") == "custom-id"


@pytest.mark.asyncio
async def test_send_template_submits_to_gupshup(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_post(url: str, *, headers: dict[str, str], data: dict[str, str]) -> MagicMock:
        captured["url"] = url
        captured["headers"] = headers
        captured["data"] = data
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"status":"submitted","messageId":"msg-123"}'
        response.json.return_value = {"status": "submitted", "messageId": "msg-123"}
        return response

    monkeypatch.setattr(
        "hireloop_api.services.whatsapp.gupshup.httpx.AsyncClient.post",
        AsyncMock(side_effect=fake_post),
    )

    wa = GupshupWhatsApp("api-key", "919111111111", app_name="Hireloop")
    try:
        result = await wa.send_template(
            to_phone="+919876543210",
            template_id="template-uuid",
            body_params=["123456"],
        )
    finally:
        await wa.close()

    assert result["sent"] is True
    assert result["message_id"] == "msg-123"
    assert captured["url"] == "https://api.gupshup.io/wa/api/v1/template/msg"
    data = captured["data"]
    assert isinstance(data, dict)
    assert data["destination"] == "919876543210"
    assert data["source"] == "919111111111"
    assert json.loads(data["template"]) == {"id": "template-uuid", "params": ["123456"]}


@pytest.mark.asyncio
async def test_send_template_mock_when_unconfigured() -> None:
    wa = GupshupWhatsApp("", "", app_name="Hireloop")
    try:
        result = await wa.send_template(
            to_phone="+919876543210",
            template_id="",
            body_params=["123456"],
        )
    finally:
        await wa.close()

    assert result["sent"] is False
    assert result.get("mock") is True
