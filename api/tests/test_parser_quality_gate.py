"""
#1: deterministic post-parse quality gate — drop résumé-parse artifacts so the
profile self-completes with clean data and Aarya doesn't store/ask junk.

Regression guard: real skills/titles must survive; artifacts must be dropped.
"""

from __future__ import annotations

from hireloop_api.services.resume_parser import (
    _canonical_skill,
    _looks_like_tagline,
    _normalise_skill_list,
)


def test_real_skills_survive() -> None:
    for good in [
        "Python",
        "Product Management",
        "stakeholder communication",
        "go to market",
        "Bullhorn",
        "demand generation",
    ]:
        assert _canonical_skill(good) is not None, good


def test_artifacts_dropped() -> None:
    for junk in [
        "i personally:",
        "used by",
        "branded",
        "languages",
        "english (professional working)",
        "we delivered measurable growth across the funnel",  # >4 words / fragment
        "responsible for revenue",
    ]:
        assert _canonical_skill(junk) is None, junk


def test_normalise_skill_list_cleans_noisy_input() -> None:
    noisy = [
        "digital strategy",
        "english (professional working)",
        "i personally:",
        "sales operations",
        "languages",
        "Python",
    ]
    out = _normalise_skill_list(noisy)
    # Known skills come back as canonical vocabulary labels; unknown real skills
    # (not in the vocab) are kept as written.
    assert "digital strategy" in out
    assert "Sales Operations" in out
    assert "Python" in out
    assert all(
        j not in out for j in ["languages", "i personally:", "english (professional working)"]
    )


def test_real_titles_pass() -> None:
    for good in [
        "Senior Backend Engineer",
        "GTM Lead - AI Resume Builder",
        "Product Manager",
        "Area Sales Manager",
        "VP of Engineering",
    ]:
        assert _looks_like_tagline(good) is False, good


def test_taglines_detected() -> None:
    for tagline in [
        "Helping Recruiters Turn Resumes into Client-Ready Submissions | GTM Lead",
        "Building the future of hiring",
        "Passionate about product | ex-Google | startup advisor | speaker",
        "Driving growth for early-stage SaaS companies across India and SEA markets today",
    ]:
        assert _looks_like_tagline(tagline) is True, tagline
