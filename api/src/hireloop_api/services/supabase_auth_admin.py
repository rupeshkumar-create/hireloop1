"""
Supabase Auth admin helpers (service role).

Used to auto-confirm OAuth signups so LinkedIn users are not sent a separate
email verification message — only email/password or magic-link signups require
inbox confirmation.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import structlog

from hireloop_api.config import Settings

logger = structlog.get_logger()

# Providers that prove email ownership via the IdP (no Hireloop verification mail).
_OAUTH_PROVIDERS = frozenset(
    {
        "linkedin",
        "linkedin_oidc",
        "google",
        "github",
        "apple",
        "azure",
        "facebook",
        "twitter",
        "discord",
        "gitlab",
        "bitbucket",
    }
)


def primary_auth_provider(supabase_user: dict[str, Any]) -> str:
    """Return the user's primary Supabase auth provider (e.g. email, linkedin_oidc)."""
    app_meta = supabase_user.get("app_metadata") or {}
    provider = str(app_meta.get("provider") or "").strip().lower()
    if provider:
        return provider
    providers = app_meta.get("providers") or []
    if isinstance(providers, list) and providers:
        return str(providers[0]).strip().lower()
    identities = supabase_user.get("identities") or []
    if isinstance(identities, list) and identities:
        first = identities[0]
        if isinstance(first, dict) and first.get("provider"):
            return str(first["provider"]).strip().lower()
    return "email"


def is_oauth_signup(supabase_user: dict[str, Any]) -> bool:
    """True when the account was created via an external OAuth/OIDC provider."""
    provider = primary_auth_provider(supabase_user)
    if provider in _OAUTH_PROVIDERS:
        return True
    app_meta = supabase_user.get("app_metadata") or {}
    providers = app_meta.get("providers") or []
    if isinstance(providers, list):
        return any(str(p).strip().lower() in _OAUTH_PROVIDERS for p in providers)
    return False


def _admin_headers(settings: Settings) -> dict[str, str]:
    key = settings.supabase_service_key
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


async def confirm_user_email(settings: Settings, user_id: uuid.UUID | str) -> bool:
    """
    Mark the Supabase Auth user as email-confirmed (no verification email needed).

    Best-effort — returns False when unconfigured or the admin call fails.
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        return False

    uid = str(user_id)
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin/users/{uid}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.put(
                url, headers=_admin_headers(settings), json={"email_confirm": True}
            )
        if resp.status_code in (200, 201):
            return True
        logger.warning(
            "supabase_confirm_email_failed",
            user_id=uid,
            status=resp.status_code,
            body=resp.text[:200],
        )
    except Exception as exc:
        logger.warning("supabase_confirm_email_error", user_id=uid, error=str(exc)[:200])
    return False


async def ensure_oauth_email_confirmed(
    settings: Settings,
    supabase_user: dict[str, Any],
) -> bool:
    """
    OAuth/OIDC signups: confirm email immediately so Supabase never blocks the
    session or sends a redundant verification email.
    """
    if not is_oauth_signup(supabase_user):
        return False
    if supabase_user.get("email_confirmed_at"):
        return True
    user_id = supabase_user.get("id")
    if not user_id:
        return False
    return await confirm_user_email(settings, user_id)
