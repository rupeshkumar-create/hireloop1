"""
Merge work history from resume, LinkedIn Apify, and career_profile for the profile UI.

Each role gets an ``aarya_insights`` bullet list — Aarya's read on what that stint
signals for the candidate's trajectory (deterministic; refreshed when CI runs).
"""

from __future__ import annotations

import re
from typing import Any

from hireloop_api.services.linkedin_oauth import extract_linkedin_headline


def best_linkedin_headline(linkedin_data: Any) -> str | None:
    """Prefer Apify professional headline, then LinkedIn OAuth metadata."""
    blob = linkedin_data if isinstance(linkedin_data, dict) else {}
    apify = blob.get("apify_profile") if isinstance(blob.get("apify_profile"), dict) else {}
    for raw in (apify.get("headline"), apify.get("tagline")):
        text = _clean_str(raw)
        if text and text.casefold() != "new candidate":
            return text[:220]
    return extract_linkedin_headline(blob)


def build_merged_experience(
    *,
    resume_experience: list[dict[str, Any]] | None,
    linkedin_data: Any,
    career_profile: dict[str, Any] | None,
    career_intelligence: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
    skills: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return de-duplicated roles richest-first (LinkedIn → resume → career_profile)."""
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    skill_list = [str(s) for s in (skills or []) if str(s).strip()]

    insight_map = _insights_by_role(career_intelligence)

    for item in _linkedin_experiences(linkedin_data):
        key = _role_key(item)
        if key in seen:
            continue
        seen.add(key)
        item["source"] = "linkedin"
        item["aarya_insights"] = insight_map.get(key) or _aarya_role_insights(item, skill_list)
        merged.append(item)

    for item in _normalize_resume_experience(resume_experience or []):
        key = _role_key(item)
        if key in seen:
            _merge_role_fields(merged, key, item)
            continue
        seen.add(key)
        item["source"] = item.get("source") or "resume"
        item["aarya_insights"] = insight_map.get(key) or _aarya_role_insights(item, skill_list)
        merged.append(item)

    cp_roles = ((career_profile or {}).get("experience_career_history") or {}).get("roles") or []
    for raw in cp_roles:
        if not isinstance(raw, dict):
            continue
        item = _career_profile_role(raw)
        key = _role_key(item)
        if key in seen:
            _merge_role_fields(merged, key, item)
            continue
        seen.add(key)
        item["source"] = "career_profile"
        item["aarya_insights"] = insight_map.get(key) or _aarya_role_insights(item, skill_list)
        merged.append(item)

    if not merged and candidate:
        title = _clean_str(candidate.get("current_title"))
        company = _clean_str(candidate.get("current_company"))
        if title or company:
            item = {
                "title": title,
                "company": company,
                "is_current": True,
                "source": "profile",
            }
            item["aarya_insights"] = _aarya_role_insights(item, skill_list)
            merged.append(item)

    return merged


def build_merged_education(
    *,
    resume_education: list[dict[str, Any]] | None,
    linkedin_data: Any,
    career_profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Return de-duplicated education entries, pulled from every source we persist.

    Priority (richest first): LinkedIn Apify profile → resume parse → career_profile.
    Each source is already durably stored in the DB:
      - LinkedIn  → candidates.linkedin_data.apify_profile.{education|schools}
      - Resume/CV → resumes.parsed_data.education
      - Fallback  → candidates.career_profile.education_credentials.education
    This is the read-side merge so the profile shows education from CV, LinkedIn,
    OR resume — whichever (or all) the candidate provided.
    """
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: dict[str, Any], source: str) -> None:
        # Skip empty rows (no institution, degree, or field of study).
        if not (item.get("institution") or item.get("degree") or item.get("field_of_study")):
            return
        key = _education_key(item)
        for existing in merged:
            if _education_key(existing) == key:
                _merge_education_fields(existing, item)
                if source == "linkedin":
                    existing["source"] = "linkedin"
                return
        item["source"] = source
        seen.add(key)
        merged.append(item)

    for item in _linkedin_education(linkedin_data):
        _add(item, "linkedin")
    for item in _normalize_resume_education(resume_education or []):
        _add(item, "resume")
    for item in _career_profile_education(career_profile):
        _add(item, "career_profile")

    return merged


