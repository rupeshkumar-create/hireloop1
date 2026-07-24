"""
Hireschema branded HTML email shell — logo, lime CTA, charcoal typography.

All product emails (Resend) should render through ``brand_shell``.
"""

from __future__ import annotations

from html import escape

# DESIGN.md tokens
LIME = "#9FE870"
CHARCOAL = "#141414"
PAPER = "#FAFAFA"
INK_MUTED = "#6B7280"
MATCH_GREEN = "#9FE870"


def default_app_base() -> str:
    return "https://www.hireschema.com"


def logo_url(app_base: str | None = None) -> str:
    base = (app_base or default_app_base()).rstrip("/")
    return f"{base}/brand/email-logo.svg"


def brand_shell(
    heading: str,
    body_html: str,
    cta_url: str,
    cta_label: str,
    *,
    app_base: str | None = None,
    preheader: str | None = None,
) -> str:
    """Client-safe HTML wrapper with logo lockup and lime primary CTA."""
    base = (app_base or default_app_base()).rstrip("/")
    logo = escape(logo_url(base))
    home = escape(base)
    pre = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0">{escape(preheader)}</div>'
        if preheader
        else ""
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{PAPER};">
{pre}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border:2px solid {CHARCOAL};">
<tr><td style="padding:28px 28px 8px 28px;">
  <a href="{home}" style="text-decoration:none;display:inline-block;">
    <img src="{logo}" width="40" height="40" alt="Hireschema" style="display:block;border:0;"/>
  </a>
  <p style="margin:12px 0 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:11px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:{INK_MUTED};">
    Hire<span style="color:{CHARCOAL};">schema</span>
  </p>
</td></tr>
<tr><td style="padding:8px 28px 28px 28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:{CHARCOAL};">
  <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;font-weight:700;">{heading}</h1>
  {body_html}
  <p style="margin:28px 0 0;">
    <a href="{escape(cta_url)}" style="background:{LIME};color:{CHARCOAL};text-decoration:none;padding:12px 22px;border:2px solid {CHARCOAL};font-weight:700;font-size:14px;display:inline-block;">
      {escape(cta_label)}
    </a>
  </p>
</td></tr>
<tr><td style="padding:0 28px 24px 28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
  <p style="margin:0;font-size:12px;line-height:1.5;color:{INK_MUTED};">
    Hireschema — AI recruiting for India
  </p>
  <p style="margin:8px 0 0;font-size:11px;line-height:1.5;color:#9CA3AF;">
    Manage email alerts in Settings → Notifications on Hireschema.
  </p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def paragraph(text: str) -> str:
    return (
        f"<p style='font-size:15px;line-height:1.65;margin:0 0 12px;color:{CHARCOAL};'>{text}</p>"
    )


def muted_paragraph(text: str) -> str:
    return (
        f"<p style='font-size:14px;line-height:1.6;margin:0 0 12px;color:{INK_MUTED};'>{text}</p>"
    )


def bullet_list(items: list[str]) -> str:
    rows = "".join(
        f"<li style='margin:4px 0;font-size:14px;line-height:1.6;color:{CHARCOAL};'>{escape(i)}</li>"
        for i in items
    )
    return f"<ul style='padding-left:20px;margin:0 0 12px;'>{rows}</ul>"
