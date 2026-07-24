"""
Chat document analysis — resume + JD fit for Aarya, resume-vs-role for Nitya.

India-only marketplace. Deterministic scoring first; optional LLM polish later.
"""

from __future__ import annotations

import re
from typing import Any

from hireloop_api.services.skills import canonical_skill

_JD_HINTS = (
    "responsibilities",
    "requirements",
    "qualifications",
    "about the role",
    "job description",
    "what you'll do",
    "what you will do",
    "must have",
    "nice to have",
    "years of experience",
    "we are hiring",
    "we're hiring",
)


def looks_like_jd(text: str) -> bool:
    """Heuristic: long paste with JD language."""
    t = (text or "").strip()
    if len(t) < 280:
        return False
    low = t.lower()
    hits = sum(1 for h in _JD_HINTS if h in low)
    return hits >= 2 or (hits >= 1 and len(t) > 600)


def _as_skills(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[,;/|]", raw)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("skill")
                if name:
                    out.append(str(name).strip())
        return out
    return []


def _lpa(rupees: int | float | None) -> float | None:
    if rupees is None:
        return None
    try:
        n = float(rupees)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n < 200:  # already LPA-ish
        return round(n, 1)
    return round(n / 100_000, 1)


def extract_jd_skills(jd_text: str) -> tuple[list[str], list[str]]:
    """Best-effort must-have / nice-to-have skill lists from freeform JD."""
    text = jd_text or ""
    low = text.lower()

    must_block = ""
    nice_block = ""
    must_m = re.search(
        r"(must[- ]haves?|required skills|requirements|qualifications)[:\s]*(.{0,800})",
        low,
        re.I | re.S,
    )
    nice_m = re.search(
        r"(nice[- ]to[- ]haves?|preferred|bonus|good to have)[:\s]*(.{0,600})",
        low,
        re.I | re.S,
    )
    if must_m:
        must_block = must_m.group(2)
    if nice_m:
        nice_block = nice_m.group(2)

    # Tokenize known tech-ish words from the whole JD as fallback.
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9+.#]{1,24}", text)
    stop = {
        "with",
        "and",
        "the",
        "for",
        "you",
        "our",
        "will",
        "have",
        "from",
        "this",
        "that",
        "role",
        "team",
        "work",
        "years",
        "experience",
        "india",
        "remote",
        "hybrid",
        "onsite",
    }
    candidates = [t for t in tokens if t.lower() not in stop and len(t) > 2]

    def _uniq(seq: list[str], limit: int = 12) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for s in seq:
            key = canonical_skill(s)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(s.strip())
            if len(out) >= limit:
                break
        return out

    must = _uniq(re.findall(r"[A-Za-z][A-Za-z0-9+.#]{1,24}", must_block) or candidates[:20])
    nice = _uniq(re.findall(r"[A-Za-z][A-Za-z0-9+.#]{1,24}", nice_block))
    nice = [s for s in nice if canonical_skill(s) not in {canonical_skill(m) for m in must}]
    return must, nice


def _seniority_band(years: int | None) -> str:
    if years is None:
        return "unknown"
    if years < 2:
        return "junior"
    if years < 5:
        return "mid"
    if years < 10:
        return "senior"
    return "lead"


def _jd_years_required(jd_text: str) -> int | None:
    m = re.search(r"(\d+)\s*\+?\s*(?:years?|yrs?)", (jd_text or "").lower())
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _location_fit(profile: dict[str, Any], jd_text: str) -> tuple[float, str]:
    jd_low = (jd_text or "").lower()
    city = (profile.get("location_city") or "").strip().lower()
    if "remote" in jd_low or "work from home" in jd_low or "wfh" in jd_low:
        return 1.0, "Role allows remote / WFH — location is flexible."
    if city and city in jd_low:
        return 1.0, f"JD mentions {profile.get('location_city')}."
    metros = (
        "bengaluru",
        "bangalore",
        "mumbai",
        "hyderabad",
        "delhi",
        "pune",
        "chennai",
        "gurugram",
        "gurgaon",
        "noida",
    )
    jd_metros = [m for m in metros if m in jd_low]
    if not jd_metros:
        return 0.7, "JD location is unclear; assuming India-wide."
    if city and any(city in m or m in city for m in jd_metros):
        return 0.95, f"City aligns with JD metros ({', '.join(jd_metros[:3])})."
    return 0.35, f"JD focuses on {', '.join(jd_metros[:3])} — confirm relocation / remote."


def analyze_resume_parsed(
    parsed: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured resume analysis for chat cards."""
    title = parsed.get("current_title") or parsed.get("headline")
    skills = _as_skills(parsed.get("skills"))
    years = parsed.get("years_experience")
    notice = parsed.get("notice_period_days")
    exp_min = _lpa(parsed.get("expected_ctc_min"))
    exp_max = _lpa(parsed.get("expected_ctc_max"))
    current_ctc = _lpa(parsed.get("current_ctc"))
    city = parsed.get("location_city")
    state = parsed.get("location_state")

    gaps: list[str] = []
    if notice is None:
        gaps.append("Notice period")
    if exp_min is None and exp_max is None:
        gaps.append("Expected CTC (LPA)")
    if not city:
        gaps.append("Preferred / current city")
    if not title:
        gaps.append("Current job title")
    if len(skills) < 5:
        gaps.append("More concrete skills (aim for 8+)")
    if years is None:
        gaps.append("Years of experience")

    strengths: list[str] = []
    if title and parsed.get("current_company"):
        strengths.append(f"Clear current role: {title} at {parsed.get('current_company')}")
    if years is not None:
        strengths.append(f"{years}+ years experience ({_seniority_band(years)} band)")
    if len(skills) >= 8:
        strengths.append(f"Solid skill coverage ({len(skills)} skills)")
    if current_ctc is not None or exp_min is not None:
        strengths.append("Compensation signals present on the CV")
    if city:
        strengths.append(f"Location listed: {city}" + (f", {state}" if state else ""))

    weak_spots: list[str] = []
    if not parsed.get("summary") and not parsed.get("headline"):
        weak_spots.append("No short professional summary / headline")
    if len(parsed.get("work_experience") or []) < 1:
        weak_spots.append("Work history looks thin — add 2–3 role bullets with impact")
    if notice is None:
        weak_spots.append("Recruiters in India expect notice period on the profile")
    if exp_min is None and exp_max is None:
        weak_spots.append("Missing expected CTC makes matching harder")

    version_compare: dict[str, Any] | None = None
    if previous:
        prev_skills = {canonical_skill(s) for s in _as_skills(previous.get("skills"))}
        curr_skills = {canonical_skill(s) for s in skills}
        added = sorted(curr_skills - prev_skills)
        removed = sorted(prev_skills - curr_skills)
        improved: list[str] = []
        if (previous.get("years_experience") or 0) < (years or 0):
            improved.append("Years of experience increased")
        if not previous.get("notice_period_days") and notice is not None:
            improved.append("Notice period added")
        if not previous.get("expected_ctc_min") and (exp_min or exp_max):
            improved.append("Expected CTC added")
        if added:
            improved.append(f"New skills: {', '.join(added[:8])}")
        version_compare = {
            "skills_added": added[:12],
            "skills_removed": removed[:12],
            "what_improved": improved or ["Profile refreshed from latest CV"],
        }

    return {
        "kind": "resume_analysis",
        "profile": {
            "full_name": parsed.get("full_name"),
            "current_title": title,
            "current_company": parsed.get("current_company"),
            "years_experience": years,
            "skills": skills[:24],
            "notice_period_days": notice,
            "expected_ctc_min_lpa": exp_min,
            "expected_ctc_max_lpa": exp_max,
            "current_ctc_lpa": current_ctc,
            "location_city": city,
            "location_state": state,
        },
        "gaps": gaps,
        "strengths": strengths
        or ["CV uploaded — fill the gaps below so Aarya can match you better"],
        "weak_spots": weak_spots,
        "version_compare": version_compare,
        "suggested_actions": [
            {"id": "find_jobs", "label": "Find matching jobs"},
            {"id": "fill_gaps", "label": "Help me fill profile gaps"},
            {"id": "career_path", "label": "Build a career path"},
        ],
    }


def analyze_jd_vs_profile(
    jd_text: str,
    profile: dict[str, Any],
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    """JD ↔ CV fit analysis for chat cards (India / INR)."""
    must, nice = extract_jd_skills(jd_text)
    cand_skills = _as_skills(profile.get("skills"))
    cand_canon = {canonical_skill(s) for s in cand_skills}

    matched_must = [s for s in must if canonical_skill(s) in cand_canon]
    missing_must = [s for s in must if canonical_skill(s) not in cand_canon]
    matched_nice = [s for s in nice if canonical_skill(s) in cand_canon]
    missing_nice = [s for s in nice if canonical_skill(s) not in cand_canon]

    skills_score = round(len(matched_must) / max(len(must), 1), 3) if must else 0.55
    years = profile.get("years_experience")
    req_years = _jd_years_required(jd_text)
    if years is None or req_years is None:
        seniority_score = 0.6
        seniority_note = "Could not compare seniority precisely."
    elif years >= req_years:
        seniority_score = 1.0
        seniority_note = f"You have {years}y vs ~{req_years}y asked."
    elif years >= max(req_years - 1, 0):
        seniority_score = 0.75
        seniority_note = f"Close: {years}y vs ~{req_years}y asked."
    else:
        seniority_score = 0.35
        seniority_note = f"JD asks ~{req_years}y; profile shows {years}y."

    # Domain: title token overlap with JD
    title = (profile.get("current_title") or profile.get("looking_for") or "").lower()
    title_tokens = set(re.findall(r"[a-z]{3,}", title))
    jd_tokens = set(re.findall(r"[a-z]{3,}", (jd_text or "").lower()))
    overlap = title_tokens & jd_tokens
    domain_score = min(1.0, 0.4 + 0.15 * len(overlap)) if title_tokens else 0.5
    domain_note = (
        f"Title overlap with JD: {', '.join(sorted(overlap)[:6])}"
        if overlap
        else "Weak title↔JD overlap — emphasise transferable domain skills."
    )

    loc_score, loc_note = _location_fit(profile, jd_text)

    overall = round(
        0.4 * skills_score + 0.25 * seniority_score + 0.2 * domain_score + 0.15 * loc_score,
        3,
    )
    overall_pct = round(overall * 100)

    if overall_pct >= 75:
        apply_rec = "yes"
        apply_reason = "Strong fit — worth applying / requesting an intro."
    elif overall_pct >= 55:
        apply_rec = "maybe"
        apply_reason = "Partial fit — tailor your CV to missing must-haves before applying."
    else:
        apply_rec = "stretch"
        apply_reason = "Stretch role — only apply if you can evidence the missing must-haves."

    # India salary band heuristic from seniority
    band = _seniority_band(years if isinstance(years, int) else None)
    salary_bands = {
        "junior": (6, 12),
        "mid": (12, 22),
        "senior": (22, 40),
        "lead": (35, 60),
        "unknown": (10, 25),
    }
    lo, hi = salary_bands[band]
    # Nudge from JD LPA mentions
    jd_lpa = re.findall(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)?\s*(\d+(?:\.\d+)?)?\s*lpa", jd_text.lower())
    if jd_lpa:
        try:
            a = float(jd_lpa[0][0])
            b = float(jd_lpa[0][1]) if jd_lpa[0][1] else a
            lo, hi = int(a), int(b)
        except ValueError:
            pass

    title_guess = profile.get("current_title") or "this role"
    tailored_bullets = [
        f"Delivered outcomes as {title_guess} using {', '.join(matched_must[:3]) or 'core skills'} relevant to this JD.",
        f"Bridged gaps toward {', '.join(missing_must[:2]) or 'role requirements'} through adjacent experience.",
        "Ready to contribute in India market timelines (notice / hybrid / metro as applicable).",
    ]
    cover_letter = (
        f"Hi Hiring Team,\n\n"
        f"I'm interested in this role. My background as {title_guess} maps well to "
        f"{', '.join(matched_must[:4]) or 'your requirements'}. "
        f"I'm focused on India opportunities and can share a tailored resume and availability on request.\n\n"
        f"Thanks,\n{(profile.get('full_name') or 'Candidate')}"
    )
    mock_questions = [
        f"Walk me through a project where you used {matched_must[0]}."
        if matched_must
        else "Walk me through a recent project you owned end-to-end.",
        "How do you prioritise when requirements are ambiguous?",
        f"This role asks for {req_years}+ years — how does your experience map?"
        if req_years
        else "How many years have you spent in this domain, and doing what?",
        "Tell me about a conflict with a stakeholder and how you resolved it.",
        "What would your first 90 days look like in this role?",
        "Which must-have from the JD are you strongest at — and weakest?",
        "Describe a metric you moved and how you measured it.",
        "Why this company / team, and why now?",
        "How do you handle production incidents / tight deadlines?",
        "What questions do you have for us?",
    ]

    return {
        "kind": "jd_fit_analysis",
        "job_id": job_id,
        "overall_score": overall_pct,
        "section_scores": {
            "skills": round(skills_score * 100),
            "seniority": round(seniority_score * 100),
            "domain": round(domain_score * 100),
            "location": round(loc_score * 100),
        },
        "section_notes": {
            "skills": f"{len(matched_must)}/{len(must)} must-haves matched"
            if must
            else "Few explicit must-haves detected",
            "seniority": seniority_note,
            "domain": domain_note,
            "location": loc_note,
        },
        "must_haves": {"matched": matched_must, "missing": missing_must},
        "nice_to_haves": {"matched": matched_nice, "missing": missing_nice},
        "missing_keywords": missing_must[:10],
        "should_apply": {"recommendation": apply_rec, "reason": apply_reason},
        "tailored_bullets": tailored_bullets,
        "cover_letter_draft": cover_letter,
        "mock_interview_questions": mock_questions,
        "salary_reality_check": {
            "currency": "INR",
            "unit": "LPA",
            "suggested_min_lpa": lo,
            "suggested_max_lpa": hi,
            "note": "India market heuristic from seniority / JD text — not an offer.",
        },
        "suggested_actions": [
            {"id": "find_similar", "label": "Find roles like this JD"},
            {"id": "prepare_kit", "label": "Prepare application kit", "requires_job_id": True},
            {"id": "request_intro", "label": "Request Intro", "requires_job_id": True},
            {"id": "save_role", "label": "Save this role", "requires_job_id": True},
            {"id": "mock_interview", "label": "Start mock interview"},
        ],
        "jd_excerpt": (jd_text or "")[:400],
    }


def analyze_resume_vs_role(
    parsed: dict[str, Any],
    role: dict[str, Any],
    *,
    skill_score: float | None = None,
    matched_skills: list[str] | None = None,
    gap_skills: list[str] | None = None,
) -> dict[str, Any]:
    """Recruiter-facing analysis of an uploaded resume against a live role."""
    must = list(role.get("must_haves") or [])
    nice = list(role.get("nice_to_haves") or [])
    jd = role.get("jd_text") or role.get("hiring_brief") or ""
    if not must and jd:
        must, nice = extract_jd_skills(str(jd))
    _ = nice

    profile = {
        "full_name": parsed.get("full_name"),
        "current_title": parsed.get("current_title") or parsed.get("headline"),
        "skills": _as_skills(parsed.get("skills")),
        "years_experience": parsed.get("years_experience"),
        "location_city": parsed.get("location_city"),
        "looking_for": role.get("title"),
    }
    fit = analyze_jd_vs_profile(str(jd or role.get("title") or ""), profile)

    # Prefer inbound skill overlap when provided
    if skill_score is not None:
        skills_pct = round(float(skill_score) * 100)
        fit["section_scores"]["skills"] = skills_pct
        base = fit["overall_score"]
        fit["overall_score"] = round(0.55 * skills_pct + 0.45 * base)
    if matched_skills is not None:
        fit["must_haves"]["matched"] = list(matched_skills)
    if gap_skills is not None:
        fit["must_haves"]["missing"] = list(gap_skills)
        fit["missing_keywords"] = list(gap_skills)[:10]

    fit["kind"] = "role_resume_analysis"
    fit["role"] = {
        "id": str(role.get("id")) if role.get("id") else None,
        "title": role.get("title"),
        "location_city": role.get("location_city"),
        "comp_min_lpa": _lpa(role.get("comp_min")),
        "comp_max_lpa": _lpa(role.get("comp_max")),
        "remote_policy": role.get("remote_policy"),
    }
    fit["candidate"] = {
        "full_name": parsed.get("full_name"),
        "current_title": profile["current_title"],
        "years_experience": parsed.get("years_experience"),
        "skills": profile["skills"][:20],
    }
    fit["bias_safe_checklist"] = [
        "Score on skills, seniority, domain, and location only",
        "Do not use name, photo, age, gender, religion, or caste signals",
        "Prefer structured must-haves over gut feel",
        "Document why/why-not for auditability",
    ]
    fit["suggested_actions"] = [
        {"id": "add_to_pipeline", "label": "Add to pipeline"},
        {"id": "request_intro", "label": "Request intro"},
        {"id": "compare", "label": "Compare with other shortlisted"},
        {"id": "draft_reject", "label": "Draft polite pass"},
    ]
    return fit
