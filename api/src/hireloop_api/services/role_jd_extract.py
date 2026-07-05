"""
Extract structured hiring brief fields from a pasted JD (recruiter fast path).
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from hireloop_api.config import Settings

logger = structlog.get_logger()

_EXTRACT_SYSTEM = """You extract structured hiring data from an India job description.
Return ONLY valid JSON (no markdown fences):
{
  "title": "role title",
  "seniority": "junior|mid|senior|lead|manager|director|unknown",
  "years_experience_min": integer or null,
  "years_experience_max": integer or null,
  "comp_min_lpa": integer LPA (lakhs per annum) or null,
  "comp_max_lpa": integer LPA or null,
  "comp_structure": "fixed_only|fixed_plus_variable|all_in|unclear",
  "location_city": string or null,
  "location_state": string or null,
  "remote_policy": "onsite|hybrid|remote|flex|unknown",
  "must_haves": ["skill or requirement"],
  "nice_to_haves": ["..."],
  "hiring_brief": "2-3 sentence internal brief for recruiters",
  "candidate_pitch": "1-2 sentence pitch candidates see",
  "evaluation_criteria": [{"criterion": "name", "weight": integer}],
  "assumptions": ["explicit assumptions when JD is ambiguous"]
}
Weights in evaluation_criteria should sum to ~100. No calibration profiles.
Use India context (LPA, cities). If comp is missing, set comp_structure to unclear."""

ROLE_REMOTE_POLICIES = frozenset({"onsite", "hybrid", "remote", "flex"})


def parse_lpa_inr(value: int | float | str | None) -> int | None:
    """Parse LPA from numbers or strings like '₹40 LPA' / '40-50 LPA' into INR."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(float(value) * 100_000)
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace("₹", "").replace(",", "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not match:
        return None
    try:
        return int(float(match.group(1)) * 100_000)
    except (TypeError, ValueError):
        return None


def normalize_role_remote_policy(value: Any) -> str | None:
    """Map LLM / free-text remote policy to roles.remote_policy CHECK values."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "unknown":
        return None
    if text in ROLE_REMOTE_POLICIES:
        return text
    normalized = text.replace("-", "").replace("_", " ")
    if normalized in ROLE_REMOTE_POLICIES:
        return normalized
    if "remote" in normalized or "wfh" in normalized or "work from home" in normalized:
        return "remote"
    if "hybrid" in normalized:
        return "hybrid"
    if "onsite" in normalized or "on site" in normalized or "in office" in normalized:
        return "onsite"
    if "flex" in normalized:
        return "flex"
    return None


def _lpa_to_inr(lpa: int | float | str | None) -> int | None:
    return parse_lpa_inr(lpa)


def compute_role_readiness(role: dict[str, Any]) -> dict[str, Any]:
    """Title · JD · Comp · Location checklist for the brief UI."""
    has_title = bool((role.get("title") or "").strip())
    jd = (role.get("jd_text") or "").strip()
    has_jd = len(jd) >= 40
    has_comp = role.get("comp_min") is not None or role.get("comp_max") is not None
    remote = role.get("remote_policy")
    has_location = bool((role.get("location_city") or "").strip()) or remote in (
        "remote",
        "flex",
    )
    items = [
        {"key": "title", "label": "Title", "done": has_title},
        {"key": "jd", "label": "JD", "done": has_jd},
        {"key": "comp", "label": "Comp", "done": has_comp},
        {"key": "location", "label": "Location", "done": has_location},
    ]
    done_count = sum(1 for i in items if i["done"])
    return {
        "items": items,
        "done_count": done_count,
        "total": len(items),
        "ready_for_search": has_title and (has_jd or has_comp),
        "ready_to_publish": has_title and has_jd and has_comp and has_location,
    }


def _parse_jd_structured(role: dict[str, Any]) -> dict[str, Any]:
    jd_structured = role.get("jd_structured")
    if isinstance(jd_structured, str):
        try:
            jd_structured = json.loads(jd_structured)
        except (ValueError, TypeError):
            jd_structured = {}
    return jd_structured if isinstance(jd_structured, dict) else {}


def _inr_to_lpa(inr: int | None) -> int | None:
    if inr is None:
        return None
    return int(inr / 100_000)


def _role_comp_lpa(role: dict[str, Any]) -> tuple[int | None, int | None]:
    """Resolve min/max LPA from role fields, jd_structured, or JD text."""
    min_lpa = _inr_to_lpa(role.get("comp_min"))
    max_lpa = _inr_to_lpa(role.get("comp_max"))
    jd = _parse_jd_structured(role)
    if min_lpa is None:
        min_lpa = parse_lpa_inr(jd.get("comp_min_lpa"))
    if max_lpa is None:
        max_lpa = parse_lpa_inr(jd.get("comp_max_lpa"))
    if min_lpa is None and max_lpa is None:
        jd_text = (role.get("jd_text") or "").strip()
        if jd_text:
            match = re.search(r"(\d{1,2})\s*[-\u2013]\s*(\d{1,2})\s*lpa", jd_text, re.I)
            if match:
                min_lpa = int(match.group(1))
                max_lpa = int(match.group(2))
            else:
                single = re.search(r"(\d{1,2})\s*lpa", jd_text, re.I)
                if single:
                    min_lpa = int(single.group(1))
                    max_lpa = min_lpa
    if min_lpa is not None and max_lpa is None:
        max_lpa = min_lpa
    return min_lpa, max_lpa


def _comp_chips(role: dict[str, Any]) -> list[str]:
    min_lpa, max_lpa = _role_comp_lpa(role)
    if min_lpa is not None and max_lpa is not None and min_lpa != max_lpa:
        return [
            f"₹{min_lpa}–{max_lpa} LPA fixed only",
            f"₹{min_lpa}–{max_lpa} LPA + variable",
            "Fixed + variable + ESOPs",
        ]
    if min_lpa is not None:
        return [
            f"₹{min_lpa} LPA fixed only",
            f"₹{min_lpa} LPA + variable",
            "Fixed + variable + ESOPs",
        ]
    return [
        "Fixed only",
        "Fixed + variable",
        "Fixed + variable + ESOPs",
    ]


def _location_chips(role: dict[str, Any]) -> list[str]:
    city = (role.get("location_city") or "").strip()
    remote = normalize_role_remote_policy(role.get("remote_policy"))
    jd = _parse_jd_structured(role)
    if not city:
        city = (jd.get("location_city") or "").strip()
    if remote is None:
        remote = normalize_role_remote_policy(jd.get("remote_policy"))

    if city:
        if remote == "remote":
            return ["Remote only", f"Optional {city} hub", "Hybrid"]
        if remote == "hybrid":
            return [f"Hybrid in {city}", "Remote only", f"{city} onsite only"]
        if remote == "flex":
            return [f"Hybrid in {city}", "Remote only", "Flexible"]
        return [f"{city} onsite only", f"Hybrid in {city}", "Remote only"]
    if remote == "remote":
        return ["Remote only", "Hybrid", "India — any city"]
    return ["Remote only", "Hybrid", "Onsite"]


def _experience_chips(role: dict[str, Any]) -> list[str]:
    jd = _parse_jd_structured(role)
    ymin = jd.get("years_experience_min")
    ymax = jd.get("years_experience_max")
    if isinstance(ymin, (int, float)) and isinstance(ymax, (int, float)):
        return [f"{int(ymin)}–{int(ymax)} years", f"{int(ymax)}+ years", f"Min {int(ymin)} years"]
    if isinstance(ymin, (int, float)):
        y = int(ymin)
        return [f"{y}+ years", f"{y}–{y + 3} years", f"Min {y} years"]
    seniority = str(jd.get("seniority") or "").lower()
    by_seniority: dict[str, list[str]] = {
        "intern": ["0–1 years", "Freshers OK"],
        "junior": ["0–2 years", "1–3 years"],
        "mid": ["3–5 years", "5–8 years"],
        "senior": ["5–8 years", "8+ years"],
        "lead": ["8–12 years", "10+ years"],
        "manager": ["8–12 years", "10+ years"],
        "director": ["12+ years", "15+ years"],
    }
    return by_seniority.get(seniority, ["3–5 years", "5–8 years", "8+ years"])


def _must_have_chips(role: dict[str, Any]) -> list[str]:
    must = role.get("must_haves") or []
    if isinstance(must, str):
        try:
            must = json.loads(must)
        except (ValueError, TypeError):
            must = []
    chips = [f"Yes — {str(m).strip()}" for m in must[:3] if str(m).strip()]
    chips.extend(["That's correct", "Let me clarify…"])
    return chips


def suggest_chips_for_reply(
    assistant_text: str,
    role: dict[str, Any] | None = None,
) -> list[str]:
    """Quick-reply chips derived from Nitya's question and the role/JD post."""
    role = role or {}
    t = assistant_text.lower()
    chips: list[str] = []
    if any(
        w in t for w in ("lpa", "comp", "salary", "ctc", "budget", "package", "variable", "esop")
    ):
        chips.extend(_comp_chips(role))
    if any(
        w in t
        for w in (
            "location",
            "remote",
            "hybrid",
            "onsite",
            "bangalore",
            "bengaluru",
            "city",
            "office",
            "where",
        )
    ):
        chips.extend(_location_chips(role))
    if any(w in t for w in ("experience", "years", "seniority", "yoe")):
        chips.extend(_experience_chips(role))
    if any(w in t for w in ("must-have", "must have", "skill", "requirement", "qualification")):
        must_chips = _must_have_chips(role)
        if len(must_chips) > 2:
            chips.extend(must_chips)
    if not chips and "?" in assistant_text:
        chips.extend(["That's correct", "Let me clarify…"])

    seen: set[str] = set()
    out: list[str] = []
    for chip in chips:
        if chip not in seen:
            seen.add(chip)
            out.append(chip)
    return out[:6]


async def extract_role_from_jd(
    *,
    title: str,
    jd_text: str,
    settings: Settings,
) -> dict[str, Any]:
    """LLM extraction with regex fallback when OpenRouter is unavailable."""
    jd_text = (jd_text or "").strip()
    if not jd_text:
        return {
            "title": title,
            "missing_fields": ["jd"],
            "assumptions": [],
        }

    parsed: dict[str, Any] | None = None
    if settings.openrouter_api_key:
        llm = ChatOpenAI(
            model=settings.openrouter_fallback_model or settings.openrouter_primary_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.2,
            max_tokens=2048,
            default_headers={
                "HTTP-Referer": "https://app.hireloop.in",
                "X-Title": "Hireloop - Role JD Extract",
            },
        )
        try:
            resp = await llm.ainvoke(
                [
                    SystemMessage(content=_EXTRACT_SYSTEM),
                    HumanMessage(content=f"Title: {title}\n\nJD:\n{jd_text[:12000]}"),
                ]
            )
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            parsed = json.loads(raw)
        except Exception as exc:
            logger.warning("role_jd_extract_llm_failed", error=str(exc)[:200])

    if not parsed:
        parsed = _regex_fallback(title, jd_text)

    return _normalize_extraction(parsed, title, jd_text)


def _regex_fallback(title: str, jd_text: str) -> dict[str, Any]:
    comp_match = re.search(r"(\d{1,2})\s*[-\u2013]\s*(\d{1,2})\s*lpa", jd_text, re.I)
    comp_single = re.search(r"(\d{1,2})\s*lpa", jd_text, re.I)
    comp_min_lpa = (
        int(comp_match.group(1))
        if comp_match
        else (int(comp_single.group(1)) if comp_single else None)
    )
    comp_max_lpa = int(comp_match.group(2)) if comp_match else comp_min_lpa
    city = None
    for c in ("Bangalore", "Bengaluru", "Mumbai", "Hyderabad", "Delhi", "Pune", "Chennai"):
        if c.lower() in jd_text.lower():
            city = "Bengaluru" if c == "Bangalore" else c
            break
    remote = "remote" if re.search(r"\bremote\b|\bwfh\b", jd_text, re.I) else "unknown"
    return {
        "title": title,
        "comp_min_lpa": comp_min_lpa,
        "comp_max_lpa": comp_max_lpa,
        "comp_structure": "unclear",
        "location_city": city,
        "remote_policy": remote,
        "must_haves": [],
        "nice_to_haves": [],
        "hiring_brief": jd_text[:400],
        "candidate_pitch": f"Join us as {title}.",
        "evaluation_criteria": [],
        "assumptions": ["Extracted via fallback — review comp and location."],
    }


def _normalize_extraction(
    data: dict[str, Any],
    title: str,
    jd_text: str,
) -> dict[str, Any]:
    comp_min = _lpa_to_inr(data.get("comp_min_lpa"))
    comp_max = _lpa_to_inr(data.get("comp_max_lpa"))
    remote = normalize_role_remote_policy(data.get("remote_policy"))
    if remote is None and re.search(r"\bremote\b", jd_text, re.I):
        remote = "remote"

    missing: list[str] = []
    if comp_min is None and comp_max is None:
        missing.append("comp")
    if not data.get("location_city") and remote not in ("remote", "flex"):
        missing.append("location")

    jd_structured = {
        "seniority": data.get("seniority"),
        "years_experience_min": data.get("years_experience_min"),
        "years_experience_max": data.get("years_experience_max"),
        "comp_structure": data.get("comp_structure"),
    }

    return {
        "title": data.get("title") or title,
        "comp_min": comp_min,
        "comp_max": comp_max,
        "comp_min_lpa": data.get("comp_min_lpa"),
        "comp_max_lpa": data.get("comp_max_lpa"),
        "location_city": data.get("location_city"),
        "location_state": data.get("location_state"),
        "remote_policy": remote,
        "must_haves": list(data.get("must_haves") or []),
        "nice_to_haves": list(data.get("nice_to_haves") or []),
        "hiring_brief": data.get("hiring_brief") or "",
        "candidate_pitch": data.get("candidate_pitch") or "",
        "evaluation_criteria": list(data.get("evaluation_criteria") or []),
        "jd_structured": jd_structured,
        "assumptions": list(data.get("assumptions") or []),
        "missing_fields": missing,
    }


async def apply_extraction_to_role(
    db: Any,
    role_id: Any,
    extraction: dict[str, Any],
) -> None:
    """Persist extracted fields onto public.roles."""
    await db.execute(
        """
        UPDATE public.roles SET
          title = COALESCE($2, title),
          comp_min = COALESCE($3, comp_min),
          comp_max = COALESCE($4, comp_max),
          location_city = COALESCE($5, location_city),
          location_state = COALESCE($6, location_state),
          remote_policy = COALESCE($7, remote_policy),
          must_haves = COALESCE($8::jsonb, must_haves),
          nice_to_haves = COALESCE($9::jsonb, nice_to_haves),
          hiring_brief = COALESCE($10, hiring_brief),
          candidate_pitch = COALESCE($11, candidate_pitch),
          evaluation_criteria = COALESCE($12::jsonb, evaluation_criteria),
          jd_structured = COALESCE($13::jsonb, jd_structured),
          calibration_candidates = '[]'::jsonb,
          updated_at = NOW()
        WHERE id = $1::uuid
        """,
        role_id,
        extraction.get("title"),
        extraction.get("comp_min"),
        extraction.get("comp_max"),
        extraction.get("location_city"),
        extraction.get("location_state"),
        extraction.get("remote_policy"),
        json.dumps(extraction.get("must_haves") or []),
        json.dumps(extraction.get("nice_to_haves") or []),
        extraction.get("hiring_brief"),
        extraction.get("candidate_pitch"),
        json.dumps(extraction.get("evaluation_criteria") or []),
        json.dumps(extraction.get("jd_structured") or {}),
    )
