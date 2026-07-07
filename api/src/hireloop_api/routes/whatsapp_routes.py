"""
WhatsApp webhooks + notification triggers (P19) — MSG91 (R10).
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user, verify_service_secret
from hireloop_api.services.notifications import send_whatsapp_if_allowed

logger = structlog.get_logger()
router = APIRouter(prefix="/webhooks", tags=["whatsapp"])


class SendTestNotification(BaseModel):
    template_name: str = "job_match_alert"
    body_params: list[str] = []


def _parse_intro_button_payload(body: dict[str, Any]) -> tuple[str | None, str | None]:
    """Best-effort parse for JSON button payloads from MSG91 inbound events."""
    payload = body.get("payload") or body.get("button") or body.get("interactive") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {}
    if isinstance(payload, dict):
        intro_id = payload.get("intro_id")
        action = payload.get("action")
        if intro_id and action in ("accept", "decline"):
            return str(intro_id), str(action)
    return None, None


@router.post("/msg91-whatsapp")
async def msg91_whatsapp_webhook(
    request: Request,
    db: asyncpg.Connection = Depends(get_db),
    _: None = Depends(verify_service_secret),
) -> Response:
    """
    Inbound MSG91 WhatsApp events (delivery status, button replies).
    Configure MSG91 callback URL to POST here with X-Service-Secret header.
    """
    body = await request.json()
    event_type = body.get("type") or body.get("event")
    logger.info("msg91_whatsapp_webhook", event_type=event_type)

    intro_id, action = _parse_intro_button_payload(body)
    if intro_id and action:
        status = "accepted" if action == "accept" else "declined"
        await db.execute(
            """
            UPDATE public.intro_requests
            SET status = $2, updated_at = NOW()
            WHERE id = $1::uuid
            """,
            intro_id,
            status,
        )
        return Response(status_code=200)

    if event_type in ("message-event", "delivery"):
        payload = body.get("payload") or body
        logger.info(
            "msg91_message_event",
            message_status=payload.get("status") or payload.get("type"),
            destination=str(payload.get("destination", ""))[-4:],
        )
    elif event_type in ("message", "incoming"):
        payload = body.get("payload") or body
        button = payload.get("button") or payload.get("interactive")
        if isinstance(button, dict):
            logger.info("msg91_button_reply", button_text=button.get("text"))

    return Response(status_code=200)


@router.post("/test-whatsapp")
async def test_whatsapp_send(
    body: SendTestNotification,
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Dev helper: send a test WhatsApp template to the current user."""
    return await send_whatsapp_if_allowed(
        db,
        settings,
        user_id=current_user["id"],
        template_name=body.template_name,
        purpose="job_match",
        body_params=body.body_params or ["Test", "Role", "Company", "85", "https://hireschema.com"],
    )
