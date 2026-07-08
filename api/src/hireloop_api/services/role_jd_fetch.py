"""
Fetch job posting content from a public URL for recruiter role import.

Supports Greenhouse + Lever JSON APIs and generic HTML pages (httpx),
including JSON-LD JobPosting blocks when present.
"""

from __future__ import annotations

import html
import ipaddress
import json
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
_OG_SITE_RE = re.compile(
    r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_META_NAME_RE = re.compile(
    r'<meta[^>]+name=["\'](?:author|application-name|twitter:data1)["\'][^>]+'
    r'content=["\']([^"\']+)["\']',
    re.I,
)
_JSON_LD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
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


def _addr_is_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Block any non-public address. is_link_local covers the cloud metadata
    IP (169.254.169.254); reserved/multicast/unspecified close the rest."""
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


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
        # Literal IP in the URL — check directly.
        addr = ipaddress.ip_address(host)
        if _addr_is_blocked(addr):
            raise RoleImportError("Private network URLs cannot be imported.")
    except ValueError:
        # Hostname — resolve and block if ANY resolved address is internal.
        # Closes DNS rebinding (evil.com → 127.0.0.1 / 169.254.169.254).
        import socket

        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise RoleImportError("Could not resolve that URL.") from exc
        for info in infos:
            try:
                if _addr_is_blocked(ipaddress.ip_address(info[4][0])):
                    raise RoleImportError("Private network URLs cannot be imported.")
            except ValueError:
                continue
    return url.strip()


def _html_to_text(raw_html: str) -> str:
    without_blocks = _SCRIPT_STYLE_RE.sub(" ", raw_html)
    text = _clean_html(without_blocks) or ""
    return re.sub(r"\s+", " ", text).strip()


def _title_from_html(raw_html: str) -> str | None:
    for pattern in (_OG_TITLE_RE, _TITLE_RE, _H1_RE):
        match = pattern.search(raw_html)
        if match:
            title = _TAG_RE.sub(" ", html.unescape(match.group(1)))
            title = re.sub(r"\s+", " ", title).strip()
            if title and len(title) > 2:
                return title
    return None


def _company_hint_from_html(raw_html: str) -> str | None:
    for pattern in (_OG_SITE_RE, _META_NAME_RE):
        match = pattern.search(raw_html)
        if match:
            name = html.unescape(match.group(1)).strip()
            if name and len(name) > 1 and name.lower() not in {"careers", "jobs", "linkedin"}:
                return name[:120]
    return None


def _humanize_slug(slug: str) -> str:
    cleaned = re.sub(r"[-_]+", " ", (slug or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    return cleaned.title()


def _location_from_value(value: Any) -> tuple[str | None, str | None]:
    """Normalise JobPosting / ATS location blobs into city + optional region."""
    if value is None:
        return None, None
    if isinstance(value, list):
        for item in value:
            city, state = _location_from_value(item)
            if city:
                return city, state
        return None, None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, None
        # "Bengaluru, Karnataka, India" → city=Bengaluru, state=Karnataka
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if not parts:
            return None, None
        city = parts[0]
        state = parts[1] if len(parts) > 1 else None
        return city[:120], (state[:80] if state else None)
    if isinstance(value, dict):
        if "address" in value:
            return _location_from_value(value.get("address"))
        city = (
            value.get("addressLocality")
            or value.get("city")
            or value.get("name")
            or value.get("addressRegion")
        )
        state = value.get("addressRegion") or value.get("state")
        if isinstance(city, str) and city.strip():
            city_s = city.strip()
            # If name is already "City, Region", split it.
            if "," in city_s and not (isinstance(state, str) and state.strip()):
                return _location_from_value(city_s)
            state_s = state.strip() if isinstance(state, str) and state.strip() else None
            return city_s[:120], (state_s[:80] if state_s else None)
        return _location_from_value(value.get("addressCountry"))
    return None, None


def _org_name(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()[:120]
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()[:120]
    if isinstance(value, list):
        for item in value:
            name = _org_name(item)
            if name:
                return name
    return None


def _walk_json_ld(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_walk_json_ld(item))
        return found
    if not isinstance(node, dict):
        return found
    types = node.get("@type")
    type_list = types if isinstance(types, list) else ([types] if types else [])
    type_names = {str(t).lower() for t in type_list}
    if "jobposting" in type_names:
        found.append(node)
    graph = node.get("@graph")
    if graph is not None:
        found.extend(_walk_json_ld(graph))
    return found


def _parse_json_ld_job_posting(raw_html: str) -> dict[str, Any] | None:
    """Extract JobPosting fields from application/ld+json blocks."""
    best: dict[str, Any] | None = None
    for match in _JSON_LD_RE.finditer(raw_html):
        raw = html.unescape(match.group(1)).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        for posting in _walk_json_ld(payload):
            title = posting.get("title") or posting.get("name")
            description = posting.get("description")
            company = _org_name(
                posting.get("hiringOrganization") or posting.get("hiringOrganizationName")
            )
            city, state = _location_from_value(
                posting.get("jobLocation") or posting.get("jobLocationType")
            )
            remote_policy = None
            loc_type = str(posting.get("jobLocationType") or "").lower()
            if "telecommute" in loc_type or "remote" in loc_type:
                remote_policy = "remote"
            desc_text = ""
            if isinstance(description, str):
                desc_text = (
                    _html_to_text(description) if "<" in description else description.strip()
                )
            title_text = title.strip() if isinstance(title, str) else None
            score = (
                (2 if title_text else 0)
                + (4 if len(desc_text) >= 40 else 0)
                + (1 if company else 0)
                + (1 if city else 0)
            )
            candidate = {
                "title": title_text,
                "jd_text": desc_text or None,
                "company_name": company,
                "location_city": city,
                "location_state": state,
                "remote_policy": remote_policy,
                "_score": score,
            }
            if best is None or score > int(best.get("_score") or 0):
                best = candidate
    if best:
        best.pop("_score", None)
        return best
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
    city, state = _location_from_value(location_name)
    company_name = (data.get("company_name") or "").strip() or None
    if not company_name:
        try:
            board_meta = await _fetch_json(
                client, f"https://boards-api.greenhouse.io/v1/boards/{board}"
            )
            company_name = (board_meta.get("name") or "").strip() or None
        except Exception:
            company_name = _humanize_slug(board) or None
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
        "company_name": company_name,
        "location_city": city,
        "location_state": state,
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
    jd_text = "\n\n".join(
        p for p in ([title, description, *extra] if title else [description, *extra]) if p
    )
    jd_text = jd_text.strip()
    if len(jd_text) < 40:
        raise RoleImportError(
            "Could not extract enough text from this Lever posting.",
            warnings=["Try pasting the JD manually if the page is gated."],
        )
    location = data.get("categories", {}) if isinstance(data.get("categories"), dict) else {}
    location_raw = (location.get("location") or "").strip() or None
    city, state = _location_from_value(location_raw)
    if not city:
        team = (location.get("team") or "").strip()
        city = team or None
    workplace = (location.get("commitment") or "").lower()
    remote_policy = None
    if "remote" in workplace:
        remote_policy = "remote"
    company_name = (data.get("company") or "").strip() or _humanize_slug(company) or None
    return {
        "title": title or None,
        "jd_text": jd_text,
        "company_name": company_name,
        "location_city": city,
        "location_state": state,
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
    # Follow redirects MANUALLY, re-validating each hop — auto-follow would let
    # a public URL 302 to an internal target and bypass the pre-flight check.
    url = source_url
    resp = None
    for _hop in range(5):
        _validate_public_url(url)
        resp = await client.get(url, follow_redirects=False)
        if resp.is_redirect and resp.headers.get("location"):
            url = str(resp.url.join(resp.headers["location"]))
            continue
        break
    if resp is None:
        raise RoleImportError("Could not fetch that URL.")
    resp.raise_for_status()
    content_type = (resp.headers.get("content-type") or "").lower()
    if "html" not in content_type and not resp.text.strip().startswith("<"):
        raise RoleImportError(
            "This URL did not return an HTML job page.",
            warnings=["Supported: career pages, Greenhouse, Lever, and most public JD links."],
        )
    raw = resp.text[:2_000_000]
    json_ld = _parse_json_ld_job_posting(raw)
    title = (json_ld or {}).get("title") or _title_from_html(raw)
    company_name = (json_ld or {}).get("company_name") or _company_hint_from_html(raw)
    location_city = (json_ld or {}).get("location_city")
    location_state = (json_ld or {}).get("location_state")
    remote_policy = (json_ld or {}).get("remote_policy")

    body = ((json_ld or {}).get("jd_text") or "").strip()
    if not body or len(body) < 40:
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
    if not location_city:
        # Light regex city sniff so HTML imports still fill City when JSON-LD is absent.
        for c in (
            "Bengaluru",
            "Bangalore",
            "Mumbai",
            "Hyderabad",
            "Delhi",
            "Gurugram",
            "Gurgaon",
            "Noida",
            "Pune",
            "Chennai",
            "Kolkata",
            "London",
            "New York",
            "San Francisco",
            "Seattle",
            "Austin",
            "Toronto",
            "Singapore",
            "Dubai",
        ):
            if re.search(rf"\b{re.escape(c)}\b", body, re.I):
                location_city = (
                    "Bengaluru" if c == "Bangalore" else ("Gurugram" if c == "Gurgaon" else c)
                )
                break
    if not remote_policy and re.search(r"\bremote\b|\bwfh\b|work from home", body, re.I):
        remote_policy = "remote"
    return {
        "title": title,
        "jd_text": body,
        "company_name": company_name,
        "location_city": location_city,
        "location_state": location_state,
        "remote_policy": remote_policy,
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

    Returns dict with title, jd_text, optional company_name/location_*/remote_policy,
    source_url, source_type, warnings.
    """
    source_url = _validate_public_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; HireschemaRoleImport/1.1; +https://hireschema.com)"
        ),
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    }
    timeout = httpx.Timeout(timeout_seconds)

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        gh = _parse_greenhouse_url(source_url)
        if gh:
            try:
                return await _import_greenhouse(
                    client, board=gh[0], job_id=gh[1], source_url=source_url
                )
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
                    warnings=[
                        "Paste the job description manually, or use a public Greenhouse/Lever link."
                    ],
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
        warnings.append(
            "We imported the page text but couldn't structure all fields — Nitya can help fill gaps."
        )
        return warnings
    missing = list(extraction.get("missing_fields") or [])
    if missing:
        warnings.append(f"Still unclear: {', '.join(missing)} — Nitya will ask if needed.")
    assumptions = extraction.get("assumptions") or []
    if isinstance(assumptions, list):
        for item in assumptions[:2]:
            if item:
                warnings.append(str(item))
    return warnings
