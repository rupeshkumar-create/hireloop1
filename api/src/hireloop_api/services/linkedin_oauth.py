"""Helpers for LinkedIn OIDC payloads stored in candidates.linkedin_data."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

_HEADLINE_KEYS = (
    "headline",
    "professional_headline",
    "job_title",
    "title",
    "occupation",
    "tagline",
)

_NAME_KEYS = ("full_name", "name", "preferred_username")


def _walk(payload: Any) -> list[dict[str, Any]]:
    """Flatten nested OAuth blobs into dict nodes to search."""
    nodes: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        nodes.append(payload)
        for value in payload.values():
            nodes.extend(_walk(value))
    elif isinstance(payload, list):
        for item in payload:
            nodes.extend(_walk(item))
    return nodes


def _first_string(payload: Any, keys: tuple[str, ...]) -> str | None:
    for node in _walk(payload):
        for key in keys:
            raw = node.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def is_valid_linkedin_profile_url(url: str | None) -> bool:
    """Reject OAuth/login URLs; require a member profile path (/in/ or /pub/)."""
    if not url or not isinstance(url, str):
        return False
    lower = url.strip().lower()
    if "linkedin.com" not in lower:
        return False
    blocked = ("/oauth", "/login", "/checkpoint", "/uas/", "/authwall")
    if any(fragment in lower for fragment in blocked):
        return False
    return "/in/" in lower or "/pub/" in lower


def extract_linkedin_profile_url(payload: Any) -> str | None:
    """
    Best-effort public LinkedIn profile URL from OAuth user_metadata / identities.
    """
    if not payload:
        return None

    if isinstance(payload, dict):
        for key in (
            "linkedin_url",
            "linkedinUrl",
            "public_profile_url",
            "publicProfileUrl",
            "profile_url",
            "profileUrl",
            "oauth_profile_url",
        ):
            value = payload.get(key)
            if isinstance(value, str) and is_valid_linkedin_profile_url(value):
                return value.strip()

        # OIDC "profile" is often a generic linkedin.com/oauth URL — try vanity next.
        for key in ("profile", "url", "website"):
            value = payload.get(key)
            if isinstance(value, str) and is_valid_linkedin_profile_url(value):
                return value.strip()

        for key in ("preferred_username", "username", "user_name", "vanity", "vanityName"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                slug = value.strip().lstrip("@")
                if "linkedin.com/" in slug.lower():
                    return slug
                return f"https://www.linkedin.com/in/{slug}"

        for value in payload.values():
            found = extract_linkedin_profile_url(value)
            if found:
                return found
        return None

    if isinstance(payload, list):
        for item in payload:
            found = extract_linkedin_profile_url(item)
            if found:
                return found
        return None

    if isinstance(payload, str):
        text = payload.strip()
        if is_valid_linkedin_profile_url(text):
            return text
        return None

    return None


def _coerce_linkedin_blob(linkedin_data: Any) -> dict[str, Any]:
    if isinstance(linkedin_data, dict):
        return linkedin_data
    if isinstance(linkedin_data, str):
        try:
            parsed = json.loads(linkedin_data)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def candidate_has_apify_profile(linkedin_data: Any) -> bool:
    """True only when Apify returned a non-empty profile payload."""
    blob = _coerce_linkedin_blob(linkedin_data)
    apify = blob.get("apify_profile")
    return isinstance(apify, dict) and bool(apify)


def candidate_has_linkdapi_profile(linkedin_data: Any) -> bool:
    """True when LinkDAPI returned experience/overview data."""
    blob = _coerce_linkedin_blob(linkedin_data)
    linkd = blob.get("linkdapi_profile")
    if not isinstance(linkd, dict) or not linkd:
        return False
    if linkd.get("experience") or linkd.get("overview"):
        return True
    return bool(blob.get("linkdapi_enriched_at"))


def linkedin_scrape_cooldown_elapsed(
    linkedin_data: Any,
    *,
    retry_after_hours: float = 6.0,
) -> bool:
    """
    True when we may attempt another scrape (never tried, or last try was long ago).
    """
    blob = _coerce_linkedin_blob(linkedin_data)
    if candidate_has_apify_profile(blob) or candidate_has_linkdapi_profile(blob):
        return False

    raw_at = blob.get("apify_scraped_at")
    if not isinstance(raw_at, str) or not raw_at.strip():
        return True

    try:
        scraped_at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
    except ValueError:
        return True

    if scraped_at.tzinfo is None:
        scraped_at = scraped_at.replace(tzinfo=UTC)

    return datetime.now(UTC) - scraped_at >= timedelta(hours=retry_after_hours)


def candidate_needs_linkedin_extraction(
    *,
    linkedin_url: str | None,
    linkedin_data: Any,
    force_retry: bool = False,
    retry_after_hours: float = 6.0,
) -> tuple[bool, str | None]:
    """
    True when the candidate has a LinkedIn URL but no successful Apify extraction yet.
    """
    blob = _coerce_linkedin_blob(linkedin_data)
    if candidate_has_apify_profile(blob) or candidate_has_linkdapi_profile(blob):
        return False, None

    profile_url = resolve_linkedin_profile_url(linkedin_url, blob)
    if not profile_url:
        return False, None

    if not force_retry and not linkedin_scrape_cooldown_elapsed(
        blob, retry_after_hours=retry_after_hours
    ):
        return False, None

    return True, profile_url


def resolve_linkedin_profile_url(
    linkedin_url: str | None,
    linkedin_data: Any,
) -> str | None:
    """Prefer explicit column URL, then OAuth blob (skips invalid /oauth links)."""
    if is_valid_linkedin_profile_url(linkedin_url):
        return linkedin_url.strip()  # type: ignore[union-attr]
    return extract_linkedin_profile_url(linkedin_data)


def extract_linkedin_display_name(linkedin_data: Any) -> str | None:
    """Best-effort display name from Supabase LinkedIn user_metadata / identities."""
    if not linkedin_data:
        return None
    name = _first_string(linkedin_data, _NAME_KEYS)
    if name:
        return name
    for node in _walk(linkedin_data):
        given = node.get("given_name")
        family = node.get("family_name")
        if isinstance(given, str) and given.strip():
            parts = [given.strip()]
            if isinstance(family, str) and family.strip():
                parts.append(family.strip())
            return " ".join(parts)
    return None


def extract_linkedin_headline(linkedin_data: Any) -> str | None:
    """
    LinkedIn professional headline (not the member's name).

    Supabase LinkedIn OIDC often stores this on user_metadata.headline or
    identities[].identity_data.headline.
    """
    if not linkedin_data:
        return None
    headline = _first_string(linkedin_data, _HEADLINE_KEYS)
    if not headline:
        return None
    display_name = extract_linkedin_display_name(linkedin_data)
    if display_name and headline.casefold() == display_name.casefold():
        return None
    if len(headline) > 220:
        return headline[:220].rstrip()
    return headline


async def heal_candidate_headline_from_linkedin(
    db: asyncpg.Connection,
    *,
    user_id: uuid.UUID | str,
    linkedin_data: Any,
    user_full_name: str | None,
) -> str | None:
    """
    Persist LinkedIn headline when the stored value is a placeholder or the user's name.
    Returns the headline now on the candidate row (after heal), or None if no row.
    """
    from hireloop_api.services.profile_experience import best_linkedin_headline

    linkedin_headline = best_linkedin_headline(linkedin_data)
    if not linkedin_headline:
        return None

    row = await db.fetchrow(
        """
        SELECT id, headline
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        uuid.UUID(str(user_id)),
    )
    if not row:
        return None

    display_name = extract_linkedin_display_name(linkedin_data)
    if headline_should_use_linkedin(
        row["headline"],
        display_name=display_name,
        user_full_name=user_full_name,
    ):
        await db.execute(
            """
            UPDATE public.candidates
            SET headline = $2, updated_at = NOW()
            WHERE id = $1::uuid
            """,
            row["id"],
            linkedin_headline,
        )
        return linkedin_headline
    return row["headline"]


def headline_should_use_linkedin(
    stored_headline: str | None,
    *,
    display_name: str | None,
    user_full_name: str | None,
) -> bool:
    """True when DB headline is empty, placeholder, or mistakenly set to the user's name."""
    if not stored_headline or not stored_headline.strip():
        return True
    value = stored_headline.strip()
    if value == "New candidate":
        return True
    names = {n.strip().casefold() for n in (display_name, user_full_name) if n and n.strip()}
    return value.casefold() in names
