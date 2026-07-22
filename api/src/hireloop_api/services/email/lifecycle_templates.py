"""
Lifecycle email copy — one branded HTML template per product moment.
"""

from __future__ import annotations

from html import escape
from typing import Any

from hireloop_api.services.email.brand_email import (
    MATCH_GREEN,
    brand_shell,
    bullet_list,
    muted_paragraph,
    paragraph,
)


def render_welcome_email(
    *,
    role: str,
    full_name: str | None,
    app_base_url: str,
) -> tuple[str, str]:
    name = escape((full_name or "").strip() or "there")
    base = (app_base_url or "https://www.hireschema.com").rstrip("/")

    if role == "recruiter":
        body = (
            paragraph(f"Hi {name},")
            + paragraph(
                "You're set up as a <strong>hiring team</strong> on Hireschema. "
                "<strong>Nitya</strong>, your AI sourcer, helps you describe open roles, "
                "surface pre-scored candidates, and warm up intros — consent-first."
            )
            + bullet_list(
                [
                    "Post roles and share public job links",
                    "Review candidate fit scores before you reach out",
                    "Candidates approve every connection",
                ]
            )
        )
        return (
            "Welcome to Hireschema — meet Nitya",
            brand_shell(
                "Welcome — Nitya is ready to source",
                body,
                f"{base}/recruiter",
                "Open recruiter dashboard",
                app_base=base,
                preheader="Your AI sourcer Nitya is ready on Hireschema.",
            ),
        )

    body = (
        paragraph(f"Hi {name},")
        + paragraph(
            "You're in. <strong>Aarya</strong>, your AI recruiter, reads your profile, "
            "finds live roles in your market, scores your fit, and requests warm intros "
            "with your approval every step of the way."
        )
        + bullet_list(
            [
                "Chat by text or voice — tell Aarya what you want next",
                "See matched roles ranked for your background",
                "Prepare cover letters and interview prep per role",
            ]
        )
    )
    return (
        "Welcome to Hireschema — meet Aarya",
        brand_shell(
            "Welcome — Aarya is on your side",
            body,
            f"{base}/dashboard",
            "Talk to Aarya",
            app_base=base,
            preheader="Your AI recruiter Aarya is ready on Hireschema.",
        ),
    )


def render_first_job_found_email(
    *,
    full_name: str | None,
    job_title: str,
    company_name: str | None,
    score_pct: int,
    app_base_url: str,
    job_id: str | None = None,
) -> tuple[str, str]:
    base = (app_base_url or "https://www.hireschema.com").rstrip("/")
    name = escape((full_name or "").strip() or "there")
    title = escape(job_title or "a role")
    company = escape(company_name or "a company")
    cta = f"{base}/dashboard?panel=jobs"
    if job_id:
        cta = f"{base}/jobs/{job_id}"
    body = (
        paragraph(f"Hi {name},")
        + paragraph(
            "Great news — we found your <strong>first matching role</strong> on Hireschema:"
        )
        + paragraph(
            f"<strong style='font-size:17px;'>{title}</strong> at {company} "
            f"<span style='color:{MATCH_GREEN};font-weight:600;'>({score_pct}% fit)</span>"
        )
        + muted_paragraph(
            "Aarya will keep scanning your market overnight. Open your dashboard to save this role, "
            "request a warm intro, or ask for an application kit."
        )
    )
    return (
        f"Your first job match: {job_title}",
        brand_shell(
            "Your first match is here",
            body,
            cta,
            "View this role",
            app_base=base,
            preheader=f"{job_title} at {company_name or 'a company'} — {score_pct}% fit",
        ),
    )


def render_intro_requested_candidate_email(
    *,
    full_name: str | None,
    job_title: str,
    company_name: str | None,
    app_base_url: str,
) -> tuple[str, str]:
    base = (app_base_url or "https://www.hireschema.com").rstrip("/")
    name = escape((full_name or "").strip() or "there")
    body = (
        paragraph(f"Hi {name},")
        + paragraph(
            f"We received your intro request for <strong>{escape(job_title)}</strong> "
            f"at <strong>{escape(company_name or 'the company')}</strong>."
        )
        + bullet_list(
            [
                "Aarya / Nitya will draft a personalised note",
                "You'll review before anything is sent",
                "We'll email you when the hiring manager responds",
            ]
        )
    )
    return (
        f"Intro requested — {job_title}",
        brand_shell(
            "We're on it",
            body,
            f"{base}/dashboard?panel=inbox",
            "Track intro status",
            app_base=base,
            preheader=f"Your intro request for {job_title} is in progress.",
        ),
    )


