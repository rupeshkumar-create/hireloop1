"""
Profile expansion from public URLs (GitHub, portfolio).
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from hireloop_api.config import Settings, get_settings

logger = structlog.get_logger()

_GITHUB_USER_RE = re.compile(r"github\.com/([A-Za-z0-9_-]+)/?", re.IGNORECASE)


async def _expand_portfolio_firecrawl(url: str, settings: Settings) -> list[dict[str, str]]:
    from hireloop_api.services.firecrawl.client import client_from_settings
    from hireloop_api.services.firecrawl.url_policy import validate_firecrawl_url

    client = client_from_settings(settings)
    if client is None:
        return []
    try:
        safe_url = validate_firecrawl_url(url)
        result = await client.scrape_markdown(safe_url)
    except Exception as exc:
        logger.info("firecrawl_portfolio_failed", error=str(exc)[:120])
        return []
    finally:
        await client.close()

    text = str(result.get("markdown") or "").lower()
    discovered: list[dict[str, str]] = []
    for kw in (
        "react",
        "python",
        "typescript",
        "javascript",
        "aws",
        "kubernetes",
        "sql",
        "node",
        "java",
        "go",
        "rust",
        "docker",
        "figma",
        "product management",
    ):
        if kw in text:
            discovered.append({"skill": kw, "source": f"portfolio:{url}"})
    return discovered


async def expand_profile_from_urls(
    urls: list[str],
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Best-effort enrichment from public profile links."""
    settings = settings or get_settings()
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

            if url.startswith("http"):
                fc_skills = await _expand_portfolio_firecrawl(url, settings)
                if fc_skills:
                    discovered_skills.extend(fc_skills)
                    sources.append({"type": "portfolio", "url": url, "via": "firecrawl"})
                    continue
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
