#!/usr/bin/env python3
"""
Push token_hash email templates to the linked Supabase cloud project.

The default {{ .ConfirmationURL }} sends users to supabase.co/auth/v1/verify with
a PKCE token that only works in the same browser session. Our templates link
directly to /auth/callback?token_hash=… so links work from incognito / temp mail.

Usage (from repo root):
  python3 scripts/patch_supabase_email_templates.py

Requires: supabase CLI logged in (`supabase login`) and project linked.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = ROOT / "supabase" / "config.toml"
    confirmation = ROOT / "supabase" / "templates" / "confirmation.html"
    magic_link = ROOT / "supabase" / "templates" / "magic_link.html"

    for path in (config, confirmation, magic_link):
        if not path.exists():
            print(f"Missing {path}", file=sys.stderr)
            return 1

    print("Pushing auth email templates to linked Supabase project…")
    result = subprocess.run(
        ["supabase", "config", "push", "--yes"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        print(
            "\nIf config push failed, paste templates manually in Supabase Dashboard → "
            "Authentication → Email Templates:\n"
            "  • Confirm signup → supabase/templates/confirmation.html\n"
            "  • Magic link → supabase/templates/magic_link.html",
            file=sys.stderr,
        )
        return result.returncode

    print("Done. Request a NEW sign-in email — old links still use the broken PKCE URL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