def render_recruiter_intro_request_email(
    *,
    recruiter_name: str | None,
    candidate_name: str,
    job_title: str,
    app_base_url: str,
) -> tuple[str, str]:
    base = (app_base_url or "https://www.hireschema.com").rstrip("/")
    name = escape((recruiter_name or "").strip() or "there")
    cand = escape(candidate_name or "A candidate")
    role = escape(job_title or "your role")
    body = (
        paragraph(f"Hi {name},")
        + paragraph(
            f"<strong>{cand}</strong> requested an intro for <strong>{role}</strong> on Hireschema."
        )
        + muted_paragraph(
            "Review their profile and fit score in your inbox — accept to open a conversation."
        )
    )
    return (
        f"{candidate_name} requested an intro — {job_title}",
        brand_shell(
            "New intro request",
            body,
            f"{base}/recruiter/inbox",
            "Review in inbox",
            app_base=base,
            preheader=f"{candidate_name} wants to connect about {job_title}.",
        ),
    )


def render_recruiter_approach_candidate_email(
    *,
    candidate_name: str | None,
    recruiter_name: str | None,
    job_title: str,
    company_name: str | None,
    app_base_url: str,
) -> tuple[str, str]:
    base = (app_base_url or "https://www.hireschema.com").rstrip("/")
    name = escape((candidate_name or "").strip() or "there")
    recruiter = escape(recruiter_name or "A hiring team")
    role = escape(job_title or "a role")
    company = escape(company_name or "their company")
    body = (
        paragraph(f"Hi {name},")
        + paragraph(
            f"<strong>{recruiter}</strong> at <strong>{company}</strong> wants to connect "
            f"with you about <strong>{role}</strong>."
        )
        + muted_paragraph(
            "Open your intro inbox to accept, decline, or ask Aarya for advice before you reply."
        )
    )
    return (
        f"A recruiter wants to connect — {job_title}",
        brand_shell(
            "Someone wants to meet you",
            body,
            f"{base}/dashboard?panel=inbox",
            "View intro request",
            app_base=base,
            preheader=f"{recruiter_name or 'A recruiter'} is interested in you for {job_title}.",
        ),
    )