def _linkedin_education(linkedin_data: Any) -> list[dict[str, Any]]:
    blob = linkedin_data if isinstance(linkedin_data, dict) else {}
    apify = blob.get("apify_profile") if isinstance(blob.get("apify_profile"), dict) else {}
    out: list[dict[str, Any]] = []

    for key in ("education", "educations", "schools", "educationHistory"):
        raw = apify.get(key)
        if not isinstance(raw, list):
            continue
        for edu in raw:
            if not isinstance(edu, dict):
                continue
            normalized = _normalize_linkedin_education(edu)
            if (
                normalized.get("institution")
                or normalized.get("degree")
                or normalized.get("field_of_study")
            ):
                out.append(normalized)
    return out


def _normalize_linkedin_education(edu: dict[str, Any]) -> dict[str, Any]:
    institution = _clean_str(
        edu.get("schoolName")
        or edu.get("school")
        or edu.get("institutionName")
        or edu.get("institution")
        or edu.get("name")
        or edu.get("title")
    )
    degree = _clean_str(edu.get("degreeName") or edu.get("degree"))
    field = _clean_str(
        edu.get("fieldOfStudy") or edu.get("field_of_study") or edu.get("field") or edu.get("major")
    )
    start = _clean_str(edu.get("startDate") or edu.get("starts_at") or edu.get("start"))
    end = _clean_str(edu.get("endDate") or edu.get("ends_at") or edu.get("end"))
    grade = _clean_str(edu.get("grade") or edu.get("gpa"))
    return {
        "institution": institution,
        "degree": degree,
        "field_of_study": field,
        "start_date": start,
        "end_date": end,
        "grade": grade,
    }


