#!/usr/bin/env python3
"""
Post-deploy smoke checks for the Hireschema API.

Usage:
  python scripts/e2e_smoke.py --base-url http://127.0.0.1:8000

Exit 0 when all checks pass; non-zero otherwise.
"""

from __future__ import annotations

import argparse
import sys

import httpx


def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Hireschema API smoke tests")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API origin (default: http://127.0.0.1:8000)",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    all_ok = True
    with httpx.Client(timeout=args.timeout) as client:
        try:
            r = client.get(f"{base}/api/v1/health")
            all_ok &= _check(
                "liveness /health",
                r.status_code == 200 and r.json().get("status") == "ok",
                f"HTTP {r.status_code}",
            )
        except Exception as exc:
            all_ok &= _check("liveness /health", False, str(exc))

        try:
            r = client.get(f"{base}/api/v1/health/ready")
            body = r.json()
            all_ok &= _check(
                "readiness /health/ready",
                r.status_code == 200 and body.get("status") == "ready",
                f"HTTP {r.status_code} checks={body.get('checks')}",
            )
        except Exception as exc:
            all_ok &= _check("readiness /health/ready", False, str(exc))

        try:
            r = client.get(f"{base}/api/openapi.json")
            all_ok &= _check(
                "openapi",
                r.status_code == 200 and "openapi" in r.json(),
                f"HTTP {r.status_code}",
            )
        except Exception as exc:
            all_ok &= _check("openapi", False, str(exc))

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
