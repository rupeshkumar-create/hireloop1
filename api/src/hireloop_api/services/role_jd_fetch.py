"""
Fetch job posting content from a public URL for recruiter role import.

Supports Greenhouse + Lever + Ashby JSON APIs, generic HTML (httpx) with
JSON-LD / Next.js embeds, and Firecrawl fallback for JS-rendered career pages.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import httpx
import structlog

from hireloop_api.services.ats.ats_source import _clean_html

if TYPE_CHECKING:
    from hireloop_api.config import Settings

logger = structlog.get_logger()

_MIN_JD_CHARS = 40

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
    # ADP and others HTML-encode "+" as &#x2B; / &#43; inside the type attr.
    r'<script[^>]+type=["\']application/ld(?:\+|&#(?:x2[bB]|43);)json["\'][^>]*>'
    r"(.*?)</script>",
    re.I | re.S,
)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_MAIN_CHUNK_RE = re.compile(
    r"<(?:main|article)[^>]*>(.*?)</(?:main|article)>",
    re.I | re.S,
)
_JD_CLASS_RE = re.compile(
    r"<(?:div|section)[^>]*(?:class|id|data-testid)=[\"'][^\"']*"
    r"(?:job[-_ ]?(?:description|details|posting)|posting-description|"
    r"description(?:-content)?|jobDescription)"
    r"[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
    re.I | re.S,
)
_GREENHOUSE_JOB_RE = re.compile(
    r"greenhouse\.io/(?:[^/]+/)?jobs/(\d+)",
    re.I,
)
_GREENHOUSE_BOARD_RE = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)",
    re.I,
)
_GREENHOUSE_EMBED_RE = re.compile(
    r"greenhouse\.io/embed/job_app",
    re.I,
)
_LEVER_JOB_RE = re.compile(
    r"jobs\.lever\.co/([^/?#]+)/([^/?#]+)",
    re.I,
)
_ASHBY_JOB_RE = re.compile(
    r"jobs\.ashbyhq\.com/([^/?#]+)/([^/?#]+)",
    re.I,
)
_LINKEDIN_HOST_RE = re.compile(r"(^|\.)linkedin\.com$", re.I)

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_NEXT_DESC_KEYS_NORM = frozenset(
    {
        "description",
        "descriptionhtml",
        "jobdescription",
        "jobdescriptionhtml",
        "content",
        "body",
        "abouttherole",
        "plaintextdescription",
    }
)

_COUNTRY_OR_VAGUE = frozenset(
    {
        "united states",
        "usa",
        "u.s.",
        "u.s.a.",
        "us",
        "india",
        "united kingdom",
        "uk",
        "great britain",
        "canada",
        "australia",
        "remote",
        "multiple locations",
        "various locations",
        "home office",
        "home office usa",
        "worldwide",
        "global",
    }
)

_TITLE_REGION_RE = re.compile(
    r"\b("
    r"US\s+East\s+Coast|US\s+West\s+Coast|East\s+Coast|West\s+Coast|"
    r"EMEA|APAC|ANZ|"
    r"New\s+York(?:\s+City)?|San\s+Francisco|Los\s+Angeles|Chicago|Boston|"
    r"Seattle|Austin|Washington(?:\s+DC)?|"
    r"Bengaluru|Bangalore|Mumbai|Hyderabad|Delhi(?:\s+NCR)?|Gurugram|Gurgaon|"
    r"Noida|Pune|Chennai|Kolkata|"
    r"London|Toronto|Singapore|Dubai|Sydney|Berlin|Amsterdam"
    r")\b",
    re.I,
)

_LOCATION_LINE_RE = re.compile(
    r"(?:^|[\n|])\s*(?:location|based\s+in|office(?:s)?(?:\s+in)?|work\s+location)"
    r"\s*[:\-]\s*([^\n|]{3,100})",
    re.I,
)

_KNOWN_CITIES: tuple[str, ...] = (
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
    "Boston",
    "Chicago",
    "Toronto",
    "Singapore",
    "Dubai",
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


def _best_html_body(raw_html: str) -> str:
    """Prefer job-description / main / article chunks over full-page chrome."""
    candidates: list[str] = []
    for pattern in (_JD_CLASS_RE, _MAIN_CHUNK_RE):
        for match in pattern.finditer(raw_html):
            text = _html_to_text(match.group(1))
            if len(text) >= _MIN_JD_CHARS:
                candidates.append(text)
    full = _html_to_text(raw_html)
    if candidates:
        return max(candidates, key=len)
    return full


def _walk_long_text_fields(node: Any, *, min_len: int = 80) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_norm = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if isinstance(value, str):
                text = _html_to_text(value) if "<" in value else re.sub(r"\s+", " ", value).strip()
                if len(text) < min_len:
                    continue
                if key_norm in _NEXT_DESC_KEYS_NORM or len(text) >= 280:
                    found.append(text)
            else:
                found.extend(_walk_long_text_fields(value, min_len=min_len))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_long_text_fields(item, min_len=min_len))
    return found


def _text_from_next_data(raw_html: str) -> str | None:
    match = _NEXT_DATA_RE.search(raw_html)
    if not match:
        return None
    raw = html.unescape(match.group(1)).strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    chunks = _walk_long_text_fields(payload)
    if not chunks:
        return None
    return max(chunks, key=len)


def _is_linkedin_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return bool(_LINKEDIN_HOST_RE.search(host))


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


def _normalize_city_label(label: str) -> str:
    text = re.sub(r"\s+", " ", (label or "").strip())
    lower = text.lower()
    if lower == "bangalore":
        return "Bengaluru"
    if lower == "gurgaon":
        return "Gurugram"
    if lower in {"new york city", "nyc"}:
        return "New York"
    if lower in {"washington dc", "washington d.c.", "washington, dc"}:
        return "Washington DC"
    # Preserve intentional region labels like "US East Coast".
    if re.search(r"\b(east|west)\s+coast\b", lower) or lower in {"emea", "apac", "anz"}:
        return re.sub(r"\bus\b", "US", text, flags=re.I)
    return text[:120]


def _is_country_or_vague(value: str | None) -> bool:
    if not value:
        return True
    return re.sub(r"\s+", " ", value.strip()).lower() in _COUNTRY_OR_VAGUE


def _geo_bucket(text: str | None) -> str | None:
    """Coarse region bucket so US titles don't accept Singapore cities."""
    t = (text or "").lower()
    if not t:
        return None
    if re.search(r"\b(singapore|malaysia|indonesia|thailand|vietnam|philippines|hong kong)\b", t):
        return "sea"
    if re.search(
        r"\b(bengaluru|bangalore|mumbai|hyderabad|delhi|gurugram|gurgaon|noida|pune|"
        r"chennai|kolkata|india)\b",
        t,
    ):
        return "in"
    if re.search(r"\b(london|manchester|birmingham|united kingdom|\buk\b)\b", t):
        return "uk"
    if re.search(
        r"\b(united states|\busa\b|\bu\.s\.a\.?\b|\bus\b|east coast|west coast|"
        r"new york|san francisco|seattle|austin|boston|chicago|florida|"
        r"california|texas|washington)\b",
        t,
    ):
        return "us"
    if re.search(r"\b(toronto|vancouver|montreal|canada)\b", t):
        return "ca"
    if re.search(r"\b(dubai|uae|abu dhabi)\b", t):
        return "mena"
    return None