def _normalize_resume_education(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for edu in items:
        if not isinstance(edu, dict):
            continue
        out.append(
            {
                "institution": _clean_str(edu.get("institution") or edu.get("university")),
                "degree": _clean_str(edu.get("degree")),
                "field_of_study": _clean_str(edu.get("field_of_study") or edu.get("major")),
                "start_date": _clean_str(edu.get("start_date")),
                "end_date": _clean_str(edu.get("end_date")),
                "grade": _clean_str(edu.get("grade") or edu.get("gpa")),
            }
        )
    return out


def _career_profile_education(career_profile: dict[str, Any] | None) -> list[dict[str, Any]]:
    creds = (career_profile or {}).get("education_credentials")
    rows = creds.get("education") if isinstance(creds, dict) else None
    out: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return out
    for edu in rows:
        if not isinstance(edu, dict):
            continue
        grad_year = edu.get("graduation_year")
        out.append(
            {
                "institution": _clean_str(edu.get("university") or edu.get("institution")),
                "degree": _clean_str(edu.get("degree")),
                "field_of_study": _clean_str(edu.get("major") or edu.get("field_of_study")),
                "start_date": None,
                "end_date": _clean_str(grad_year) if grad_year is not None else None,
                "grade": _clean_str(edu.get("gpa") or edu.get("grade")),
            }
        )
    return out


def _education_key(edu: dict[str, Any]) -> str:
    institution = (_clean_str(edu.get("institution")) or "").casefold()
    degree = (_clean_str(edu.get("degree")) or "").casefold()
    field = (_clean_str(edu.get("field_of_study")) or "").casefold()
    # School + degree identifies a programme; field_of_study is deliberately NOT
    # in the key so the same record from two sources (one with the major filled,
    # one without) collapses into a single entry and back-fills the gap. Only
    # when neither school nor degree is captured do we fall back to the field.
    if institution or degree:
        return f"{institution}|{degree}"
    return f"||{field}"


def _merge_education_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    for field in ("institution", "degree", "field_of_study", "start_date", "end_date", "grade"):
        if not existing.get(field) and incoming.get(field):
            existing[field] = incoming[field]


def _linkedin_experiences(linkedin_data: Any) -> list[dict[str, Any]]:
    blob = linkedin_data if isinstance(linkedin_data, dict) else {}
    apify = blob.get("apify_profile") if isinstance(blob.get("apify_profile"), dict) else {}
    out: list[dict[str, Any]] = []

    for key in (
        "experiences",
        "positions",
        "employmentHistory",
        "experience",
        "currentPositions",
    ):
        raw = apify.get(key)
        if not isinstance(raw, list):
            continue
        for pos in raw:
            if not isinstance(pos, dict):
                continue
            normalized = _normalize_linkedin_position(pos)
            if normalized.get("title") or normalized.get("company"):
                out.append(normalized)

    return out


def _normalize_linkedin_position(pos: dict[str, Any]) -> dict[str, Any]:
    title = _clean_str(
        pos.get("title") or pos.get("jobTitle") or pos.get("position") or pos.get("role")
    )
    company = _clean_str(pos.get("company") or pos.get("companyName") or pos.get("organization"))
    location = _clean_str(pos.get("location") or pos.get("geoLocation"))
    industry = _clean_str(pos.get("industry"))
    description = _clean_str(
        pos.get("description") or pos.get("summary") or pos.get("jobDescription")
    )
    start = _clean_str(pos.get("startDate") or pos.get("starts_at") or pos.get("start"))
    end = _clean_str(pos.get("endDate") or pos.get("ends_at") or pos.get("end"))
    is_current = bool(pos.get("isCurrent") or pos.get("current") or not end)

    return {
        "title": title,
        "company": company,
        "location": location,
        "industry": industry,
        "description": description,
        "start_date": start,
        "end_date": None if is_current else end,
        "is_current": is_current,
        "employment_type": _clean_str(pos.get("employmentType") or pos.get("type")),
        "seniority": _clean_str(pos.get("seniority") or pos.get("level")),
    }


def _normalize_resume_experience(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for exp in items:
        if not isinstance(exp, dict):
            continue
        out.append(
            {
                "title": _clean_str(exp.get("title")),
                "company": _clean_str(exp.get("company")),
                "location": _clean_str(exp.get("location")),
                "description": _clean_str(exp.get("description")),
                "start_date": _clean_str(exp.get("start_date")),
                "end_date": _clean_str(exp.get("end_date")),
                "is_current": bool(exp.get("is_current")),
                "source": "resume",
            }
        )
    return out


def _career_profile_role(raw: dict[str, Any]) -> dict[str, Any]:
    achievements = raw.get("achievements")
    ach_text = None
    if isinstance(achievements, list) and achievements:
        ach_text = "; ".join(str(a) for a in achievements[:3])
    elif isinstance(achievements, str):
        ach_text = achievements
    responsibilities = raw.get("responsibilities")
    resp_text = None
    if isinstance(responsibilities, list) and responsibilities:
        resp_text = " ".join(str(r) for r in responsibilities[:2])
    description = _clean_str(raw.get("description")) or ach_text or resp_text
    return {
        "title": _clean_str(raw.get("job_title") or raw.get("title")),
        "company": _clean_str(raw.get("company")),
        "industry": _clean_str(raw.get("industry")),
        "location": _clean_str(raw.get("location")),
        "description": description,
        "start_date": _clean_str(raw.get("start_date")),
        "end_date": _clean_str(raw.get("end_date")),
        "is_current": not bool(raw.get("end_date")),
        "seniority": _clean_str(raw.get("seniority_level") or raw.get("seniority")),
    }


def _insights_by_role(career_intelligence: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(career_intelligence, dict):
        return {}
    roles = (career_intelligence.get("experience") or {}).get("role_history") or []
    out: dict[str, list[str]] = {}
    for role in roles:
        if not isinstance(role, dict):
            continue
        insights = role.get("aarya_insights")
        if not isinstance(insights, list) or not insights:
            continue
        key = _role_key(role)
        out[key] = [str(i) for i in insights if str(i).strip()][:5]
    return out


def _aarya_role_insights(role: dict[str, Any], skills: list[str]) -> list[str]:
    """Deterministic Aarya bullets when CI/LLM insights aren't stored yet."""
    title = _clean_str(role.get("title")) or "this role"
    company = _clean_str(role.get("company")) or "your employer"
    industry = _clean_str(role.get("industry"))
    bullets: list[str] = []

    bullets.append(
        f"This {title} stint at {company} anchors your professional story — "
        "Aarya weights it heavily for role matching."
    )

    if industry:
        bullets.append(
            f"Industry exposure here ({industry}) shapes which sectors you can pivot into."
        )

    desc = _clean_str(role.get("description"))
    if desc:
        snippet = desc[:160].rstrip()
        if len(desc) > 160:
            snippet += "…"
        bullets.append(f"On-the-ground signal: {snippet}")

    if role.get("is_current"):
        bullets.append("Current role — your live narrative for intros and salary positioning.")

    if skills:
        sample = ", ".join(skills[:4])
        bullets.append(f"Skills in play across this period include {sample}.")

    if len(bullets) < 3:
        bullets.append(
            "Upload more detail or chat with Aarya to sharpen the story for this chapter."
        )

    return bullets[:4]


def _role_key(role: dict[str, Any]) -> str:
    title = (_clean_str(role.get("title")) or "").casefold()
    company = (_clean_str(role.get("company")) or "").casefold()
    return f"{company}|{title}"


def _merge_role_fields(merged: list[dict[str, Any]], key: str, incoming: dict[str, Any]) -> None:
    for existing in merged:
        if _role_key(existing) != key:
            continue
        for field in (
            "description",
            "location",
            "industry",
            "seniority",
            "employment_type",
            "start_date",
            "end_date",
        ):
            if not existing.get(field) and incoming.get(field):
                existing[field] = incoming[field]
        if incoming.get("source") == "linkedin":
            existing["source"] = "linkedin"
        return


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for k in ("text", "name", "title", "year", "month"):
            if k in value and value[k] is not None:
                return _clean_str(value[k])
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


_OVERVIEW_FIELDS = (
    "headline",
    "summary",
    "current_title",
    "current_company",
    "looking_for",
    "years_experience",
)

_DURATION_ONLY_RE = re.compile(
    r"^\(?\s*\d+\s*(?:year|yr|years|month|mo|months)",
    re.I,
)


def _looks_corrupt_overview_value(value: object) -> bool:
    """Detect mangled parse artifacts in overview columns."""
    if value is None:
        return True
    if isinstance(value, int | float):
        return False
    if not isinstance(value, str):
        return True
    v = value.strip()
    if not v or v.casefold() == "new candidate":
        return True
    if _DURATION_ONLY_RE.match(v):
        return True
    if re.match(r"^\(\d+\s+year", v, re.I):
        return True
    # Truncated title like "Senior C" from a bad resume parse.
    if re.fullmatch(r"senior [a-z]", v, re.I):
        return True
    if " at (" in v and "month)" in v:
        return True
    if "fashion buying fashion buying" in v.casefold():
        return True
    return False


def _current_role_from_experience(merged: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not merged:
        return None
    for role in merged:
        if role.get("is_current"):
            return role
    return merged[0]


def _parse_year_month(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    text = raw.strip()
    year_m = re.search(r"(\d{4})", text)
    if not year_m:
        return None
    year = int(year_m.group(1))
    month_m = re.search(r"-(\d{1,2})\b", text)
    month = int(month_m.group(1)) if month_m else 1
    return year, min(max(month, 1), 12)


def estimate_years_from_experience(
    merged: list[dict[str, Any]],
    *,
    fallback: int | None = None,
) -> int | None:
    """Estimate total years from role date spans, else a conservative role-count heuristic."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    total_months = 0.0
    for role in merged:
        start = _parse_year_month(_clean_str(role.get("start_date")))
        if not start:
            continue
        if role.get("is_current"):
            end = (now.year, now.month)
        else:
            parsed_end = _parse_year_month(_clean_str(role.get("end_date")))
            end = parsed_end or (now.year, now.month)
        months = (end[0] - start[0]) * 12 + (end[1] - start[1])
        if months > 0:
            total_months += months
    if total_months >= 6:
        return max(1, round(total_months / 12))
    if merged:
        return max(fallback or 0, len(merged) * 2) or None
    return fallback


def _build_summary_from_experience(
    merged: list[dict[str, Any]],
    skills: list[str] | None,
) -> str | None:
    current = _current_role_from_experience(merged)
    parts: list[str] = []
    if current:
        title = _clean_str(current.get("title"))
        company = _clean_str(current.get("company"))
        if title and company:
            parts.append(f"Currently {title} at {company}")
        elif title:
            parts.append(f"Currently {title}")

    history: list[str] = []
    for role in merged[:4]:
        title = _clean_str(role.get("title"))
        company = _clean_str(role.get("company"))
        if title and company:
            history.append(f"{title} at {company}")
        elif title:
            history.append(title)
    if len(history) > 1:
        parts.append(f"Background includes {'; '.join(history[1:])}")
    elif history and not parts:
        parts.append(history[0])

    skill_list = [str(s).strip() for s in (skills or []) if str(s).strip()][:8]
    if skill_list:
        parts.append(f"Skills: {', '.join(skill_list)}")
    if not parts:
        return None
    return ". ".join(parts) + "."


def derive_overview_from_experience(
    merged: list[dict[str, Any]],
    *,
    candidate: dict[str, Any] | None = None,
    linkedin_data: Any = None,
    skills: list[str] | None = None,
) -> dict[str, Any]:
    """Build overview fields from merged work history (richest source of truth)."""
    current = _current_role_from_experience(merged)
    current_title = _clean_str(current.get("title")) if current else None
    current_company = _clean_str(current.get("company")) if current else None

    if current_title and current_company:
        headline = f"{current_title} at {current_company}"
    elif current_title:
        headline = current_title
    else:
        headline = best_linkedin_headline(linkedin_data)

    summary = _build_summary_from_experience(merged, skills)
    years = estimate_years_from_experience(
        merged,
        fallback=(candidate or {}).get("years_experience"),
    )

    looking_for = (candidate or {}).get("looking_for")
    if _looks_corrupt_overview_value(looking_for):
        looking_for = None
    if not looking_for and current_title:
        lower = current_title.casefold()
        if "manager" in lower or "director" in lower or "head" in lower:
            looking_for = current_title
        elif "senior" not in lower:
            looking_for = f"Senior {current_title}"

    out: dict[str, Any] = {}
    if headline:
        out["headline"] = headline
    if summary:
        out["summary"] = summary
    if current_title:
        out["current_title"] = current_title
    if current_company:
        out["current_company"] = current_company
    if looking_for:
        out["looking_for"] = looking_for
    if years is not None:
        out["years_experience"] = years
    return out


def reconcile_candidate_overview(
    candidate: dict[str, Any],
    merged: list[dict[str, Any]],
    *,
    linkedin_data: Any = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Return (display_candidate, db_fixes).

    Overview columns prefer merged experience when stored values are corrupt or
    clearly out of sync with the current role in ``merged``.
    """
    if not merged:
        return dict(candidate), {}

    derived = derive_overview_from_experience(
        merged,
        candidate=candidate,
        linkedin_data=linkedin_data,
        skills=list(candidate.get("skills") or []),
    )
    current = _current_role_from_experience(merged)
    exp_title = _clean_str(current.get("title")) if current else None
    exp_company = _clean_str(current.get("company")) if current else None

    out = dict(candidate)
    fixes: dict[str, Any] = {}

    for field in _OVERVIEW_FIELDS:
        stored = candidate.get(field)
        derived_val = derived.get(field)
        if derived_val is None:
            continue

        replace = _looks_corrupt_overview_value(stored)
        if field == "headline" and exp_title and derived_val:
            replace = str(stored or "").strip().casefold() != str(derived_val).strip().casefold()
        elif not replace and field == "headline":
            replace = stored == candidate.get("full_name") or stored == "New candidate"
        if not replace and field == "current_title" and exp_title:
            replace = bool(stored) and str(stored).strip().casefold() != exp_title.casefold()
        if not replace and field == "current_company" and exp_company:
            replace = bool(stored) and str(stored).strip().casefold() != exp_company.casefold()

        if replace or (stored in (None, "") and derived_val):
            out[field] = derived_val
            if stored != derived_val:
                fixes[field] = derived_val

    return out, fixes


def enrich_ctx_from_merged_experience(ctx: dict[str, Any]) -> dict[str, Any]:
    """Overlay career-intelligence context with experience-derived overview facts."""
    merged = build_merged_experience(
        resume_experience=ctx.get("resume_work_experience"),
        linkedin_data=ctx.get("linkedin_data"),
        career_profile=ctx.get("career_profile"),
        career_intelligence=ctx.get("career_intelligence"),
        candidate=ctx,
        skills=ctx.get("skills"),
    )
    if not merged:
        return ctx

    enriched = dict(ctx)
    enriched["_merged_experience"] = merged
    reconciled, _ = reconcile_candidate_overview(
        enriched,
        merged,
        linkedin_data=ctx.get("linkedin_data"),
    )
    for field in _OVERVIEW_FIELDS:
        if field in reconciled:
            enriched[field] = reconciled[field]
    return enriched
