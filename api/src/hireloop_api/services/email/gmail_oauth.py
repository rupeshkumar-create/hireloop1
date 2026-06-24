"""
Gmail OAuth service — candidate-authorised cold outreach to hiring managers.

REQUIRED for all HM outreach (R9):
  "Request Intro" emails MUST be sent from the candidate's own Gmail account
  via their OAuth token. Hireloop NEVER sends cold email via SendGrid.

Flow:
  1. Candidate connects Gmail in onboarding (OAuth 2.0, scope: gmail.send)
  2. Tokens stored in public.gmail_tokens (encrypted at rest)
  3. Nitya drafts email, shows candidate a preview
  4. Candidate approves → GmailOAuthService.send_intro_email() fires

Token refresh is handled automatically before each send.

Gmail API reference: https://developers.google.com/gmail/api/reference/rest/v1/users.messages/send
"""

from __future__ import annotations

import base64
import email.mime.multipart
import email.mime.text
from datetime import UTC, datetime

import asyncpg
import httpx
import structlog

logger = structlog.get_logger()

_GMAIL_API = "https://www.googleapis.com/gmail/v1"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 — URL, not a secret


class GmailOAuthService:
    """
    Sends emails from a candidate's Gmail account using their OAuth token.

    Usage:
        svc = GmailOAuthService(client_id, client_secret, db)
        ok = await svc.send_intro_email(candidate_id, to_email, to_name, subject, body)
    """

    def __init__(
        self,
        google_client_id: str,
        google_client_secret: str,
        db: asyncpg.Connection,
    ) -> None:
        self._client_id = google_client_id
        self._client_secret = google_client_secret
        self._db = db
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    # ── Token management ──────────────────────────────────────────────────────

    async def _get_token(self, candidate_id: str) -> str | None:
        """
        Fetch a valid access token for this candidate.
        Refreshes automatically if expired.
        Returns None if no token exists.
        """
        row = await self._db.fetchrow(
            "SELECT * FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
            candidate_id,
        )
        if not row:
            return None

        # If token expires within 60 seconds, refresh it
        expires_at = row["token_expiry"]
        now = datetime.now(UTC)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        seconds_left = (expires_at - now).total_seconds()
        if seconds_left < 60:
            return await self._refresh_token(candidate_id, row["refresh_token"])

        return row["access_token"]

    async def _refresh_token(self, candidate_id: str, refresh_token: str) -> str | None:
        """Exchange a refresh token for a new access token. Returns new access token or None."""
        try:
            res = await self._http.post(
                _OAUTH_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            res.raise_for_status()
            data = res.json()

            new_token = data["access_token"]
            expires_in = data.get("expires_in", 3600)
            new_expiry = datetime.now(UTC).replace(microsecond=0)
            new_expiry = new_expiry.replace(second=new_expiry.second + expires_in)

            await self._db.execute(
                """
                UPDATE public.gmail_tokens
                SET access_token = $1, token_expiry = $2, updated_at = NOW()
                WHERE candidate_id = $3::uuid
                """,
                new_token,
                new_expiry,
                candidate_id,
            )

            logger.info("gmail_token_refreshed", candidate_id=candidate_id)
            return new_token

        except Exception as exc:
            logger.error("gmail_token_refresh_failed", candidate_id=candidate_id, error=str(exc))
            return None

    async def has_token(self, candidate_id: str) -> bool:
        """Check whether the candidate has a valid Gmail token stored."""
        row = await self._db.fetchrow(
            "SELECT id FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
            candidate_id,
        )
        return row is not None

    # ── Email sending ─────────────────────────────────────────────────────────

    async def send_intro_email(
        self,
        candidate_id: str,
        to_email: str,
        to_name: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        reply_to: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Send an intro email from the candidate's Gmail account.

        Returns (success: bool, gmail_message_id: str | None).
        The gmail_message_id is stored in intro_requests for thread tracking.
        """
        access_token = await self._get_token(candidate_id)
        if not access_token:
            logger.warning("gmail_no_token", candidate_id=candidate_id)
            return False, "No Gmail token — candidate must connect Gmail first"

        # Build MIME message
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["To"] = f"{to_name} <{to_email}>"
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to

        if body_text:
            msg.attach(email.mime.text.MIMEText(body_text, "plain", "utf-8"))
        msg.attach(email.mime.text.MIMEText(body_html, "html", "utf-8"))

        # Encode to base64url (Gmail API format)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        try:
            res = await self._http.post(
                f"{_GMAIL_API}/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
                timeout=30.0,
            )

            if res.status_code == 200:
                gmail_msg_id = res.json().get("id")
                logger.info(
                    "gmail_intro_sent",
                    candidate_id=candidate_id,
                    to=to_email,
                    msg_id=gmail_msg_id,
                )
                return True, gmail_msg_id

            logger.error(
                "gmail_send_failed",
                candidate_id=candidate_id,
                to=to_email,
                status=res.status_code,
                body=res.text[:300],
            )
            return False, f"Gmail API error {res.status_code}"

        except Exception as exc:
            logger.error("gmail_send_error", candidate_id=candidate_id, error=str(exc))
            return False, str(exc)

    # ── OAuth callback handler ────────────────────────────────────────────────

    async def save_oauth_tokens(
        self,
        candidate_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        gmail_email: str,
        scopes: list[str],
    ) -> bool:
        """
        Persist Gmail OAuth tokens after the consent flow completes.
        Idempotent — upserts on candidate_id.
        """
        from datetime import timedelta

        expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

        try:
            await self._db.execute(
                """
                INSERT INTO public.gmail_tokens
                    (candidate_id, access_token, refresh_token, token_expiry, email, scopes)
                VALUES ($1::uuid, $2, $3, $4, $5, $6)
                ON CONFLICT (candidate_id) DO UPDATE SET
                    access_token  = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    token_expiry  = EXCLUDED.token_expiry,
                    email         = EXCLUDED.email,
                    scopes        = EXCLUDED.scopes,
                    updated_at    = NOW()
                """,
                candidate_id,
                access_token,
                refresh_token,
                expiry,
                gmail_email,
                scopes,
            )
            logger.info("gmail_tokens_saved", candidate_id=candidate_id, email=gmail_email)
            return True
        except Exception as exc:
            logger.error("gmail_tokens_save_failed", candidate_id=candidate_id, error=str(exc))
            return False
