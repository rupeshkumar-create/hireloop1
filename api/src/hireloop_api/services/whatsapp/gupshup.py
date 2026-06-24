"""
Gupshup WhatsApp Business API — OTP verification + transactional templates (R10).

Used for: phone OTP (WhatsApp), job match alerts, intro status, interview reminders.
Never used for cold outreach (R9).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from hireloop_api.config import Settings

logger = structlog.get_logger()

GUPSHUP_TEMPLATE_MSG_URL = "https://api.gupshup.io/wa/api/v1/template/msg"


def normalize_india_whatsapp_number(phone: str) -> str:
    """E.164 without '+' — Gupshup expects e.g. 919876543210."""
    digits = phone.strip().lstrip("+")
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    if digits.startswith("91") and len(digits) == 12:
        return digits
    return digits


class GupshupWhatsApp:
    def __init__(
        self,
        api_key: str,
        source_number: str,
        *,
        app_name: str = "Hireloop",
    ) -> None:
        self._api_key = api_key
        self._source_number = normalize_india_whatsapp_number(source_number)
        self._app_name = app_name
        self._client = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def send_otp(
        self,
        *,
        to_phone: str,
        otp: str,
        template_id: str,
    ) -> dict[str, Any]:
        """Send OTP via an approved WhatsApp utility/authentication template."""
        return await self.send_template(
            to_phone=to_phone,
            template_id=template_id,
            body_params=[otp],
        )

    async def send_template(
        self,
        *,
        to_phone: str,
        template_id: str,
        body_params: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Send a pre-approved WhatsApp template message.
        `to_phone` must be +91... or 91...
        """
        if not self._api_key or not self._source_number or not template_id:
            return {
                "sent": False,
                "error": "Gupshup WhatsApp not configured",
                "mock": True,
            }

        destination = normalize_india_whatsapp_number(to_phone)
        template_payload = json.dumps(
            {"id": template_id, "params": body_params or []},
            separators=(",", ":"),
        )
        form_data = {
            "channel": "whatsapp",
            "source": self._source_number,
            "destination": destination,
            "src.name": self._app_name,
            "template": template_payload,
        }

        try:
            resp = await self._client.post(
                GUPSHUP_TEMPLATE_MSG_URL,
                headers={
                    "apikey": self._api_key,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=form_data,
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                logger.warning(
                    "gupshup_whatsapp_failed",
                    status=resp.status_code,
                    body=data,
                )
                return {"sent": False, "error": str(data), "status_code": resp.status_code}

            status = str(data.get("status", "")).lower()
            if status and status != "submitted":
                logger.warning("gupshup_whatsapp_unexpected_status", status=status, body=data)
                return {
                    "sent": False,
                    "error": f"Unexpected status: {status}",
                    "gupshup_response": data,
                }

            return {
                "sent": True,
                "gupshup_response": data,
                "message_id": data.get("messageId"),
            }
        except httpx.HTTPError as exc:
            logger.error("gupshup_whatsapp_error", error=str(exc))
            return {"sent": False, "error": str(exc)}


def resolve_gupshup_template_id(settings: Settings, template_name: str) -> str:
    """Map logical template names used in code to Gupshup template UUIDs."""
    mapping = {
        "job_match_alert": settings.gupshup_job_match_template_id,
        "hireloop_otp": settings.gupshup_otp_template_id,
        "intro_status": settings.gupshup_intro_status_template_id,
    }
    resolved = mapping.get(template_name, "")
    return resolved or template_name
