"""
MSG91 SMS + WhatsApp Business API — OTP verification + transactional templates (R10).

Used for: +91 SMS OTP, WhatsApp job alerts, intro status, interview reminders.
Never used for cold outreach (R9).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from hireloop_api.config import Settings

logger = structlog.get_logger()

MSG91_OTP_URL = "https://control.msg91.com/api/v5/otp"
MSG91_WHATSAPP_URL = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"


def normalize_india_mobile(phone: str) -> str:
    """E.164 without '+' — MSG91 expects e.g. 919876543210."""
    digits = phone.strip().lstrip("+")
    if len(digits) == 10 and digits[0] in "6789":
        return f"91{digits}"
    if digits.startswith("91") and len(digits) == 12:
        return digits
    return digits


class Msg91Client:
    def __init__(
        self,
        auth_key: str,
        *,
        sender_id: str = "HLLOOP",
        whatsapp_number: str = "",
    ) -> None:
        self._auth_key = auth_key
        self._sender_id = sender_id
        self._whatsapp_number = normalize_india_mobile(whatsapp_number) if whatsapp_number else ""
        self._client = httpx.AsyncClient(timeout=15.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def send_sms_otp(
        self,
        *,
        to_phone: str,
        otp: str,
        template_id: str = "",
    ) -> dict[str, Any]:
        """Send a 6-digit OTP via MSG91 SMS (India +91 only)."""
        if not self._auth_key:
            return {"sent": False, "error": "MSG91 not configured", "mock": True}

        mobile = normalize_india_mobile(to_phone)
        params: dict[str, str] = {
            "authkey": self._auth_key,
            "mobile": mobile,
            "otp_expiry": "10",
            "realTimeResponse": "1",
        }
        if template_id:
            params["template_id"] = template_id
        elif self._sender_id:
            params["sender"] = self._sender_id

        try:
            resp = await self._client.post(
                MSG91_OTP_URL,
                params=params,
                json={"OTP": otp},
                headers={"Content-Type": "application/json", "authkey": self._auth_key},
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                logger.warning("msg91_sms_otp_failed", status=resp.status_code, body=data)
                return {"sent": False, "error": str(data), "status_code": resp.status_code}

            msg_type = str(data.get("type", "")).lower()
            if msg_type == "error":
                logger.warning("msg91_sms_otp_error", body=data)
                return {"sent": False, "error": str(data.get("message", data))}

            return {
                "sent": True,
                "msg91_response": data,
                "message_id": data.get("request_id") or data.get("message"),
            }
        except httpx.HTTPError as exc:
            logger.error("msg91_sms_otp_error", error=str(exc))
            return {"sent": False, "error": str(exc)}

    async def send_whatsapp_template(
        self,
        *,
        to_phone: str,
        template_name: str,
        body_params: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send a pre-approved WhatsApp template via MSG91."""
        if not self._auth_key or not self._whatsapp_number or not template_name:
            return {
                "sent": False,
                "error": "MSG91 WhatsApp not configured",
                "mock": True,
            }

        destination = normalize_india_mobile(to_phone)
        parameters = [{"type": "text", "text": p} for p in (body_params or [])]
        payload = {
            "integrated_number": self._whatsapp_number,
            "content_type": "template",
            "payload": {
                "messaging_product": "whatsapp",
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en"},
                    "components": [
                        {
                            "type": "body",
                            "parameters": parameters,
                        }
                    ],
                },
            },
            "recipient_whatsapp": destination,
        }

        try:
            resp = await self._client.post(
                MSG91_WHATSAPP_URL,
                json=payload,
                headers={
                    "authkey": self._auth_key,
                    "Content-Type": "application/json",
                },
            )
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                logger.warning(
                    "msg91_whatsapp_failed",
                    status=resp.status_code,
                    body=data,
                )
                return {"sent": False, "error": str(data), "status_code": resp.status_code}

            return {
                "sent": True,
                "msg91_response": data,
                "message_id": data.get("message_uuid") or data.get("request_id"),
            }
        except httpx.HTTPError as exc:
            logger.error("msg91_whatsapp_error", error=str(exc))
            return {"sent": False, "error": str(exc)}


def resolve_msg91_template_name(settings: Settings, template_name: str) -> str:
    """Map logical template names used in code to MSG91 WhatsApp template names."""
    mapping = {
        "job_match_alert": settings.msg91_job_match_template,
        "hireloop_otp": settings.msg91_whatsapp_otp_template,
        "intro_status": settings.msg91_intro_status_template,
    }
    resolved = mapping.get(template_name, "")
    return resolved or template_name
