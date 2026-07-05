"""
Fetch job posting content from a public URL for recruiter role import.

Supports Greenhouse + Lever JSON APIs and generic HTML pages (httpx).
"""

from __future__ import annotations

import html
import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from hireloop_api.services.ats.ats_source import _clean_html

logger = structlog.get_logger()

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript|svg)[^>]*>.*?</\1>",
    re.I | re.S,
)
_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_OG_DESC_RE = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_H1_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>", re.I)
_GREENHOUSE_JOB_RE = re.compile(
    r"greenhouse\.io/(?:[^/]+/)?jobs/(\d+)",
    re.I,
)
_GREENHOUSE_BOARD_RE = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)",
    re.I,
)
_LEVER_JOB_RE = re.compile(
    r"jobs\.lever\.co/([^/?#]+)/([^/?#]+)",
    re.I,
)


class RoleImportError(Exception):
    """User-facing import failure."""

    def __init__(self, message: str, *, warnings: list[str] | None = None) -> None:
        super().__init__(message)
        self.warnings = warnings or []


def _validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise RoleImportError("Only http(s) URLs are supported.")
    if not parsed.netloc:
        raise RoleImportError("Enter a valid job posting URL.")
    host = parsed.hostname or ""
    if host in ("localhost", "127.0.0.1") or host.endswith(".local"):
        raise RoleImportError("Local URLs cannot be imported.")
    if host == "0.0.0.0":  # noqa: S104
        raise RoleImportError("Local URLs cannot be imported.")
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise RoleImportError("Private network URLs cannot be imported.")
    except ValueError:
        pass
    return url.strip()


def _html_to_text(raw_html: str) -> str:
    without_blocks = _SCRIPT_STYLE_RE.sub(" ", raw_html)
    text = _clean_html(without_blocks) or ""
    return re.sub(r"\s+", " ", text).strip()


def _title_from_html(raw_html: str) -> str | None:
    for pattern in (_OG_TITLE_RE, _TITLE_RE, _H1_RE):
        match = pattern.search(raw_html)
        if match:
            title = html.unescape(match.group(1)).strip()
            if title and len(title) > 2:
                return title
    return None


def _parse_greenhouse_url(url: str) -> tuple[str, str] | None:
    job_match = _GREENHOUSE_JOB_RE.search(url)
    if not job_match:
        return None
    board_match = _GREENHOUSE_BOARD_RE.search(url)
    if not board_match:
        return None
    return board_match.group(1), job_match.group(1)


def _parse_lever_url(url: str) -> tuple[str, str] | None:
    match = _LEVER_JOB_RE.search(url)
    if not match:
        return None
    return match.group(1), match.group(2)


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    resp = await client.get(url)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RoleImportError("Unexpected response from job board API.")
    return data


async def _import_greenhouse(
    client: httpx.AsyncClient,
    *,
    board: str,
    job_id: str,
    source_url: str,
) -> dict[str, Any]:
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    data = await _fetch_json(client, api_url)
    title = (data.get("title") or "").strip()
    content = _clean_html(data.get("content")) or ""
    location = data.get("location") or {}
    location_name = location.get("name") if isinstance(location, dict) else str(location or "")
    jd_parts = [p for p in (title, location_name, content) if p]
    jd_text = "\n\n".join(jd_parts).strip()
    if len(jd_text) < 40:
        raise RoleImportError(
            "Could not extract enough text from this Greenhouse posting.",
            warnings=["Try pasting the JD manually if the page is gated."],
        )
    return {
        "title": title or None,
        "jd_text": jd_text,
        "location_city": location_name or None,
        "source_url": source_url,
        "source_type": "greenhouse",
        "warnings": [],
    }


async def _import_lever(
    client: httpx.AsyncClient,
    *,
    company: str,
    posting_id: str,
    source_url: str,
) -> dict[str, Any]:
    api_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}?mode=json"
    data = await _fetch_json(client, api_url)
    title = (data.get("text") or data.get("title") or "").strip()
    description = _clean_html(data.get("description")) or ""
    lists = data.get("lists") or []
    extra: list[str] = []
    if isinstance(lists, list):
        for block in lists:
            if not isinstance(block, dict):
                continue
            heading = (block.get("text") or "").strip()
            items = block.get("content") or ""
            body = _clean_html(items) if isinstance(items, str) else ""
            if heading or body:
                extra.append("\n".join(p for p in (heading, body) if p))
    jd_text = "\n\n".join(p for p in ([title, description, *extra] if title else [description, *extra]) if p)
    jd_text = jd_text.strip()
    if len(jd_text) < 40:
        raise RoleImportError(
            "Could not extract enough text from this Lever posting.",
            warnings=["Try pasting the JD manually if the page is gated."],
        )
    location = data.get("categories", {}) if isinstance(data.get("categories"), dict) else {}
    location_city = (location.get("location") or location.get("team") or "").strip() or None
    workplace = (location.get("commitment") or "").lower()
    remote_policy = None
    if "remote" in workplace:
        remote_policy = "remote"
    return {
        "title": title or None,
        "jd_text": jd_text,
        "location_city": location_city,
        "remote_policy": remote_policy,
        "source_url": source_url,
        "source_type": "lever",
        "warnings": [],
    }