def location_conflicts_with_title(title: str | None, city: str | None) -> bool:
    """True when a guessed city is in a different region than the job title."""
    title_geo = _geo_bucket(title)
    city_geo = _geo_bucket(city)
    return bool(title_geo and city_geo and title_geo != city_geo)


def _clean_company_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = re.sub(
        r"\s+(careers|jobs|hiring|recruiting|job openings)\s*$",
        "",
        name.strip(),
        flags=re.I,
    ).strip()
    return cleaned[:120] or None


def infer_role_location(
    *,
    title: str | None,
    body: str | None,
    structured_city: str | None = None,
    structured_state: str | None = None,
) -> tuple[str | None, str | None]:
    """
    Prefer title/region and early JD location lines over whole-page city sniffing.

    Whole-page sniffing picks nav chrome (e.g. ADP's Singapore location picker).
    """
    title_s = (title or "").strip()
    body_s = (body or "").strip()
    state = structured_state

    title_match = _TITLE_REGION_RE.search(title_s)
    if title_match:
        # Title region is authoritative — don't keep a conflicting ATS state.
        return _normalize_city_label(title_match.group(1)), None

    if structured_city and not _is_country_or_vague(structured_city):
        if not location_conflicts_with_title(title_s, structured_city):
            return _normalize_city_label(structured_city), state

    head = body_s[:1800]
    line = _LOCATION_LINE_RE.search(head)
    if line:
        city, st = _location_from_value(line.group(1))
        if city and not _is_country_or_vague(city):
            if not location_conflicts_with_title(title_s, city):
                return _normalize_city_label(city), (st or state)

    if re.search(r"\bUnited\s+States\b|\bHome\s+Office\s+USA\b", head, re.I):
        if re.search(r"\beast\s+coast\b", title_s, re.I):
            return "US East Coast", state
        if re.search(r"\bwest\s+coast\b", title_s, re.I):
            return "US West Coast", state
        if structured_city and not location_conflicts_with_title(title_s, structured_city):
            if not _is_country_or_vague(structured_city):
                return _normalize_city_label(structured_city), state
        return "United States", state

    # Only sniff curated cities in the early JD text — never the full page/nav.
    for c in _KNOWN_CITIES:
        if re.search(rf"\b{re.escape(c)}\b", head[:900], re.I):
            city = _normalize_city_label(c)
            if location_conflicts_with_title(title_s, city):
                continue
            return city, state

    if structured_city and not location_conflicts_with_title(title_s, structured_city):
        return _normalize_city_label(structured_city), state
    return None, state


