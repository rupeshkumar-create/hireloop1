"""
SendGrid transactional email service.

CRITICAL CONSTRAINT (R9 / R16 §2):
  SendGrid is ONLY used for transactional email — never cold/unsolicited.

  Allowed use cases:
    - signup_confirmation   : welcome email after LinkedIn OAuth + OTP
    - job_match_alert       : "X new matches" digest (candidate opted-in)
    - interview_reminder    : 24h before a booked voice-call slot
    - otp_fallback          : SMS OTP delivery fallback (email channel)
    - intro_status_update   : "Nitya sent your intro to {HM name}"

  NEVER allowed via SendGrid:
    - Outreach to hiring managers (use GmailOAuthService instead)
    - Marketing/bulk email
    - Any unsolicited email

Template IDs are stored in environment variables (never hardcoded UUIDs).
"""

from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger()

_SENDGRID_API = "https://api.sendgrid.com/v3"


class SendGridService:
    """
    Thin async wrapper for the SendGrid v3 Mail Send API.
    All methods send a single dynamic template email.
    """

    def __init__(self, api_key: str, from_email: str, from_name: str) -> None:
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name
        self._http = httpx.AsyncClient(
            base_url=_SENDGRID_API,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _send(
        self,
        to_email: str,
        to_name: str | None,
        template_id: str,
        dynamic_data: dict,
    ) -> bool:
        """
        Send a single dynamic template email.
        Returns True on success, False on failure (logs error).
        """
        payload = {
            "personalizations": [
                {
                    "to": [{"email": to_email, "name": to_name or to_email}],
                    "dynamic_template_data": dynamic_data,
                }
            ],
            "from": {"email": self._from_email, "name": self._from_name},
            "template_id": template_id,
        }

        try:
            res = await self._http.post("/mail/send", json=payload)
            if res.status_code == 202:
                logger.info("sendgrid_sent", to=to_email, template=template_id)
                return True

            logger.error(
                "sendgrid_failed",
                to=to_email,
                template=template_id,
                status=res.status_code,
                body=res.text[:500],
            )
            return False

        except Exception as exc:
            logger.error("sendgrid_error", to=to_email, error=str(exc))
            return False

    # ── Transactional email methods ───────────────────────────────────────────

    async def send_signup_confirmation(
        self,
        to_email: str,
        full_name: str,
        template_id: str,
    ) -> bool:
        """Welcome email after first login."""
        return await self._send(
            to_email=to_email,
            to_name=full_name,
            template_id=template_id,
            dynamic_data={
                "full_name": full_name,
                "cta_url": "https://app.hireloop.in/onboarding",
            },
        )

    async def send_job_match_alert(
        self,
        to_email: str,
        full_name: str,
        template_id: str,
        new_match_count: int,
        top_job_title: str,
        top_company: str,
        top_score_pct: int,
    ) -> bool:
        """Daily/weekly digest: "You have X new job matches"."""
        return await self._send(
            to_email=to_email,
            to_name=full_name,
            template_id=template_id,
            dynamic_data={
                "full_name": full_name,
                "match_count": new_match_count,
                "top_job_title": top_job_title,
                "top_company": top_company,
                "top_score_pct": top_score_pct,
                "cta_url": "https://app.hireloop.in/dashboard",
            },
        )

    async def send_interview_reminder(
        self,
        to_email: str,
        full_name: str,
        template_id: str,
        interview_date: str,
        interview_time: str,
        join_url: str,
    ) -> bool:
        """24h reminder before a booked AI career call."""
        return await self._send(
            to_email=to_email,
            to_name=full_name,
            template_id=template_id,
            dynamic_data={
                "full_name": full_name,
                "interview_date": interview_date,
                "interview_time": interview_time,
                "join_url": join_url,
            },
        )

    async def send_intro_status_update(
        self,
        to_email: str,
        full_name: str,
        template_id: str,
        hm_name: str,
        company_name: str,
        job_title: str,
        status: str,  # 'sent' | 'opened' | 'replied'
    ) -> bool:
        """Notify candidate when their intro request changes status."""
        status_messages = {
            "sent": f"Your intro to {hm_name} at {company_name} has been sent!",
            "opened": f"{hm_name} opened your intro email.",
            "replied": f"🎉 {hm_name} replied to your intro!",
        }
        return await self._send(
            to_email=to_email,
            to_name=full_name,
            template_id=template_id,
            dynamic_data={
                "full_name": full_name,
                "hm_name": hm_name,
                "company_name": company_name,
                "job_title": job_title,
                "status": status,
                "status_message": status_messages.get(status, f"Intro status: {status}"),
                "cta_url": "https://app.hireloop.in/dashboard",
            },
        )
