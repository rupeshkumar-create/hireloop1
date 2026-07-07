"""
Welcome email templates — separate copy for candidates (Aarya) vs recruiters (Nitya).

Sent once per new user via Resend (or SMTP fallback) after signup bootstrap / phone verify.
"""

from __future__ import annotations

from html import escape


def _shell(heading: str, body_html: str, cta_url: str, cta_label: str) -> str:
    return f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1a1a1a">
  <p style="font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#6b7280;margin:0 0 16px">Hireschema</p>
  <h2 style="font-size:22px;margin:0 0 14px;line-height:1.3">{heading}</h2>
  {body_html}
  <p style="margin:28px 0">
    <a href="{escape(cta_url)}" style="background:#b9f84c;color:#000;text-decoration:none;padding:12px 20px;border-radius:0;border:2px solid #000;font-weight:600;display:inline-block">{escape(cta_label)}</a>
  </p>
  <p style="font-size:12px;color:#888;margin-top:24px;line-height:1.5">Hireschema — AI recruiting for India, the US &amp; the UK</p>
</div>"""


def render_welcome_email(
    *,
    role: str,
    full_name: str | None,
    app_base_url: str,
) -> tuple[str, str]:
    """Return (subject, html) for a new-user welcome email."""
    name = escape((full_name or "").strip() or "there")
    base = (app_base_url or "https://app.hireschema.com").rstrip("/")

    if role == "recruiter":
        subject = "Welcome to Hireschema — meet Nitya"
        body = (
            f"<p style='font-size:15px;line-height:1.65;margin:0 0 12px'>Hi {name},</p>"
            "<p style='font-size:15px;line-height:1.65;margin:0 0 12px'>"
            "You're set up as a <strong>hiring team</strong> on Hireschema. "
            "<strong>Nitya</strong>, your AI sourcer, helps you describe open roles in plain "
            "language, surface pre-scored candidates who opted in, and warm up intros — "
            "without cold outreach spam.</p>"
            "<ul style='padding-left:20px;margin:0;font-size:14px;line-height:1.75;color:#374151'>"
            "<li>Post roles and share public job links</li>"
            "<li>Review candidate fit scores before you reach out</li>"
            "<li>Consent-first intros — candidates approve every connection</li>"
            "</ul>"
        )
        heading = "Welcome — Nitya is ready to source"
        cta_url = f"{base}/recruiter"
        cta_label = "Open recruiter dashboard"
        return subject, _shell(heading, body, cta_url, cta_label)

    subject = "Welcome to Hireschema — meet Aarya"
    body = (
        f"<p style='font-size:15px;line-height:1.65;margin:0 0 12px'>Hi {name},</p>"
        "<p style='font-size:15px;line-height:1.65;margin:0 0 12px'>"
        "You're in. <strong>Aarya</strong>, your AI recruiter, reads your profile, "
        "finds live roles in your market, scores your fit, and can request warm intros "
        "on your behalf — with your approval every step of the way.</p>"
        "<ul style='padding-left:20px;margin:0;font-size:14px;line-height:1.75;color:#374151'>"
        "<li>Chat by text or voice — tell Aarya what you want next</li>"
        "<li>See matched roles ranked for your background</li>"
        "<li>Prepare cover letters and interview prep per role</li>"
        "</ul>"
    )
    heading = "Welcome — Aarya is on your side"
    cta_url = f"{base}/dashboard"
    cta_label = "Talk to Aarya"
    return subject, _shell(heading, body, cta_url, cta_label)
