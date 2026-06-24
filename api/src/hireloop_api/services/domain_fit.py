"""
Industry / domain fit signals for the matching engine.

Generic title overlap (e.g. both roles mention "sales") and embedding cosine
similarity can inflate scores for cross-industry matches — a B2B SaaS GTM lead
vs a hotel sales director. This module tags candidate and job blobs with coarse
domain labels and returns a multiplier (0.1–1.0) applied to the overall score.
"""

from __future__ import annotations

import re

from hireloop_api.services.titles import canonical_title_tokens

# Coarse domain markers — substring match on a normalised blob.
_HOSPITALITY = (
    "hotel",
    "hospitality",
    "resort",
    "lodging",
    "accor",
    "marriott",
    "hilton",
    "hyatt",
    "taj hotels",
    "oberoi",
    "itc hotels",
    "front office",
    "food and beverage",
    "f&b",
    "housekeeping",
    "banquet",
)

_TECH_SAAS = (
    "software",
    "saas",
    "engineer",
    "developer",
    "product manager",
    "machine learning",
    "artificial intelligence",
    "fintech",
    "startup",
    "devops",
    "full stack",
    "backend",
    "frontend",
    "data scientist",
    "platform",
    "api",
    "cloud",
)

_STAFFING_RECRUITING = (
    "staffing",
    "recruiter",
    "recruitment",
    "talent acquisition",
    "bullhorn",
    "applicant tracking",
    "resume builder",
    "hiring platform",
    "ats",
    "rpo",
    "candidately",
)

_FINANCE_CORE = (
    "investment banking",
    "chartered accountant",
    "audit",
    "underwriting",
    "actuarial",
)

_MANUFACTURING = (
    "manufacturing",
    "plant manager",
    "production engineer",
    "supply chain",
    "warehouse",
)

_GENERIC_FUNCTION = frozenset(
    {
        "sales",
        "marketing",
        "operations",
        "manager",
        "business",
        "development",
        "executive",
        "analyst",
        "consultant",
    }
)


def _blob(*parts: object) -> str:
    chunks: list[str] = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, (list, tuple)):
            chunks.extend(str(x) for x in p if x)
        else:
            chunks.append(str(p))
    return re.sub(r"\s+", " ", " ".join(chunks)).lower()


def detect_domains(
    *,
    title: str | None = None,
    company: str | None = None,
    skills: list[str] | None = None,
    extra: str | None = None,
) -> frozenset[str]:
    """Return coarse domain tags inferred from title, company, skills, and text."""
    text = _blob(title, company, extra, *(skills or []))
    if not text.strip():
        return frozenset()

    tags: set[str] = set()
    if any(m in text for m in _HOSPITALITY):
        tags.add("hospitality")
    if any(m in text for m in _STAFFING_RECRUITING):
        tags.add("staffing")
    if any(m in text for m in _TECH_SAAS):
        tags.add("tech")
    if any(m in text for m in _FINANCE_CORE):
        tags.add("finance")
    if any(m in text for m in _MANUFACTURING):
        tags.add("manufacturing")

    title_tokens = canonical_title_tokens(title)
    if title_tokens & {"sales"} and not tags:
        tags.add("generic_sales")
    return frozenset(tags)


def domain_fit_multiplier(
    candidate_domains: frozenset[str],
    job_domains: frozenset[str],
) -> float:
    """0.1–1.0 multiplier; 1.0 when domains are compatible or unknown."""
    if not job_domains:
        return 1.0

    cand = candidate_domains
    job = job_domains

    # Tech / staffing SaaS candidate vs hospitality sales — common false positive.
    if "hospitality" in job and cand & {"tech", "staffing"} and "hospitality" not in cand:
        return 0.12

    # Hospitality candidate vs pure tech engineering role.
    if "tech" in job and "hospitality" in cand and "tech" not in cand:
        return 0.15

    # Staffing/recruiting vs hotel-only roles.
    if "staffing" in cand and job == frozenset({"hospitality"}):
        return 0.12

    # Manufacturing vs pure desk/SaaS roles (and vice versa).
    if "manufacturing" in job and cand & {"tech", "staffing"} and "manufacturing" not in cand:
        return 0.2
    if "manufacturing" in cand and job & {"tech", "staffing"} and "manufacturing" not in job:
        return 0.2

    return 1.0


def generic_title_overlap_penalty(candidate_title: str | None, job_title: str | None) -> float:
    """Down-rank when titles only overlap on generic function words (e.g. both say sales)."""
    ta = canonical_title_tokens(candidate_title)
    tb = canonical_title_tokens(job_title)
    if not ta or not tb:
        return 1.0
    overlap = ta & tb
    if not overlap:
        return 1.0
    # Only generic tokens in common — not enough to call it a role match.
    if overlap <= _GENERIC_FUNCTION and len(overlap) <= 2:
        return 0.35
    return 1.0