def _location_from_value(value: Any) -> tuple[str | None, str | None]:
    """Normalise JobPosting / ATS location blobs into city + optional region."""
    if value is None:
        return None, None
    if isinstance(value, list):
        # Prefer a concrete city over country-level placeholders in multi-location posts.
        best: tuple[str | None, str | None] = (None, None)
        for item in value:
            city, state = _location_from_value(item)
            if not city:
                continue
            if not _is_country_or_vague(city):
                return city, state
            if best[0] is None:
                best = (city, state)
        return best
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
        # "United States, Home Office USA" → keep United States (caller may refine).
        if _is_country_or_vague(city) and state and _is_country_or_vague(state):
            return city[:120], None
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
            if _is_country_or_vague(city_s) and state_s and not _is_country_or_vague(state_s):
                # Prefer region when locality is just "United States".
                return state_s[:120], None
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
    board_match = _GREENHOUSE_BOARD_RE.search(url)
    if job_match and board_match:
        return board_match.group(1), job_match.group(1)
    if _GREENHOUSE_EMBED_RE.search(url):
        qs = parse_qs(urlparse(url).query)
        board = (qs.get("for") or [None])[0]
        token = (qs.get("token") or [None])[0]
        if board and token and str(token).isdigit():
            return str(board), str(token)
    return None


def _parse_lever_url(url: str) -> tuple[str, str] | None:
    match = _LEVER_JOB_RE.search(url)
    if not match:
        return None
    return match.group(1), match.group(2)


def _parse_ashby_url(url: str) -> tuple[str, str] | None:
    match = _ASHBY_JOB_RE.search(url)
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
    if len(jd_text) < _MIN_JD_CHARS:
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
    if len(jd_text) < _MIN_JD_CHARS:
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


