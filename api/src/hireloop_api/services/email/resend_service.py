"""
Resend transactional email client.

Preferred provider for product emails (welcome, job-match alerts). Sends plain
HTML — no template IDs to manage. Best-effort: callers treat a False return as
"not sent" and never let email failures break the request/job.
"""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

_RESEND_URL = "https://api.resend.com/emails"


class ResendService:
    def __init__(self, api_key: str, from_email: str, from_name: str) -> None:
        self._api_key = api_key
        self._from = f"{from_name} <{from_email}>" if from_name else from_email
        self._http = httpx.AsyncClient(
            base_url="https://api.resend.com",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def send(self, *, to_email: str, subject: str, html: str) -> bool:
        """Send one HTML email. Returns True on a 2xx from Resend."""
        if not self._api_key or not to_email:
            return False
        try:
            res = await self._http.post(
                "/emails",
                json={"from": self._from, "to": [to_email], "subject": subject, "html": html},
            )
            if res.status_code >= 300:
                logger.warning(
                    "resend_send_failed",
                    status=res.status_code,
                    body=res.text[:300],
                )
                return False
            return True
        except Exception as exc:  # network etc. — never raise to the caller
            logger.warning("resend_send_error", error=str(exc)[:300])
            return False
