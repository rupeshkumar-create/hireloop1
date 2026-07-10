"""
Resend HTML templates for user notification categories.

Renders through the shared Hireschema brand shell (logo + lime CTA).
"""

from __future__ import annotations

from typing import Any

from hireloop_api.services.email.lifecycle_templates import (
    render_notification_email as _render_branded,
)

NOTIFICATION_CATEGORIES = frozenset(
    {
        "job_match_alerts",
        "intro_updates",
        "interview_reminders",
        "aarya_digest",
        "profile_views",
        "application_updates",
        "platform_updates",
    }
)

CATEGORY_ALIASES: dict[str, str] = {
    "job_match": "job_match_alerts",
    "job_match_alert": "job_match_alerts",
    "intro_status": "intro_updates",
    "intro": "intro_updates",
    "interview_reminder": "interview_reminders",
    "weekly_digest": "aarya_digest",
    "profile_view": "profile_views",
    "application_update": "application_updates",
    "platform_update": "platform_updates",
}


def normalize_category(category: str) -> str:
    key = (category or "").strip()
    return CATEGORY_ALIASES.get(key, key)


def render_notification_email(category: str, data: dict[str, Any]) -> tuple[str, str]:
    return _render_branded(category, data)