async def _import_html(
    client: httpx.AsyncClient,
    *,
    source_url: str,
) -> dict[str, Any]:
    resp = await client.get(source_url, follow_redirects=True)
    resp.raise_for_status()
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" not in content_type and not resp.text.strip().startswith("<"):
        raise RoleImportError(
            "This URL did not return an HTML job page.",
            warnings=["Supported: career pages, Greenhouse, Lever, and most public JD links."],
        )
    raw = resp.text[:2_000_000]
    title = _title_from_html(raw)
    body = _html_to_text(raw)
    og_desc = _OG_DESC_RE.search(raw)
    if og_desc:
        desc = html.unescape(og_desc.group(1)).strip()
        if desc and desc not in body[:200]:
            body = f"{desc}\n\n{body}" if body else desc
    if not body or len(body) < 40:
        raise RoleImportError(
            "Could not extract enough job text from this page.",
            warnings=[
                "LinkedIn and some ATS pages block automated reads — paste the JD manually, "
                "or use a Greenhouse/Lever public link."
            ],
        )
    warnings: list[str] = []
    if len(body) > 12000:
        body = body[:12000].rsplit(" ", 1)[0] + "…"
        warnings.append("Imported text was trimmed — review before publishing.")
    return {
        "title": title,
        "jd_text": body,
        "source_url": source_url,
        "source_type": "html",
        "warnings": warnings,
    }


async def fetch_role_from_url(
    url: str,
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """
    Fetch and normalise a job posting from a public URL.

    Returns dict with title, jd_text, optional location_city/remote_policy,
    source_url, source_type, warnings.
    """
    source_url = _validate_public_url(url)
    headers = {
        "User-Agent": "HireloopRoleImport/1.0 (+https://hireloop.in)",
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(timeout_seconds)

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        gh = _parse_greenhouse_url(source_url)
        if gh:
            try:
                return await _import_greenhouse(client, board=gh[0], job_id=gh[1], source_url=source_url)
            except httpx.HTTPError as exc:
                logger.warning("greenhouse_import_failed", error=str(exc)[:200])
                raise RoleImportError(
                    "Could not load this Greenhouse posting.",
                    warnings=["Check the URL is public, or paste the JD manually."],
                ) from exc

        lever = _parse_lever_url(source_url)
        if lever:
            try:
                return await _import_lever(
                    client,
                    company=lever[0],
                    posting_id=lever[1],
                    source_url=source_url,
                )
            except httpx.HTTPError as exc:
                logger.warning("lever_import_failed", error=str(exc)[:200])
                raise RoleImportError(
                    "Could not load this Lever posting.",
                    warnings=["Check the URL is public, or paste the JD manually."],
                ) from exc

        try:
            return await _import_html(client, source_url=source_url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403, 429):
                raise RoleImportError(
                    "This site blocked automated access.",
                    warnings=["Paste the job description manually, or use a public Greenhouse/Lever link."],
                ) from exc
            raise RoleImportError(
                f"Could not fetch URL (HTTP {exc.response.status_code}).",
            ) from exc
        except httpx.HTTPError as exc:
            logger.warning("html_import_failed", error=str(exc)[:200])
            raise RoleImportError(
                "Could not reach that URL — check the link and try again.",
            ) from exc


def merge_import_warnings(base: dict[str, Any], extraction: dict[str, Any] | None) -> list[str]:
    warnings = list(base.get("warnings") or [])
    if not extraction:
        warnings.append("We imported the page text but couldn't structure all fields — Nitya can help fill gaps.")
        return warnings
    missing = list(extraction.get("missing_fields") or [])
    if missing:
        warnings.append(
            f"Still unclear: {', '.join(missing)} — Nitya will ask if needed."
        )
    assumptions = extraction.get("assumptions") or []
    if isinstance(assumptions, list):
        for item in assumptions[:2]:
            if item:
                warnings.append(str(item))
    return warnings
