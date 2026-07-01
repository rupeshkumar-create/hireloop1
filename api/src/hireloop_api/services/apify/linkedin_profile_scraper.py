"""
Apify LinkedIn profile scraper — no-cookie actor for candidate onboarding.

Default actor: dev_fusion/linkedin-profile-scraper (public /in/ URLs only).
Falls back to the legacy HM actor input shape when configured via settings.

Maps actor output → candidates.linkedin_data.apify_profile and fills scalar
columns + career_profile so profile_experience / career_intelligence work.
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

from hireloop_api.config import Settings
from hireloop_api.services.linkdapi_profile import _infer_years_experience

logger = structlog.get_logger()

_APIFY_BASE = "https://api.apify.com/v2"
_POLL_INTERVAL = 8
_TIMEOUT = 300
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")

DEFAULT_LINKEDIN_PROFILE_ACTOR = "dev_fusion/linkedin-profile-scraper"
_LEGACY_PROFILE_ACTOR = "2SyF0bVxmgGr8IVCZ"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_actor_input(actor: str, profile_url: str) -> dict[str, Any]:
    """Actor-specific run input (no LinkedIn cookies — R16)."""
    if actor.endswith(
        (
            "dev_fusion/linkedin-profile-scraper",
            "dev_fusion~linkedin-profile-scraper",
        )
    ):
        return {"profileUrls": [profile_url]}
    return {
        "startUrls": [{"url": profile_url}],
        "scrapeType": "profile",
    }


def _year_from_value(value: Any) -> int | None:
    if isinstance(value, int) and 1900 <= value <= 2100:
        return value
    text = _clean(value)
    if not text:
        return None
    years = [int(y) for y in _YEAR_RE.findall(text) if 1900 <= int(y) <= 2100]
    return min(years) if years else None


def _map_experience_item(item: dict[str, Any]) -> dict[str, Any] | None:
    title = _clean(
        item.get("title")
        or item.get("jobTitle")
        or item.get("position")
        or item.get("role")
    )
    company = _clean(
        item.get("companyName")
        or item.get("company")
        or item.get("organization")
        or item.get("organizationName")
    )
    if not (title or company):
        return None
    start = _clean(
        item.get("jobStartedOn")
        or item.get("startDate")
        or item.get("starts_at")
        or item.get("start")
    )
    end = _clean(
        item.get("jobEndedOn")
        or item.get("endDate")
        or item.get("ends_at")
        or item.get("end")
    )
    still = item.get("jobStillWorking")
    is_current = bool(still) if still is not None else not end
    return {
        "title": title,
        "company": company,
        "location": _clean(item.get("jobLocation") or item.get("location")),
        "industry": _clean(item.get("companyIndustry") or item.get("industry")),
        "description": _clean(item.get("jobDescription") or item.get("description")),
        "start_date": start,
        "end_date": None if is_current else end,
        "is_current": is_current,
        "employment_type": _clean(item.get("employmentType")),
        "seniority": _clean(item.get("seniority")),
    }


def _map_education_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "schoolName": _clean(
            item.get("schoolName")
            or item.get("school")
            or item.get("institution")
            or item.get("institutionName")
            or item.get("name")
        ),
        "degreeName": _clean(item.get("degreeName") or item.get("degree")),
        "fieldOfStudy": _clean(
            item.get("fieldOfStudy") or item.get("field_of_study") or item.get("field")
        ),
        "startDate": _clean(item.get("startDate") or item.get("starts_at") or item.get("start")),
        "endDate": _clean(item.get("endDate") or item.get("ends_at") or item.get("end")),
        "grade": _clean(item.get("grade") or item.get("gpa")),
    }


def _map_skill_item(item: Any) -> str | None:
    if isinstance(item, str):
        return _clean(item)
    if isinstance(item, dict):
        return _clean(item.get("title") or item.get("name") or item.get("skill"))
    return None


def normalize_apify_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize variant Apify actor shapes into apify_profile consumed by
    profile_experience, career_intelligence, and the profile UI.
    """
    experiences: list[dict[str, Any]] = []
    seen_exp: set[str] = set()
    for key in ("experiences", "positions", "employmentHistory", "experience"):
        raw_list = raw.get(key)
        if not isinstance(raw_list, list):
            continue
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            mapped = _map_experience_item(item)
            if not mapped:
                continue
            dedupe = f"{mapped.get('title','')}|{mapped.get('company','')}".casefold()
            if dedupe in seen_exp:
                continue
            seen_exp.add(dedupe)
            experiences.append(mapped)

    if not experiences and raw.get("jobTitle"):
        single = _map_experience_item(raw)
        if single:
            experiences.append(single)

    educations: list[dict[str, Any]] = []
    for key in ("educations", "education", "schools", "educationHistory"):
        raw_list = raw.get(key)
        if not isinstance(raw_list, list):
            continue
        for item in raw_list:
            if isinstance(item, dict):
                educations.append(_map_education_item(item))

    skills: list[str] = []
    for item in raw.get("skills") or []:
        skill = _map_skill_item(item)
        if skill and skill not in skills:
            skills.append(skill)

    full_name = _clean(raw.get("fullName") or raw.get("name"))
    if not full_name:
        first = _clean(raw.get("firstName"))
        last = _clean(raw.get("lastName"))
        if first or last:
            full_name = " ".join(part for part in (first, last) if part)

    current = experiences[0] if experiences else {}
    location = _clean(
        raw.get("location")
        or raw.get("addressWithCountry")
        or raw.get("geoLocationName")
        or current.get("location")
    )

    return {
        "fullName": full_name,
        "name": full_name,
        "headline": _clean(raw.get("headline") or raw.get("tagline")),
        "summary": _clean(raw.get("summary") or raw.get("about") or raw.get("description")),
        "location": location,
        "currentCompany": _clean(
            raw.get("currentCompany") or raw.get("companyName") or current.get("company")
        ),
        "currentTitle": _clean(
            raw.get("currentTitle") or raw.get("jobTitle") or current.get("title")
        ),
        "experiences": experiences,
        "positions": experiences,
        "currentPositions": [current] if current else [],
        "education": educations,
        "educations": educations,
        "schools": educations,
        "skills": skills,
        "profileUrl": _clean(
            raw.get("linkedinUrl") or raw.get("linkedinPublicUrl") or raw.get("profileUrl")
        ),
        "linkedin_parser_metadata": {
            "source": "apify",
            "normalized_at": datetime.now(UTC).isoformat(),
            "experience_count": len(experiences),
            "education_count": len(educations),
            "skill_count": len(skills),
        },
    }


