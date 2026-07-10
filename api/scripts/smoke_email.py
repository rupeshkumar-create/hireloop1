#!/usr/bin/env python3
"""
Smoke-test branded lifecycle email rendering + delivery (Resend).

Usage (from api/):
  uv run python scripts/smoke_email.py              # render + config only
  uv run python scripts/smoke_email.py --send       # also send one test per template
  SMOKE_TEST_EMAIL=you@example.com uv run python scripts/smoke_email.py --send

Exit 0 when all checks pass.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

import httpx

from hireloop_api.config import get_settings
from hireloop_api.services.email.brand_email import logo_url
from hireloop_api.services.email.lifecycle_templates import (
    render_first_job_found_email,
    render_intro_requested_candidate_email,
    render_notification_email,
    render_recruiter_approach_candidate_email,
    render_recruiter_intro_request_email,
    render_welcome_email,
)
from hireloop_api.services.email.notification_templates import NOTIFICATION_CATEGORIES
from hireloop_api.services.email.transactional import _html_email_configured, _send_html_email


def _mask(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "(empty)"
    if len(s) <= 6:
        return "***"
    return f"{s[:3]}…{s[-3:]}"


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def _provider_status(settings) -> dict[str, bool]:
    resend = bool((settings.resend_api_key or "").strip())
    sg_key = (settings.sendgrid_api_key or "").strip()
    sendgrid = bool(sg_key and sg_key.startswith("SG.") and len(sg_key) >= 24)
    return {"resend": resend, "sendgrid": sendgrid}


def _sample_notification_data(category: str, base: str) -> dict[str, Any]:
    common = {
        "full_name": "Smoke Tester",
        "cta_url": f"{base}/dashboard",
    }
    samples: dict[str, dict[str, Any]] = {
        "job_match_alerts": {
            **common,
            "job_title": "Senior Software Engineer",
            "company_name": "Acme Labs",
            "score_pct": 78,
        },
        "intro_updates": {
            **common,
            "status_message": "Your intro email was sent to the hiring manager.",
            "job_title": "Product Manager",
            "company_name": "Beta Corp",
            "hm_name": "Alex Morgan",
        },
        "interview_reminders": {
            **common,
            "session_label": "AI career call",
            "scheduled_label": "Tomorrow at 4:00 PM IST",
            "is_reminder": True,
        },
        "aarya_digest": {**common, "match_count": 3, "intro_count": 1, "actions_count": 7},
        "profile_views": {**common, "viewer_label": "A recruiter at Gamma Inc"},
        "application_updates": {
            **common,
            "job_title": "Data Analyst",
            "company_name": "Delta Systems",
            "status_label": "Application kit ready",
        },
        "platform_updates": {
            **common,
            "headline": "New on Hireschema",
            "body": "Smarter job matching and faster intro drafts are live.",
        },
    }
    return samples.get(category, common)


def _collect_templates(base: str) -> list[tuple[str, str, str]]:
    """Return (label, subject, html) for every lifecycle template."""
    out: list[tuple[str, str, str]] = []

    for role in ("candidate", "recruiter"):
        subject, html = render_welcome_email(role=role, full_name="Smoke Tester", app_base_url=base)
        out.append((f"welcome_{role}", subject, html))

    subject, html = render_first_job_found_email(
        full_name="Smoke Tester",
        job_title="Senior Software Engineer",
        company_name="Acme Labs",
        score_pct=82,
        app_base_url=base,
        job_id="smoke-job-id",
    )
    out.append(("first_job_found", subject, html))

    subject, html = render_intro_requested_candidate_email(
        full_name="Smoke Tester",
        job_title="Product Manager",
        company_name="Beta Corp",
        app_base_url=base,
    )
    out.append(("intro_requested_candidate", subject, html))

    subject, html = render_recruiter_intro_request_email(
        recruiter_name="Recruiter Smoke",
        candidate_name="Smoke Tester",
        job_title="Designer",
        app_base_url=base,
    )
    out.append(("recruiter_intro_request", subject, html))

    subject, html = render_recruiter_approach_candidate_email(
        candidate_name="Smoke Tester",
        recruiter_name="Morgan Lee",
        job_title="Backend Engineer",
        company_name="Gamma Inc",
        app_base_url=base,
    )
    out.append(("recruiter_approach_candidate", subject, html))

    for cat in sorted(NOTIFICATION_CATEGORIES):
        subject, html = render_notification_email(cat, _sample_notification_data(cat, base))
        out.append((f"notification_{cat}", subject, html))

    return out


async def _check_logo(base: str) -> bool:
    url = logo_url(base)
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            res = await client.get(url)
        ok = res.status_code == 200 and "svg" in (res.headers.get("content-type") or "").lower()
        return _check("logo_asset_reachable", ok, f"{url} HTTP {res.status_code}")
    except Exception as exc:
        return _check("logo_asset_reachable", False, f"{url} — {exc}")


async def _send_templates(
    settings,
    *,
    to_email: str,
    templates: list[tuple[str, str, str]],
) -> bool:
    all_ok = True
    for label, subject, html in templates:
        test_subject = f"[SMOKE] {subject}"
        sent = await _send_html_email(
            settings,
            to_email=to_email,
            subject=test_subject,
            html=html,
        )
        all_ok &= _check(f"send_{label}", sent, f"→ {_mask(to_email)}")
        await asyncio.sleep(0.35)  # gentle rate limit for Resend
    return all_ok


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Hireschema email smoke test")
    parser.add_argument("--send", action="store_true", help="Send one test email per template")
    parser.add_argument(
        "--to",
        default="",
        help="Recipient (default: SMOKE_TEST_EMAIL or RESEND_FROM_EMAIL)",
    )
    args = parser.parse_args()

    settings = get_settings()
    base = (settings.public_app_url or "https://www.hireschema.com").rstrip("/")
    providers = _provider_status(settings)

    print("Hireschema email smoke test")
    print(f"  app_base: {base}")
    print(f"  from: {settings.resend_from_name} <{settings.resend_from_email}>")
    print(
        "  providers: "
        f"resend={'yes' if providers['resend'] else 'no'} "
        f"sendgrid={'yes' if providers['sendgrid'] else 'no'}"
    )
    if providers["resend"]:
        print(f"  resend_key: {_mask(settings.resend_api_key)}")
    print()

    all_ok = True
    all_ok &= _check("html_email_configured", _html_email_configured(settings))
    all_ok &= await _check_logo(base)

    templates = _collect_templates(base)
    all_ok &= _check("template_count", len(templates) >= 12, f"{len(templates)} templates")

    for label, subject, html in templates:
        has_logo = "email-logo.svg" in html
        has_cta = "#B5FF6B" in html
        has_doctype = "<!DOCTYPE html>" in html
        ok = bool(subject.strip()) and len(html) > 200 and has_logo and has_cta and has_doctype
        all_ok &= _check(f"render_{label}", ok, subject[:60])

    if args.send:
        if not _html_email_configured(settings):
            all_ok &= _check("send_all", False, "no email provider configured")
        else:
            import os

            to_email = (
                args.to.strip()
                or os.environ.get("SMOKE_TEST_EMAIL", "").strip()
                or settings.resend_from_email
            )
            if not to_email:
                all_ok &= _check("send_all", False, "set --to or SMOKE_TEST_EMAIL")
            else:
                print()
                print(f"Sending {len(templates)} test emails to {_mask(to_email)} …")
                print()
                all_ok &= await _send_templates(settings, to_email=to_email, templates=templates)

    print()
    if all_ok:
        print("All email smoke checks passed.")
        return 0
    print("Some email smoke checks failed.")
    return 1


def main() -> None:
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