async def _import_ashby(
    client: httpx.AsyncClient,
    *,
    board: str,
    job_id: str,
    source_url: str,
) -> dict[str, Any]:
    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
    resp = await client.get(api_url)
    resp.raise_for_status()
    data = resp.json()
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        raise RoleImportError("Unexpected response from Ashby job board API.")
    match: dict[str, Any] | None = None
    for job in jobs:
        if not isinstance(job, dict):
            continue
        candidates = {
            str(job.get("id") or ""),
            str(job.get("jobUrl") or ""),
            str(job.get("jobPostingId") or ""),
        }
        if job_id in candidates or any(job_id in c for c in candidates if c):
            match = job
            break
    if match is None:
        # Fallback: open the public page HTML (still may be thin; caller can Firecrawl).
        raise RoleImportError("Could not find this Ashby posting on the public board.")

    title = str(match.get("title") or "").strip()
    description = match.get("descriptionHtml") or match.get("description") or ""
    content = _clean_html(description) if isinstance(description, str) else ""
    content = (content or "").strip()
    location_raw = match.get("location")
    if isinstance(location_raw, dict):
        location_name = str(location_raw.get("name") or location_raw.get("location") or "")
    else:
        location_name = str(location_raw or "")
    city, state = _location_from_value(location_name)
    is_remote = bool(match.get("isRemote")) or "remote" in location_name.lower()
    company_name = None
    if isinstance(data, dict):
        company_name = str(data.get("companyName") or data.get("name") or "").strip() or None
    company_name = company_name or _humanize_slug(board) or None
    jd_text = "\n\n".join(p for p in (title, location_name, content) if p).strip()
    if len(jd_text) < _MIN_JD_CHARS:
        raise RoleImportError(
            "Could not extract enough text from this Ashby posting.",
            warnings=["Try pasting the JD manually if the page is gated."],
        )
    return {
        "title": title or None,
        "jd_text": jd_text,
        "company_name": company_name,
        "location_city": city,
        "location_state": state,
        "remote_policy": "remote" if is_remote else None,
        "source_url": source_url,
        "source_type": "ashby",
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
            warnings=[
                "Supported: career pages, Greenhouse, Lever, Ashby, and most public JD links."
            ],
        )
    raw = resp.text[:2_000_000]
    json_ld = _parse_json_ld_job_posting(raw)
    title = (json_ld or {}).get("title") or _title_from_html(raw)
    company_name = (json_ld or {}).get("company_name") or _company_hint_from_html(raw)
    location_city = (json_ld or {}).get("location_city")
    location_state = (json_ld or {}).get("location_state")
    remote_policy = (json_ld or {}).get("remote_policy")

    body = ((json_ld or {}).get("jd_text") or "").strip()
    if not body or len(body) < _MIN_JD_CHARS:
        next_text = _text_from_next_data(raw)
        if next_text and len(next_text) >= _MIN_JD_CHARS:
            body = next_text
    if not body or len(body) < _MIN_JD_CHARS:
        body = _best_html_body(raw)
        og_desc = _OG_DESC_RE.search(raw)
        if og_desc:
            desc = html.unescape(og_desc.group(1)).strip()
            if desc and desc not in body[:200]:
                body = f"{desc}\n\n{body}" if body else desc
    if not body or len(body) < _MIN_JD_CHARS:
        if _is_linkedin_url(source_url):
            raise RoleImportError(
                "LinkedIn job pages can’t be imported automatically.",
                warnings=[
                    "Paste the job description manually, or use a public Greenhouse, "
                    "Lever, or Ashby career link."
                ],
            )
        raise RoleImportError(
            "Could not extract enough job text from this page.",
            warnings=[
                "Many modern career sites load the JD in JavaScript. "
                "We’ll retry with a deeper scrape when available — or paste the JD manually."
            ],
        )
    warnings: list[str] = []
    if len(body) > 12000:
        body = body[:12000].rsplit(" ", 1)[0] + "…"
        warnings.append("Imported text was trimmed — review before publishing.")
    location_city, location_state = infer_role_location(
        title=title if isinstance(title, str) else None,
        body=body,
        structured_city=location_city if isinstance(location_city, str) else None,
        structured_state=location_state if isinstance(location_state, str) else None,
    )
    if not remote_policy and re.search(r"\bremote\b|\bwfh\b|work from home", body, re.I):
        remote_policy = "remote"
    return {
        "title": title,
        "jd_text": body,
        "company_name": _clean_company_name(
            company_name if isinstance(company_name, str) else None
        ),
        "location_city": location_city,
        "location_state": location_state,
        "remote_policy": remote_policy,
        "source_url": source_url,
        "source_type": "html",
        "warnings": warnings,
    }


