"""
Resend HTML templates for user notification categories.

Each category maps to a toggle in app Settings → Notifications.
Templates are inline HTML (no Resend dashboard template IDs required).
"""

from __future__ import annotations

from html import escape
from typing import Any

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

# Legacy purpose keys → settings category id
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


def _shell(heading: str, body_html: str, cta_url: str, cta_label: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1a1a1a">
  <h2 style="font-size:20px;margin:0 0 12px">{heading}</h2>
  {body_html}
  <p style="margin:24px 0">
    <a href="{escape(cta_url)}" style="background:#111;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;display:inline-block">{escape(cta_label)}</a>
  </p>
  <p style="font-size:12px;color:#888;margin-top:24px">Hireschema — AI recruiting for India, the US &amp; the UK</p>
  <p style="font-size:11px;color:#aaa;margin-top:8px">Manage notifications in Settings on Hireschema.</p>
</div>"""


def render_notification_email(category: str, data: dict[str, Any]) -> tuple[str, str]:
    """Return (subject, html) for a notification category."""
    cat = normalize_category(category)
    name = escape(str(data.get("full_name") or "there"))
    cta_url = str(data.get("cta_url") or "https://www.hireschema.com/dashboard")

    if cat == "job_match_alerts":
        jobs = data.get("jobs") or []
        if jobs:
            rows = "".join(
                f"<li style='margin:6px 0;font-size:14px'><b>{escape(str(j.get('title', 'Role')))}</b>"
                f"{(' · ' + escape(str(j['company']))) if j.get('company') else ''} "
                f"<span style='color:#16a34a'>({int(j.get('score_pct', 0))}% match)</span></li>"
                for j in jobs
            )
            body = f"<ul style='padding-left:18px;margin:0'>{rows}</ul>"
            subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} on Hireschema"
            heading = f"{len(jobs)} new role{'s' if len(jobs) != 1 else ''} that fit you, {name}"
        else:
            title = escape(str(data.get("job_title") or "a role"))
            company = escape(str(data.get("company_name") or "a company"))
            pct = int(data.get("score_pct") or data.get("top_score_pct") or 0)
            body = (
                f"<p style='font-size:14px;line-height:1.6'><b>{title}</b> at {company} "
                f"— <span style='color:#16a34a'>{pct}% match</span></p>"
            )
            subject = f"New match: {data.get('job_title', 'Role')} on Hireschema"
            heading = f"A new role fits your profile, {name}"
        return subject, _shell(heading, body, cta_url, "View your matches")

    if cat == "intro_updates":
        msg = escape(str(data.get("status_message") or "Your intro status changed."))
        job = escape(str(data.get("job_title") or "the role"))
        company = escape(str(data.get("company_name") or "the company"))
        hm = escape(str(data.get("hm_name") or "the hiring manager"))
        body = (
            f"<p style='font-size:14px;line-height:1.6'>{msg}</p>"
            f"<p style='font-size:14px;line-height:1.6;color:#555'>"
            f"<b>{job}</b> at {company} · {hm}</p>"
        )
        return f"Intro update — {data.get('job_title', 'your role')}", _shell(
            f"Intro update for {name}", body, cta_url, "View intro status"
        )

    if cat == "interview_reminders":
        when = escape(str(data.get("scheduled_label") or data.get("scheduled_at") or "soon"))
        session = escape(str(data.get("session_label") or "AI career call"))
        body = (
            f"<p style='font-size:14px;line-height:1.6'>Your <b>{session}</b> with Aarya "
            f"is scheduled for <b>{when}</b>.</p>"
            "<p style='font-size:14px;line-height:1.6;color:#555'>"
            "Join from Hireschema at the scheduled time — voice or text, your choice.</p>"
        )
        is_reminder = bool(data.get("is_reminder"))
        subject = (
            f"Reminder: {session} tomorrow" if is_reminder else f"Booked: {session} with Aarya"
        )
        heading = f"Reminder, {name}" if is_reminder else f"You're booked, {name}"
        return subject, _shell(heading, body, cta_url, "Open Hireschema")

    if cat == "aarya_digest":
        matches = int(data.get("match_count") or 0)
        intros = int(data.get("intro_count") or 0)
        actions = int(data.get("actions_count") or 0)
        body = (
            "<p style='font-size:14px;line-height:1.6'>Here's what Aarya did for you this week:</p>"
            "<ul style='padding-left:18px;margin:0;font-size:14px;line-height:1.8'>"
            f"<li><b>{matches}</b> new job match{'es' if matches != 1 else ''}</li>"
            f"<li><b>{intros}</b> intro update{'s' if intros != 1 else ''}</li>"
            f"<li><b>{actions}</b> action{'s' if actions != 1 else ''} on your profile</li>"
            "</ul>"
        )
        return "Your weekly career digest from Aarya", _shell(
            f"Weekly digest for {name}", body, cta_url, "Open dashboard"
        )

    if cat == "profile_views":
        viewer = escape(str(data.get("viewer_label") or "A recruiter"))
        body = (
            f"<p style='font-size:14px;line-height:1.6'>{viewer} viewed your public "
            "Hireschema profile.</p>"
            "<p style='font-size:14px;line-height:1.6;color:#555'>"
            "Keep your headline and skills fresh so you stand out.</p>"
        )
        return "Someone viewed your Hireschema profile", _shell(
            f"Your profile was viewed, {name}", body, cta_url, "View your profile"
        )

    if cat == "application_updates":
        job = escape(str(data.get("job_title") or "a role"))
        company = escape(str(data.get("company_name") or "a company"))
        status = escape(str(data.get("status_label") or data.get("status") or "updated"))
        body = (
            f"<p style='font-size:14px;line-height:1.6'>Application status for "
            f"<b>{job}</b> at {company}: <b>{status}</b>.</p>"
        )
        return f"Application update — {data.get('job_title', 'your role')}", _shell(
            f"Application update, {name}", body, cta_url, "View pipeline"
        )

    if cat == "platform_updates":
        headline = escape(str(data.get("headline") or "What's new on Hireschema"))
        extra = str(data.get("body_html") or data.get("body") or "")
        if extra and "<" not in extra:
            extra = f"<p style='font-size:14px;line-height:1.6'>{escape(extra)}</p>"
        body = extra or (
            "<p style='font-size:14px;line-height:1.6'>We've shipped improvements to "
            "job matching, intros, and your Aarya chat experience.</p>"
        )
        cta_label = str(data.get("cta_label") or "See what's new")
        return str(data.get("subject") or headline), _shell(headline, body, cta_url, cta_label)

    # Fallback
    body = f"<p style='font-size:14px;line-height:1.6'>{escape(str(data.get('body', 'You have a new notification.')))}</p>"
    return "Update from Hireschema", _shell(f"Hi {name}", body, cta_url, "Open Hireschema")
