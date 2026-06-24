"""
LinkDAPI (linkdapi.com) — primary LinkedIn profile enrichment.

At onboarding, once we know a new candidate's LinkedIn URL we resolve it to full
profile details (overview, experience, education, skills) and pre-fill the
candidate record so the dashboard is populated before they type anything.

Flow (per linkdapi.com docs):
  GET /api/v1/profile/username-to-urn?username=<slug>   → urn
  GET /api/v1/profile/overview?username=<slug>          → headline/name/location
  GET /api/v1/profile/full-experience?urn=<urn>         → work history
  GET /api/v1/profile/education?urn=<urn>                → education
  GET /api/v1/profile/skills?urn=<urn>                   → skills

Auth: header `X-linkdapi-apikey`. The key comes from settings (.env) — never
hardcoded. All network/parse failures are non-fatal (enrichment is best-effort).

Mapped data is written so the existing read-time profile merge surfaces it:
  - candidate columns: headline, summary, current_title/company, location, skills
  - career_profile.experience_career_history.roles  (build_merged_experience)
  - career_profile.education_credentials.education   (build_merged_education)
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx
import structlog

logger = structlog.get_logger()

_TIMEOUT = 30.0
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


# ── URL / value helpers ───────────────────────────────────────────────────────


def extract_linkedin_username(url: str | None) -> str | None:
    """Pull the public identifier out of a linkedin.com/in/<slug> URL."""
    if not url:
        return None
    m = re.search(r"linkedin\.com/in/([^/?#]+)", url, re.IGNORECASE)
    if not m:
        return None
    slug = m.group(1).strip().strip("/")
    return slug or None


def _clean(value: Any) -> str | None:  # noqa: ANN401
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(d: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = _clean(d.get(k))
        if v:
            return v
    return None


def _unwrap(payload: Any) -> Any:  # noqa: ANN401
    """LinkDAPI commonly wraps the result in {success, data:{...}}; peel it."""
    if isinstance(payload, dict):
        for key in ("data", "result", "profile", "response"):
            if key in payload and isinstance(payload[key], (dict, list)):
                return payload[key]
    return payload


def _as_list(payload: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    data = _unwrap(payload)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        # Sometimes lists live under a nested key.
        for key in ("items", "elements", "education", "experience", "experiences", "skills"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _year(value: Any) -> int | None:  # noqa: ANN401
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1900 <= value <= 2100:
        return value
    if isinstance(value, dict):
        value = value.get("year") or value.get("end") or value.get("date")
    text = _clean(value)
    if not text:
        return None
    years = [int(y) for y in _YEAR_RE.findall(text) if 1900 <= int(y) <= 2100]
    return max(years) if years else None


# ── Client ──────────────────────────────────────────────────────────────────--


class LinkdAPIClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={"X-linkdapi-apikey": api_key},
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, str]) -> Any:  # noqa: ANN401
        resp = await self._http.get(f"{self._base}{path}", params=params)
        if resp.status_code != 200:
            logger.warning(
                "linkdapi_request_failed",
                path=path,
                status=resp.status_code,
                body=resp.text[:300],
            )
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    async def resolve_urn(self, username: str) -> str | None:
        data = _unwrap(await self._get("/api/v1/profile/username-to-urn", {"username": username}))
        if isinstance(data, dict):
            return _first(data, ("urn", "profileUrn", "entityUrn", "id"))
        return _clean(data)

    async def overview(self, username: str) -> dict[str, Any]:
        d = _unwrap(await self._get("/api/v1/profile/overview", {"username": username}))
        return d if isinstance(d, dict) else {}

    async def experience(self, urn: str) -> list[dict[str, Any]]:
        return _as_list(await self._get("/api/v1/profile/full-experience", {"urn": urn}))

    async def education(self, urn: str) -> list[dict[str, Any]]:
        return _as_list(await self._get("/api/v1/profile/education", {"urn": urn}))

    async def skills(self, urn: str) -> list[dict[str, Any]]:
        return _as_list(await self._get("/api/v1/profile/skills", {"urn": urn}))


# ── Mapping ─────────────────────────────────────────────────────────────────--


def _map_location(overview: dict[str, Any]) -> tuple[str | None, str | None]:
    loc = overview.get("location") or overview.get("geo") or {}
    if isinstance(loc, dict):
        city = _first(loc, ("city", "locality"))
        state = _first(loc, ("state", "region", "province"))
        return city, state
    raw = _clean(loc) or _first(overview, ("locationName", "geoLocationName"))
    if not raw:
        return None, None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if parts and parts[-1].casefold() == "india":
        parts = parts[:-1]
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


def _map_roles(experience: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roles: list[dict[str, Any]] = []
    for e in experience:
        title = _first(e, ("title", "position", "role", "jobTitle"))
        company = _first(e, ("company", "companyName", "organization", "organizationName"))
        if not (title or company):
            continue
        start = _first(e, ("startDate", "start", "from", "starts_at")) or (
            _clean((e.get("dateRange") or {}).get("start"))
            if isinstance(e.get("dateRange"), dict)
            else None
        )
        end = _first(e, ("endDate", "end", "to", "ends_at"))
        roles.append(
            {
                "title": title,
                "company": company,
                "location": _first(e, ("location", "locationName")),
                "description": _first(e, ("description", "summary")),
                "start_date": start,
                "end_date": end,
            }
        )
    return roles


def _map_education(education: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in education:
        university = _first(e, ("schoolName", "school", "institution", "institutionName", "name"))
        degree = _first(e, ("degreeName", "degree", "qualification"))
        major = _first(e, ("fieldOfStudy", "field", "fieldName", "major"))
        if not (university or degree or major):
            continue
        out.append(
            {
                "university": university,
                "degree": degree,
                "major": major,
                "graduation_year": _year(
                    e.get("endDate") or e.get("end") or e.get("dateRange") or e.get("ends_at")
                ),
                "gpa": _first(e, ("grade", "gpa")),
            }
        )
    return out


def _map_skills(skills: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in skills:
        name = _first(s, ("name", "skill", "title", "label")) if isinstance(s, dict) else _clean(s)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out[:40]


def _edu_key(edu: dict[str, Any]) -> str:
    uni = (_clean(edu.get("university")) or "").casefold()
    deg = (_clean(edu.get("degree")) or "").casefold()
    if uni or deg:
        return f"{uni}|{deg}"
    return f"||{(_clean(edu.get('major')) or '').casefold()}"


# ── Enrichment ────────────────────────────────────────────────────────────────


async def enrich_candidate_via_linkdapi(
    db: asyncpg.Connection,
    *,
    user_id: str,
    profile_url: str,
    api_key: str,
    base_url: str,
) -> dict[str, Any]:
    """
    Resolve the candidate's LinkedIn URL via LinkDAPI and pre-fill their profile.
    Best-effort: returns a status dict; never raises on network/parse issues.
    """
    username = extract_linkedin_username(profile_url)
    if not username:
        return {"status": "skipped", "reason": "no_username"}

    client = LinkdAPIClient(api_key, base_url)
    try:
        urn = await client.resolve_urn(username)
        overview = await client.overview(username)
        roles: list[dict[str, Any]] = []
        education: list[dict[str, Any]] = []
        skills: list[str] = []
        if urn:
            exp_raw, edu_raw, skl_raw = await asyncio.gather(
                client.experience(urn),
                client.education(urn),
                client.skills(urn),
                return_exceptions=True,
            )
            roles = _map_roles(exp_raw if isinstance(exp_raw, list) else [])
            education = _map_education(edu_raw if isinstance(edu_raw, list) else [])
            skills = _map_skills(skl_raw if isinstance(skl_raw, list) else [])
    except Exception as exc:  # never propagate from a best-effort enrich
        logger.warning("linkdapi_enrich_failed", user_id=str(user_id), error=str(exc))
        await client.close()
        return {"status": "error", "error": str(exc)}
    finally:
        await client.close()

    if not overview and not roles and not education:
        return {"status": "empty", "username": username}

    headline = _first(overview, ("headline", "title", "occupation"))
    summary = _first(overview, ("summary", "about", "description"))
    current = roles[0] if roles else {}
    current_title = _first(overview, ("currentTitle", "jobTitle")) or current.get("title")
    current_company = _first(overview, ("currentCompany", "companyName")) or current.get("company")
    # LinkedIn often echoes the company name into the title for founder / top-level
    # entries → a bogus "X at X". A title that merely duplicates the company is not
    # a real title (and would pollute match title-affinity), so drop it and fall
    # back to the headline if that gives something distinct.
    if (
        current_title
        and current_company
        and current_title.strip().lower() == current_company.strip().lower()
    ):
        alt = (headline or "").split(" at ")[0].strip()
        current_title = alt if alt and alt.lower() != current_company.strip().lower() else None
    city, state = _map_location(overview)

    uid = uuid.UUID(str(user_id))

    # Read the current candidate so we only fill blanks (never clobber edits).
    row = await db.fetchrow(
        """
        SELECT id, headline, summary, current_title, current_company,
               location_city, location_state, skills, career_profile
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        uid,
    )
    if not row:
        return {"status": "skipped", "reason": "no_candidate"}

    def _fill(existing: Any, incoming: str | None) -> Any:  # noqa: ANN401
        cur = _clean(existing)
        if cur and cur.lower() != "new candidate":
            return existing
        return incoming or existing

    new_headline = _fill(row["headline"], headline)
    new_summary = _fill(row["summary"], summary)
    new_title = _fill(row["current_title"], current_title)
    new_company = _fill(row["current_company"], current_company)
    new_city = _fill(row["location_city"], city)
    new_state = _fill(row["location_state"], state)
    existing_skills = list(row["skills"] or [])
    new_skills = existing_skills if existing_skills else skills

    # Merge experience + education into career_profile (fill, don't clobber).
    cp: dict[str, Any] = {}
    raw_cp = row["career_profile"]
    if isinstance(raw_cp, str):
        try:
            parsed = json.loads(raw_cp)
            cp = parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            cp = {}
    elif isinstance(raw_cp, dict):
        cp = dict(raw_cp)

    if roles:
        exp_hist = cp.get("experience_career_history")
        if not isinstance(exp_hist, dict):
            exp_hist = {}
        if not isinstance(exp_hist.get("roles"), list) or not exp_hist["roles"]:
            exp_hist["roles"] = roles
            cp["experience_career_history"] = exp_hist

    if education:
        creds = cp.get("education_credentials")
        if not isinstance(creds, dict):
            creds = {}
        existing_edu = creds.get("education") if isinstance(creds.get("education"), list) else []
        index = {_edu_key(e): e for e in existing_edu if isinstance(e, dict)}
        for edu in education:
            key = _edu_key(edu)
            if key in index:
                for f, v in edu.items():
                    if v and not index[key].get(f):
                        index[key][f] = v
            else:
                existing_edu.append(edu)
                index[key] = edu
        creds["education"] = existing_edu
        cp["education_credentials"] = creds

    linkedin_blob = {
        "linkdapi_profile": {
            "overview": overview,
            "experience": roles,
            "education": education,
            "skills": skills,
            "urn": urn,
        },
        "linkdapi_enriched_at": datetime.now(UTC).isoformat(),
    }

    await db.execute(
        """
        UPDATE public.candidates SET
          headline = $2,
          summary = COALESCE($3, summary),
          current_title = $4,
          current_company = $5,
          location_city = $6,
          location_state = $7,
          skills = CASE WHEN cardinality($8::text[]) > 0 THEN $8::text[] ELSE skills END,
          career_profile = $9::jsonb,
          linkedin_url = COALESCE(linkedin_url, $10),
          linkedin_data = COALESCE(linkedin_data, '{}'::jsonb) || $11::jsonb,
          updated_at = NOW()
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        uid,
        new_headline,
        new_summary,
        new_title,
        new_company,
        new_city,
        new_state,
        new_skills,
        json.dumps(cp),
        profile_url,
        json.dumps(linkedin_blob),
    )

    await db.execute(
        """
        INSERT INTO public.consent_log (user_id, purpose, granted)
        VALUES ($1::uuid, 'linkedin_profile_enrichment', TRUE)
        """,
        uid,
    )

    return {
        "status": "enriched",
        "username": username,
        "roles": len(roles),
        "education": len(education),
        "skills": len(skills),
    }


async def run_linkdapi_enrichment(settings: Any, user_id: str, profile_url: str) -> None:  # noqa: ANN401
    """Fire-and-forget LinkDAPI enrichment on its own pooled connection. Never raises."""
    from hireloop_api.deps import get_db_pool

    api_key = getattr(settings, "linkdapi_key", "") or ""
    if not api_key:
        return
    base_url = getattr(settings, "linkdapi_base_url", "https://linkdapi.com")
    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as db:
            result = await enrich_candidate_via_linkdapi(
                db,
                user_id=user_id,
                profile_url=profile_url,
                api_key=api_key,
                base_url=base_url,
            )
        logger.info(
            "linkdapi_enrichment_done",
            user_id=str(user_id),
            **{k: v for k, v in result.items() if k != "error"},
        )
        # Rebuild Career Intelligence AND the career path now that the profile is
        # richer — concurrently. The CI refresh is the important one: without it,
        # completeness stayed frozen at its name-only value (~23%) until some
        # OTHER path (CV upload) happened to regenerate CI, producing the
        # confusing 23%→85% jump. Now LinkedIn enrichment immediately lifts it.
        if result.get("status") == "enriched":
            from hireloop_api.services.career_intelligence import (
                run_career_intelligence_update,
            )
            from hireloop_api.services.career_path import run_career_path_update

            async with pool.acquire() as db:
                cid = await db.fetchval(
                    """
                    SELECT id FROM public.candidates
                    WHERE user_id = $1::uuid AND deleted_at IS NULL
                    """,
                    uuid.UUID(str(user_id)),
                )
            if cid:
                await asyncio.gather(
                    run_career_intelligence_update(settings, str(cid)),
                    run_career_path_update(settings, str(cid)),
                )
    except Exception as exc:  # background task — never propagate
        logger.warning("linkdapi_enrichment_bg_failed", user_id=str(user_id), error=str(exc))
