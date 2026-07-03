"""Resolve candidate display names — prefer résumé/LinkedIn over email local-parts."""

from __future__ import annotations

import re


def looks_like_email_derived_name(full_name: str | None, email: str | None) -> bool:
    """
    True when `full_name` is empty or looks auto-generated from the signup email
    (e.g. rupesh.kumar@… → display name "rupesh.kumar").
    """
    name = (full_name or "").strip()
    if not name:
        return True
    if not email or "@" not in email:
        return False

    local = email.split("@", 1)[0].strip().lower()
    normalized = name.lower()

    # Title Case / mixed-case multi-word names are user-entered, not email local-parts.
    if " " in name and any(ch.isupper() for ch in name):
        return False

    if normalized == local:
        return True
    if normalized.replace(" ", ".") == local:
        return True
    if normalized.replace(" ", "") == local.replace(".", "").replace("_", ""):
        return True
    # Single token with dots, no spaces — typical email-prefix display name.
    if "." in normalized and " " not in normalized and normalized == local:
        return True
    # All-lowercase compact form matching email local part (rupesh.kumar → rupeshkumar).
    compact_local = re.sub(r"[._-]+", "", local)
    compact_name = re.sub(r"[._\s-]+", "", normalized)
    return bool(compact_local and compact_name == compact_local and normalized.islower())


def pick_display_name(
    *,
    user_full_name: str | None,
    email: str | None = None,
    resume_full_name: str | None = None,
    linkedin_full_name: str | None = None,
) -> str | None:
    """Best display name for UI salutations."""
    resume = (resume_full_name or "").strip()
    linkedin = (linkedin_full_name or "").strip()
    current = (user_full_name or "").strip()

    if resume and (not current or looks_like_email_derived_name(current, email)):
        return resume
    if linkedin and (not current or looks_like_email_derived_name(current, email)):
        return linkedin
    return current or resume or linkedin or None