def render_notification_email(category: str, data: dict[str, Any]) -> tuple[str, str]:
    """Branded wrapper for all Settings → Notifications categories."""
    from hireloop_api.services.email.notification_templates import normalize_category

    cat = normalize_category(category)
    name = escape(str(data.get("full_name") or "there"))
    cta_url = str(data.get("cta_url") or "https://www.hireschema.com/dashboard")
    app_base = (
        cta_url.split("/dashboard")[0] if "/dashboard" in cta_url else "https://www.hireschema.com"
    )

    if cat == "job_match_alerts":
        jobs = data.get("jobs") or []
        if jobs:
            rows = "".join(
                f"<li style='margin:6px 0;font-size:14px;line-height:1.5;'>"
                f"<strong>{escape(str(j.get('title', 'Role')))}</strong>"
                f"{(' · ' + escape(str(j['company']))) if j.get('company') else ''} "
                f"<span style='color:{MATCH_GREEN};font-weight:600;'>"
                f"({int(j.get('score_pct', 0))}% match)</span></li>"
                for j in jobs
            )
            body = f"<ul style='padding-left:18px;margin:0 0 12px;'>{rows}</ul>"
            subject = f"{len(jobs)} new job match{'es' if len(jobs) != 1 else ''} on Hireschema"
            heading = f"{len(jobs)} new role{'s' if len(jobs) != 1 else ''} for you, {name}"
        else:
            title = escape(str(data.get("job_title") or "a role"))
            company = escape(str(data.get("company_name") or "a company"))
            pct = int(data.get("score_pct") or data.get("top_score_pct") or 0)
            body = paragraph(
                f"<strong>{title}</strong> at {company} "
                f"<span style='color:{MATCH_GREEN};font-weight:600;'>({pct}% match)</span>"
            )
            subject = f"New match: {data.get('job_title', 'Role')} on Hireschema"
            heading = f"A new role fits your profile, {name}"
        return subject, brand_shell(heading, body, cta_url, "View your matches", app_base=app_base)

    if cat == "intro_updates":
        msg = escape(str(data.get("status_message") or "Your intro status changed."))
        job = escape(str(data.get("job_title") or "the role"))
        company = escape(str(data.get("company_name") or "the company"))
        hm = escape(str(data.get("hm_name") or "the hiring manager"))
        body = paragraph(msg) + muted_paragraph(f"<strong>{job}</strong> at {company} · {hm}")
        return (
            f"Intro update — {data.get('job_title', 'your role')}",
            brand_shell(
                f"Intro update, {name}", body, cta_url, "View intro status", app_base=app_base
            ),
        )

    if cat == "interview_reminders":
        when = escape(str(data.get("scheduled_label") or data.get("scheduled_at") or "soon"))
        session = escape(str(data.get("session_label") or "AI career call"))
        cta_label = str(data.get("cta_label") or "Open Hireschema")
        body = paragraph(
            f"Your <strong>{session}</strong> with Aarya is scheduled for <strong>{when}</strong>."
        ) + muted_paragraph("Join from Hireschema — voice or text, your choice.")
        is_reminder = bool(data.get("is_reminder"))
        subject = (
            f"Reminder: {session} tomorrow" if is_reminder else f"Booked: {session} with Aarya"
        )
        heading = f"Reminder, {name}" if is_reminder else f"You're booked, {name}"
        return subject, brand_shell(heading, body, cta_url, cta_label, app_base=app_base)

    if cat == "aarya_digest":
        matches = int(data.get("match_count") or 0)
        intros = int(data.get("intro_count") or 0)
        actions = int(data.get("actions_count") or 0)
        body = paragraph("Here's what Aarya did for you this week:") + bullet_list(
            [
                f"{matches} new job match{'es' if matches != 1 else ''}",
                f"{intros} intro update{'s' if intros != 1 else ''}",
                f"{actions} action{'s' if actions != 1 else ''} on your profile",
            ]
        )
        return (
            "Your weekly career digest from Aarya",
            brand_shell(
                f"Weekly digest for {name}", body, cta_url, "Open dashboard", app_base=app_base
            ),
        )

    if cat == "profile_views":
        viewer = escape(str(data.get("viewer_label") or "A recruiter"))
        body = paragraph(f"{viewer} viewed your public Hireschema profile.") + muted_paragraph(
            "Keep your headline and skills fresh so you stand out."
        )
        return (
            "Someone viewed your Hireschema profile",
            brand_shell(
                f"Your profile was viewed, {name}",
                body,
                cta_url,
                "View your profile",
                app_base=app_base,
            ),
        )

    if cat == "application_updates":
        job = escape(str(data.get("job_title") or "a role"))
        company = escape(str(data.get("company_name") or "a company"))
        status = escape(str(data.get("status_label") or data.get("status") or "updated"))
        body = paragraph(
            f"Application for <strong>{job}</strong> at {company}: <strong>{status}</strong>."
        )
        return (
            f"Application update — {data.get('job_title', 'your role')}",
            brand_shell(
                f"Application update, {name}", body, cta_url, "View pipeline", app_base=app_base
            ),
        )

    if cat == "platform_updates":
        headline = escape(str(data.get("headline") or "What's new on Hireschema"))
        extra = str(data.get("body_html") or data.get("body") or "")
        if extra and "<" not in extra:
            extra = paragraph(escape(extra))
        body = extra or paragraph(
            "We've shipped improvements to job matching, intros, and your Aarya chat experience."
        )
        cta_label = str(data.get("cta_label") or "See what's new")
        return str(data.get("subject") or headline), brand_shell(
            headline, body, cta_url, cta_label, app_base=app_base
        )

    body = paragraph(escape(str(data.get("body", "You have a new notification on Hireschema."))))
    return "Update from Hireschema", brand_shell(
        f"Hi {name}", body, cta_url, "Open Hireschema", app_base=app_base
    )
