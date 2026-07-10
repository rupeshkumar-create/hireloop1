"""Thin async client for Firecrawl v2 scrape API."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from hireloop_api.config import Settings
from hireloop_api.services.firecrawl.url_policy import validate_firecrawl_url

logger = structlog.get_logger()

_FIRECRAWL_BASE = "https://api.firecrawl.dev/v2"


class FirecrawlError(Exception):
    """Firecrawl API failure."""


class FirecrawlClient:
    def __init__(self, api_key: str, *, timeout_seconds: float = 45.0) -> None:
        self._api_key = api_key.strip()
        self._http = httpx.AsyncClient(
            base_url=_FIRECRAWL_BASE,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def scrape_markdown(
        self,
        url: str,
        *,
        only_main_content: bool = True,
        proxy: str = "auto",
    ) -> dict[str, Any]:
        """
        Scrape a single URL to markdown.

        Returns ``{"markdown": str, "metadata": dict, "source_url": str}``.
        """
        source_url = validate_firecrawl_url(url)
        payload: dict[str, Any] = {
            "url": source_url,
            "formats": ["markdown"],
            "onlyMainContent": only_main_content,
            "proxy": proxy,
        }
        try:
            resp = await self._http.post("/scrape", json=payload)
        except httpx.HTTPError as exc:
            raise FirecrawlError(f"Firecrawl request failed: {exc}") from exc

        if resp.status_code == 429:
            raise FirecrawlError("Firecrawl rate limit exceeded")
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise FirecrawlError(f"Firecrawl HTTP {resp.status_code}: {detail}")

        body = resp.json()
        if not body.get("success"):
            raise FirecrawlError(str(body.get("error") or "Firecrawl scrape failed"))

        data = body.get("data") or {}
        markdown = str(data.get("markdown") or "").strip()
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        return {
            "markdown": markdown,
            "metadata": metadata,
            "source_url": source_url,
        }


def firecrawl_enabled(settings: Settings) -> bool:
    return bool((settings.firecrawl_api_key or "").strip()) and settings.firecrawl_enabled


def client_from_settings(settings: Settings) -> FirecrawlClient | None:
    if not firecrawl_enabled(settings):
        return None
    return FirecrawlClient(settings.firecrawl_api_key)
