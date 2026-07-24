"""
Google OAuth routes — connects a candidate's Google account (R9 outreach + P07).

GET  /api/v1/gmail/connect           → redirect to Google OAuth consent page
GET  /api/v1/gmail/callback          → OAuth callback: exchange code → save tokens
GET  /api/v1/gmail/status            → check the candidate's connected Google account
DELETE /api/v1/gmail/disconnect      → revoke + delete the stored token

Scopes requested (least-privilege, no read access to mail/calendar):
  - https://www.googleapis.com/auth/gmail.send       → P13 cold outreach (send only)
  - https://www.googleapis.com/auth/calendar.events  → P07 voice-session booking

Hireschema NEVER reads or indexes the candidate's email or calendar. gmail.send is
send-only and calendar.events only creates/cancels the events we book. This
commitment is documented in /terms and /privacy on the web app.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
import urllib.parse
import uuid

import asyncpg
import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.services.email.gmail_oauth import GmailOAuthService
from hireloop_api.services.token_crypto import decrypt_token

logger = structlog.get_logger()
router = APIRouter(prefix="/gmail", tags=["gmail", "gmail-oauth-v2"])

# Least-privilege scopes: send-only mail (P13) + event-only calendar (P07).
# `openid email` is required to read the connected account's address from the
# userinfo endpoint / id_token — without it that call 400s ("Could not fetch
# Gmail address"). These two are basic, non-sensitive scopes (no extra
# verification). One consent grants everything so the candidate connects once.
_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.send"
_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
_EMAIL_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
_GOOGLE_SCOPE = f"openid {_EMAIL_SCOPE} {_GMAIL_SCOPE} {_CALENDAR_SCOPE}"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# The callback is unauthenticated (Google redirects the browser there), so the
# `state` parameter is the ONLY binding between the OAuth result and a Hireschema
# user. A raw user-id state is forgeable: anyone who learns a victim's user-id
# could complete the flow with their own Google account and attach THEIR mailbox
# to the victim's profile (intercepting intro conversations). So state is
# HMAC-signed with SECRET_KEY and expires after 10 minutes.
_STATE_TTL_SECONDS = 600


def sign_oauth_state(secret: str, user_id: str, *, now: float | None = None) -> str:
    ts = str(int(now if now is not None else time.time()))
    msg = f"{user_id}.{ts}"
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}.{sig}"


def verify_oauth_state(secret: str, state: str, *, now: float | None = None) -> str | None:
    """Return the user_id if the state is authentic and unexpired, else None."""
    try:
        user_id, ts, sig = state.rsplit(".", 2)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), f"{user_id}.{ts}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        issued_at = int(ts)
    except ValueError:
        return None
    current = now if now is not None else time.time()
    if current - issued_at > _STATE_TTL_SECONDS:
        return None
    return user_id


def _email_from_id_token(id_token: str | None) -> str:
    """
    Read the `email` claim from a Google id_token (a JWT) without verifying the
    signature — safe here because the token came straight from Google's token
    endpoint over TLS in this same request, and we only read the email for
    display/storage. Returns "" if absent or unparseable.
    """
    if not id_token or id_token.count(".") != 2:
        return ""
    payload_b64 = id_token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)  # restore base64 padding
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (binascii.Error, ValueError, json.JSONDecodeError):
        return ""
    email = claims.get("email")
    return email if isinstance(email, str) else ""


def _build_auth_url(settings: Settings, user_id: str) -> str:
    """Build the Google consent URL (send-only Gmail + event-only Calendar)."""
    redirect_uri = settings.gmail_oauth_redirect_uri
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": _GOOGLE_SCOPE,
        "include_granted_scopes": "true",  # incremental auth — keep prior grants
        "access_type": "offline",  # get refresh token
        "prompt": "consent",  # force re-consent to always get refresh_token
        "state": sign_oauth_state(settings.secret_key, user_id),
    }
    return f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


@router.get("/connect")
async def gmail_connect(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """
    Start the Google OAuth flow via a server redirect (used when the browser can
    carry the session as a cookie). SPA clients use `/auth-url` instead.
    """
    return RedirectResponse(url=_build_auth_url(settings, current_user["id"]))


@router.get("/auth-url")
async def gmail_auth_url(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
) -> dict:
    """
    Return the Google consent URL as JSON so the Bearer-token SPA can start the
    flow with `window.location.href = auth_url` (a plain link can't carry the JWT).
    """
    if not settings.google_client_id:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    return {
        "auth_url": _build_auth_url(settings, current_user["id"]),
        "redirect_uri": settings.gmail_oauth_redirect_uri,
    }


def _dashboard_gmail_redirect(
    settings: Settings,
    *,
    status: str,
    reason: str | None = None,
) -> RedirectResponse:
    """Send the browser to chat (no panel) with a gmail= query the SPA handles."""
    base = settings.public_app_url.rstrip("/") or "https://www.hireschema.com"
    q = f"gmail={urllib.parse.quote(status)}"
    if reason:
        q += f"&gmail_reason={urllib.parse.quote(reason)}"
    return RedirectResponse(url=f"{base}/dashboard?{q}", status_code=302)


@router.get("/callback")
async def gmail_callback(
    code: str = Query(...),
    state: str = Query(...),  # HMAC-signed "user_id.ts.sig" issued by /connect
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> RedirectResponse:
    """
    OAuth callback: exchange auth code for tokens.
    Redirects to /dashboard?gmail=connected (chat) on success.
    """
    # Verify the state BEFORE any token exchange — a forged or expired state must
    # never bind Google tokens to a Hireschema account.
    user_id = verify_oauth_state(settings.secret_key, state)
    if not user_id:
        logger.warning("gmail_callback_bad_state")
        return _dashboard_gmail_redirect(settings, status="error", reason="bad_state")

    redirect_uri = settings.gmail_oauth_redirect_uri

    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            # Exchange code for tokens
            token_res = await http.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id.strip(),
                    "client_secret": settings.google_client_secret.strip(),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if not token_res.is_success:
                body = token_res.text[:300]
                logger.error(
                    "gmail_token_exchange_failed",
                    status=token_res.status_code,
                    body=body,
                )
                reason = "token_exchange"
                err_payload = (
                    token_res.json()
                    if "application/json" in (token_res.headers.get("content-type") or "")
                    else {}
                )
                err = err_payload.get("error") if isinstance(err_payload, dict) else None
                if isinstance(err, str) and err:
                    reason = err  # e.g. invalid_client, invalid_grant
                return _dashboard_gmail_redirect(settings, status="error", reason=reason)

            tokens = token_res.json()

            # Resolve the connected account's email. Prefer the userinfo endpoint;
            # if it fails, fall back to the `email` claim in the id_token (present
            # because we requested the `openid` scope) so the flow never hard-fails.
            gmail_email = ""
            userinfo_res = await http.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            if userinfo_res.is_success:
                gmail_email = userinfo_res.json().get("email", "")
            if not gmail_email:
                gmail_email = _email_from_id_token(tokens.get("id_token"))
            if not gmail_email:
                logger.error("gmail_email_unresolved", userinfo_status=userinfo_res.status_code)
                return _dashboard_gmail_redirect(
                    settings, status="error", reason="email_unresolved"
                )

        # Get candidate_id from the verified user_id
        candidate = await db.fetchrow(
            "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
            uuid.UUID(user_id),
        )
        if not candidate:
            logger.warning("gmail_callback_no_candidate", user_id=user_id)
            return _dashboard_gmail_redirect(settings, status="error", reason="no_candidate")

        scope_raw = (tokens.get("scope") or "").strip() or _GOOGLE_SCOPE
        svc = GmailOAuthService(
            google_client_id=settings.google_client_id.strip(),
            google_client_secret=settings.google_client_secret.strip(),
            db=db,
        )
        try:
            ok = await svc.save_oauth_tokens(
                candidate_id=str(candidate["id"]),
                access_token=tokens["access_token"],
                refresh_token=tokens.get("refresh_token") or "",
                expires_in=tokens.get("expires_in", 3600),
                gmail_email=gmail_email,
                scopes=scope_raw.split(),
            )
            if not ok:
                return _dashboard_gmail_redirect(settings, status="error", reason="save_failed")
        finally:
            await svc.close()

        logger.info("gmail_connected", user_id=user_id, gmail=gmail_email)
        return _dashboard_gmail_redirect(settings, status="connected")
    except Exception as exc:
        logger.error("gmail_callback_failed", error=str(exc)[:300])
        return _dashboard_gmail_redirect(settings, status="error", reason="exception")


@router.get("/status")
async def gmail_status(
    current_user: dict = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Check whether the candidate has a connected Gmail token."""
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    row = await db.fetchrow(
        "SELECT email, token_expiry, scopes FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
        candidate["id"],
    )

    scopes = list(row["scopes"]) if row and row["scopes"] else []
    return {
        "connected": row is not None,
        "gmail_email": row["email"] if row else None,
        # Whether the granted token includes each capability (a candidate who
        # connected before calendar.events was added will show calendar=False).
        "send_enabled": _GMAIL_SCOPE in scopes,
        "calendar_enabled": _CALENDAR_SCOPE in scopes,
    }


@router.delete("/disconnect", status_code=200)
async def gmail_disconnect(
    current_user: dict = Depends(get_phone_verified_user),
    settings: Settings = Depends(get_settings),
    db: asyncpg.Connection = Depends(get_db),
) -> dict:
    """
    Revoke Gmail OAuth token and delete stored credentials.
    Candidate can reconnect at any time.
    """
    candidate = await db.fetchrow(
        "SELECT id FROM public.candidates WHERE user_id = $1::uuid AND deleted_at IS NULL",
        uuid.UUID(current_user["id"]),
    )
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    row = await db.fetchrow(
        "SELECT access_token FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
        candidate["id"],
    )

    if row:
        # Attempt to revoke the token with Google
        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                await http.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": decrypt_token(row["access_token"])},
                )
        except Exception as exc:
            # Revocation failure is non-fatal — delete locally anyway.
            logger.debug("gmail_revoke_failed", error=str(exc))

        await db.execute(
            "DELETE FROM public.gmail_tokens WHERE candidate_id = $1::uuid",
            candidate["id"],
        )

    logger.info("gmail_disconnected", user_id=current_user["id"])
    return {"disconnected": True}
