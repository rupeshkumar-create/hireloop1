"""Generic SMTP email sender (stdlib smtplib, run off the event loop).

Lets us send transactional email through any SMTP server — notably a free Gmail
account (smtp.gmail.com:587 + a Google App Password), which delivers to ANY
recipient with no verified sending domain. Best-effort: returns False on
failure and never raises to the caller.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

logger = structlog.get_logger()


class SmtpService:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        from_name: str,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        addr = from_email or user
        self._from = f"{from_name} <{addr}>" if from_name else addr

    def _send_sync(self, to_email: str, subject: str, html: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(self._host, self._port, timeout=20) as server:
            server.starttls()
            server.login(self._user, self._password)
            server.sendmail(self._user, [to_email], msg.as_string())

    async def send(self, *, to_email: str, subject: str, html: str) -> bool:
        if not (self._host and self._user and self._password and to_email):
            return False
        try:
            await asyncio.to_thread(self._send_sync, to_email, subject, html)
            return True
        except Exception as exc:  # network / auth — never raise to the caller
            logger.warning("smtp_send_failed", error=str(exc)[:300])
            return False