async def _import_via_firecrawl(
    url: str,
    settings: Settings,
) -> dict[str, Any] | None:
    """JS-rendered career pages — scrape markdown via Firecrawl when configured."""
    from hireloop_api.services.firecrawl.client import (
        FirecrawlError,
        client_from_settings,
        firecrawl_enabled,
    )
    from hireloop_api.services.firecrawl.url_policy import is_scrapable_job_url

    if not firecrawl_enabled(settings) or not is_scrapable_job_url(url):
        return None

    client = client_from_settings(settings)
    if client is None:
        return None
    try:
        result = await client.scrape_markdown(url, only_main_content=True, proxy="auto")
    except (FirecrawlError, ValueError) as exc:
        logger.warning("role_import_firecrawl_failed", url=url[:120], error=str(exc)[:200])
        return None
    finally:
        await client.close()

    markdown = str(result.get("markdown") or "").strip()
    if len(markdown) < _MIN_JD_CHARS:
        return None

    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    title = str(metadata.get("title") or metadata.get("ogTitle") or "").strip() or _title_from_html(
        f"<title>{metadata.get('title') or ''}</title>"
    )
    company_name = str(metadata.get("siteName") or metadata.get("ogSiteName") or "").strip() or None
    if company_name and company_name.lower() in {"careers", "jobs", "linkedin"}:
        company_name = None

    body = markdown
    warnings: list[str] = []
    if len(body) > 12000:
        body = body[:12000].rsplit(" ", 1)[0] + "…"
        warnings.append("Imported text was trimmed — review before publishing.")

    location_city, _location_state = infer_role_location(
        title=title or None,
        body=body,
    )
    remote_policy = None
    if re.search(r"\bremote\b|\bwfh\b|work from home", body, re.I):
        remote_policy = "remote"

    return {
        "title": title or None,
        "jd_text": body,
        "company_name": _clean_company_name(company_name),
        "location_city": location_city,
        "location_state": _location_state,
        "remote_policy": remote_policy,
        "source_url": url,
        "source_type": "firecrawl",
        "warnings": warnings,
    }


async def fetch_role_from_url(
    url: str,
    *,
    timeout_seconds: float = 30.0,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Fetch and normalise a job posting from a public URL.

    Returns dict with title, jd_text, optional company_name/location_*/remote_policy,
    source_url, source_type, warnings.

    When ``settings`` includes a Firecrawl API key, JS-rendered career pages that
    fail the free HTML path are retried via Firecrawl.
    """
    source_url = _validate_public_url(url)
    headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    timeout = httpx.Timeout(timeout_seconds)
    free_error: RoleImportError | None = None

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        gh = _parse_greenhouse_url(source_url)
        if gh:
            try:
                return await _import_greenhouse(
                    client, board=gh[0], job_id=gh[1], source_url=source_url
                )
            except httpx.HTTPError as exc:
                logger.warning("greenhouse_import_failed", error=str(exc)[:200])

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

        ashby = _parse_ashby_url(source_url)
        if ashby:
            try:
                return await _import_ashby(
                    client,
                    board=ashby[0],
                    job_id=ashby[1],
                    source_url=source_url,
                )
            except RoleImportError as exc:
                logger.warning("ashby_import_failed", error=str(exc)[:200])
            except httpx.HTTPError as exc:
                logger.warning("ashby_import_failed", error=str(exc)[:200])

        try:
            return await _import_html(client, source_url=source_url)
        except RoleImportError as exc:
            free_error = exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403, 429):
                free_error = RoleImportError(
                    "This site blocked automated access.",
                    warnings=[
                        "Paste the job description manually, or use a public "
                        "Greenhouse/Lever/Ashby link."
                    ],
                )
            else:
                free_error = RoleImportError(
                    f"Could not fetch URL (HTTP {exc.response.status_code}).",
                )
        except httpx.HTTPError as exc:
            logger.warning("html_import_failed", error=str(exc)[:200])
            free_error = RoleImportError(
                "Could not reach that URL — check the link and try again.",
            )

    if settings is not None and free_error is not None:
        if _is_linkedin_url(source_url):
            raise free_error
        fc = await _import_via_firecrawl(source_url, settings)
        if fc and len(str(fc.get("jd_text") or "")) >= _MIN_JD_CHARS:
            logger.info("role_import_firecrawl_ok", url=source_url[:120])
            return fc

    if free_error is not None:
        raise free_error
    raise RoleImportError("Could not extract enough job text from this page.")


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
