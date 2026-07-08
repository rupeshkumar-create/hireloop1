"""Tests for industry/domain fit penalties in matching."""

from __future__ import annotations

from hireloop_api.services.domain_fit import (
    detect_domains,
    domain_fit_multiplier,
    generic_title_overlap_penalty,
)
from hireloop_api.services.matching import _assemble_score


def test_detect_hospitality_job_from_accor_title() -> None:
    domains = detect_domains(
        title="Associate Director of Sales - Mumbai",
        company="AccorHotel",
        skills=["sales", "hospitality"],
        extra="hotel revenue management",
    )
    assert "hospitality" in domains


def test_detect_staffing_saas_candidate() -> None:
    domains = detect_domains(
        title="Go-To-Market Lead",
        company="Candidately",
        skills=["AI", "Digital Strategy", "Automation"],
        extra="staffing agencies B2B SaaS",
    )
    assert domains & {"tech", "staffing"}


def test_hospitality_job_penalised_for_saas_candidate() -> None:
    cand = detect_domains(
        title="Go-To-Market Lead",
        company="Candidately",
        skills=["AI", "Digital Strategy", "Automation"],
    )
    job = detect_domains(
        title="Associate Director of Sales",
        company="AccorHotel",
        extra="hospitality hotel resort",
    )
    assert domain_fit_multiplier(cand, job) <= 0.15


def test_dental_healthcare_job_penalised_for_staffing_saas_candidate() -> None:
    cand = detect_domains(
        title="Go-To-Market Lead",
        company="Candidately",
        skills=["AI", "Digital Strategy", "Automation", "Sales"],
        extra="B2B SaaS for staffing agencies",
    )
    job = detect_domains(
        title="Sales Manager",
        company="SmileBright Dental Clinic",
        skills=["sales", "patient acquisition"],
        extra="dental clinic healthcare practice management",
    )
    assert {"healthcare", "local_services"} <= job
    assert domain_fit_multiplier(cand, job) <= 0.15


def test_commercial_function_overlap_counts_generic_overlap_still_penalised() -> None:
    # Commercial-function overlap (sales/GTM/growth/revenue) now COUNTS as a
    # function match — precision is enforced by the seniority-fit gate + domain
    # fit, not by penalising the shared commercial function. (Previously the
    # generic-title penalty down-ranked these; that fought relevant senior GTM
    # matching, so it's intentionally no longer penalised here.)
    assert generic_title_overlap_penalty("Director of Sales", "Head of Growth") == 1.0
    # A truly generic, NON-commercial single-word overlap is still down-ranked.
    assert generic_title_overlap_penalty("Operations Manager", "Project Manager") < 1.0
    # Exact / contained Ops Manager titles must NOT be crushed — that left the
    # Jobs feed empty for centre-ops candidates despite Apify inserts.
    assert generic_title_overlap_penalty("Operations Manager", "Operations Manager") == 1.0
    assert (
        generic_title_overlap_penalty("Senior Operations Manager", "Operations Manager") == 1.0
    )


def test_saas_gtm_vs_accor_hotel_score_is_low() -> None:
    """Regression: Accor hotel sales must not rank ~60% for a SaaS GTM profile."""
    cand_row = {
        "full_name": "Rupesh Kumar",
        "current_title": "Go-To-Market Lead",
        "current_company": "Candidately",
        "headline": "B2B SaaS for staffing agencies",
        "summary": "AI resume builder and recruiting automation",
        "years_experience": 10,
        "skills": ["AI", "Digital Strategy", "Automation", "Sales"],
        "expected_ctc_min": 2_500_000,
        "expected_ctc_max": 4_000_000,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "remote_preference": "any",
        "open_to_relocation": False,
        "location_scope": "city",
        "target_titles": ["Head of Sales", "VP Sales"],
    }
    job_row = {
        "title": "Associate Director of Sales - Mumbai",
        "description": "Accor hospitality hotel sales leadership in Mumbai",
        "seniority": "director",
        "skills_required": ["sales", "hospitality", "revenue"],
        "is_remote": False,
        "location_city": "Mumbai",
        "location_state": "Maharashtra",
        "ctc_min": 2_000_000,
        "ctc_max": 3_500_000,
        "company_name": "AccorHotel",
    }
    result = _assemble_score(cand_row, job_row, embed_skills_sim=0.45, embed_profile_sim=0.42)
    assert result["overall"] < 0.35, f"expected weak match, got {result['overall']}"