def _parse_location(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if parts and parts[-1].casefold() == "india":
        parts = parts[:-1]
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


async def _run_actor(
    apify_token: str,
    actor: str,
    run_input: dict[str, Any],
) -> list[dict[str, Any]]:
    actor_id = actor.replace("/", "~")
    http = httpx.AsyncClient(timeout=60.0)
    try:
        trigger = await http.post(
            f"{_APIFY_BASE}/acts/{actor_id}/runs",
            params={"token": apify_token},
            json=run_input,
            timeout=30.0,
        )
        trigger.raise_for_status()
        run_id = trigger.json()["data"]["id"]

        elapsed = 0
        while elapsed < _TIMEOUT:
            await asyncio.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            status_res = await http.get(
                f"{_APIFY_BASE}/actor-runs/{run_id}",
                params={"token": apify_token},
                timeout=30.0,
            )
            status_res.raise_for_status()
            run_data = status_res.json()["data"]
            status = run_data["status"]
            if status == "SUCCEEDED":
                dataset_id = run_data["defaultDatasetId"]
                items_res = await http.get(
                    f"{_APIFY_BASE}/datasets/{dataset_id}/items",
                    params={"token": apify_token, "format": "json"},
                    timeout=60.0,
                )
                items_res.raise_for_status()
                payload = items_res.json()
                return payload if isinstance(payload, list) else []
            if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
                logger.warning("apify_profile_actor_failed", actor=actor, status=status)
                return []
        logger.warning("apify_profile_actor_timeout", actor=actor, run_id=run_id)
        return []
    except Exception as exc:
        logger.warning("apify_profile_run_error", actor=actor, error=str(exc)[:300])
        return []
    finally:
        await http.aclose()


async def scrape_linkedin_profile(
    *,
    apify_token: str,
    profile_url: str,
    actor: str = DEFAULT_LINKEDIN_PROFILE_ACTOR,
) -> dict[str, Any] | None:
    """Run Apify actor for one profile URL; return normalized apify_profile or None."""
    if not apify_token:
        return None
    items = await _run_actor(
        apify_token,
        actor,
        build_actor_input(actor, profile_url),
    )
    if not items:
        return None
    raw = items[0]
    if not isinstance(raw, dict):
        return None
    if raw.get("succeeded") is False or raw.get("error"):
        logger.info(
            "apify_profile_item_failed",
            error=str(raw.get("error") or "unknown")[:200],
        )
        return None
    profile = normalize_apify_profile(raw)
    if not (
        profile.get("headline")
        or profile.get("experiences")
        or profile.get("education")
        or profile.get("skills")
    ):
        return None
    return profile


async def enrich_candidate_via_apify(
    db: asyncpg.Connection,
    *,
    user_id: str,
    profile_url: str,
    settings: Settings,
) -> dict[str, Any]:
    """Scrape via Apify and persist apify_profile + candidate columns. Best-effort."""
    token = settings.apify_token
    if not token:
        return {"status": "skipped", "reason": "apify_token_missing"}

    actor = settings.apify_linkedin_profile_actor or DEFAULT_LINKEDIN_PROFILE_ACTOR
    apify_profile = await scrape_linkedin_profile(
        apify_token=token,
        profile_url=profile_url,
        actor=actor,
    )
    if not apify_profile:
        await db.execute(
            """
            UPDATE public.candidates
            SET linkedin_data = COALESCE(linkedin_data, '{}'::jsonb) || $2::jsonb,
                updated_at = NOW()
            WHERE user_id = $1::uuid AND deleted_at IS NULL
            """,
            uuid.UUID(str(user_id)),
            json.dumps(
                {
                    "apify_scrape_status": "empty",
                    "apify_scraped_at": datetime.now(UTC).isoformat(),
                }
            ),
        )
        return {"status": "empty", "actor": actor}

    uid = uuid.UUID(str(user_id))
    row = await db.fetchrow(
        """
        SELECT id, headline, summary, current_title, current_company,
               location_city, location_state, skills, years_experience, career_profile
        FROM public.candidates
        WHERE user_id = $1::uuid AND deleted_at IS NULL
        """,
        uid,
    )
    if not row:
        return {"status": "skipped", "reason": "no_candidate"}

    def _fill(existing: Any, incoming: str | None) -> Any:
        cur = _clean(existing)
        if cur and cur.lower() != "new candidate":
            return existing
        return incoming or existing

    roles = apify_profile.get("experiences") or []
    city, state = _parse_location(apify_profile.get("location"))
    new_headline = _fill(row["headline"], apify_profile.get("headline"))
    new_summary = _fill(row["summary"], apify_profile.get("summary"))
    new_title = _fill(row["current_title"], apify_profile.get("currentTitle"))
    new_company = _fill(row["current_company"], apify_profile.get("currentCompany"))
    new_city = _fill(row["location_city"], city)
    new_state = _fill(row["location_state"], state)
    existing_skills = list(row["skills"] or [])
    scraped_skills = [str(s) for s in (apify_profile.get("skills") or []) if str(s).strip()]
    new_skills = existing_skills if existing_skills else scraped_skills
    inferred_years = _infer_years_experience(roles)
    existing_years = row["years_experience"]
    new_years = (
        existing_years
        if existing_years is not None and int(existing_years) > 0
        else inferred_years
    )

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

    education = apify_profile.get("education") or []
    if education:
        creds = cp.get("education_credentials")
        if not isinstance(creds, dict):
            creds = {}
        if not isinstance(creds.get("education"), list) or not creds["education"]:
            creds["education"] = education
            cp["education_credentials"] = creds

    linkedin_blob = {
        "apify_profile": apify_profile,
        "apify_scrape_status": "ok",
        "apify_scraped_at": datetime.now(UTC).isoformat(),
        "apify_actor": actor,
    }

    full_name = apify_profile.get("fullName")
    if full_name:
        await db.execute(
            """
            UPDATE public.users
            SET full_name = COALESCE(NULLIF(TRIM(full_name), ''), $2), updated_at = NOW()
            WHERE id = $1::uuid AND deleted_at IS NULL
            """,
            uid,
            full_name,
        )

    await db.execute(
        """
        UPDATE public.candidates SET
          headline = $2,
          summary = COALESCE($3, summary),
          current_title = $4,
          current_company = $5,
          location_city = $6,
          location_state = $7,
          years_experience = COALESCE($8, years_experience),
          skills = CASE WHEN cardinality($9::text[]) > 0 THEN $9::text[] ELSE skills END,
          career_profile = $10::jsonb,
          linkedin_url = COALESCE(linkedin_url, $11),
          linkedin_data = COALESCE(linkedin_data, '{}'::jsonb) || $12::jsonb,
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
        new_years,
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
        "source": "apify",
        "actor": actor,
        "roles": len(roles),
        "education": len(education),
        "skills": len(scraped_skills),
        "years_experience": new_years,
    }
