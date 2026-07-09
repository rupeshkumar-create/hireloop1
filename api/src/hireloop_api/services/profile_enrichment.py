"""
Profile expansion from public URLs (GitHub, portfolio).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_GITHUB_USER_RE = re.compile(r"github\.com/([A-Za-z0-9_-]+)/?", re.IGNORECASE)


async def expand_profile_from_urls(urls: list[str]) -> dict[str, Any]:
    """Best-effort enrichment from public profile links."""
    discovered_skills: list[dict[str, str]] = []
    sources: list[dict[str, str]] = []

    async with httpx.AsyncClient(timeout=12.0) as client:
        for url in urls[:5]:
            url = (url or "").strip()
            if not url:
                continue
            gh = _GITHUB_USER_RE.search(url)
            if gh:
                user = gh.group(1)
                try:
                    repos = await client.get(
                        f"https://api.github.com/users/{user}/repos",
                        params={"sort": "updated", "per_page": 8},
                        headers={"Accept": "application/vnd.github+json"},
                    )
                    if repos.status_code == 200:
                        for repo in repos.json()[:8]:
                            lang = repo.get("language")
                            name = repo.get("name")
                            if lang:
                                discovered_skills.append(
                                    {"skill": lang, "source": f"github:{user}/{name}"}
                                )
                        sources.append({"type": "github", "url": url, "username": user})
                except Exception as exc:
                    logger.warning("github_expand_failed", error=str(exc)[:120])
                continue

            # Generic portfolio — fetch title/meta only
            if url.startswith("http"):
                try:
                    res = await client.get(url, follow_redirects=True)
                    if res.status_code < 400:
                        text = res.text[:5000].lower()
                        for kw in ("react", "python", "typescript", "aws", "kubernetes", "sql"):
                            if kw in text:
                                discovered_skills.append({"skill": kw, "source": f"portfolio:{url}"})
                        sources.append({"type": "portfolio", "url": url})
                except Exception as exc:
                    logger.warning("portfolio_expand_failed", error=str(exc)[:120])

    # Dedupe skills
    seen: set[str] = set()
    skills_out: list[dict[str, str]] = []
    for item in discovered_skills:
        sk = item["skill"].lower()
        if sk in seen:
            continue
        seen.add(sk)
        skills_out.append(item)

    return {
        "expanded_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
        "sources": sources,
        "discovered_skills": skills_out,
    }


def merge_enrichment(existing: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    base = dict(existing or {})
    for key, val in patch.items():
        if key == "discovered_skills":
            prior = base.get("discovered_skills") or []
            merged = list(prior) + [s for s in val if s not in prior]
            base["discovered_skills"] = merged[:40]
        else:
            base[key] = val
    return base
