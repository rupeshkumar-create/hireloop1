"""
Merge work history from resume, LinkedIn Apify, and career_profile for the profile UI.

Each role gets an ``aarya_insights`` bullet list — Aarya's read on what that stint
signals for the candidate's trajectory (deterministic; refreshed when CI runs).
"""

from __future__ import annotations

import re
from typing import Any

from hireloop_api.services.linkedin_oauth import extract_linkedin_headline


def best_linkedin_headline(linkedin_data: Any) -> str | None:  # noqa: ANN401
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
    linkedin_data: Any,  # noqa: ANN401
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
    linkedin_data: Any,  # noqa: ANN401
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


def _linkedin_education(linkedin_data: Any) -> list[dict[str, Any]]:  # noqa: ANN401
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


def _linkedin_experiences(linkedin_data: Any) -> list[dict[str, Any]]:  # noqa: ANN401
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
