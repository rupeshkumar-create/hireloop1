from __future__ import annotations

import uuid
from datetime import UTC, datetime

from hireloop_api.routes import matches
from hireloop_api.services.match_audit import audit_match_quality


def _candidate(**kwargs: object) -> dict:
    base = {
        "current_title": "Go-To-Market Lead",
        "current_company": "Candidately",
        "headline": "B2B SaaS staffing",
        "summary": "AI workflow automation for recruiters",
        "years_experience": 10,
        "skills": ["sales", "saas", "automation"],
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "remote_preference": "any",
        "open_to_relocation": True,
        "location_scope": "country",
        "target_titles": ["Head of GTM", "VP Sales"],
    }
    base.update(kwargs)
    return base


def _job(**kwargs: object) -> dict:
    base = {
        "job_id": uuid.uuid4(),
        "title": "Head of GTM - Staffing SaaS",
        "company_name": "RecruitOS",
        "description": "Own B2B SaaS GTM for staffing and recruiting automation.",
        "skills_required": ["sales", "saas", "automation"],
        "is_remote": True,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "seniority": "lead",
        "ctc_min": None,
        "ctc_max": None,
    }
    base.update(kwargs)
    return base


def test_match_audit_explains_accepted_relevant_job() -> None:
    audit = audit_match_quality(_candidate(), _job(), {"overall": 0.72})

    assert audit.accepted is True
    assert audit.reasons == []
    assert audit.signals["title_affinity"] > 0
    assert audit.signals["skill_overlap"] > 0
    assert audit.signals["domain_multiplier"] >= 1.0


def test_match_audit_reports_quality_gate_reasons_for_rejected_job() -> None:
    audit = audit_match_quality(
        _candidate(),
        _job(
            title="Hotel Sales Manager",
            company_name="Marriott",
            description="hospitality hotel resort sales",
            skills_required=["sales", "hospitality"],
        ),
        {"overall": 0.85},
    )

    assert audit.accepted is False
    assert "domain_mismatch" in audit.reasons
    assert audit.signals["domain_multiplier"] < 0.25


def test_cached_match_serializer_attaches_match_diagnostics() -> None:
    row = {
        **_job(),
        "job_id": uuid.uuid4(),
        "company_logo_url": None,
        "company_domain": "recruitos.example",
        "employment_type": "full_time",
        "salary_currency": "INR",
        "apply_url": "https://example.com/apply",
        "overall_score": 0.72,
        "skills_score": 0.84,
        "experience_score": 0.9,
        "location_score": 1.0,
        "ctc_score": 0.5,
        "explanation": "Good match",
        "llm_rationale": None,
        "llm_rationale_at": None,
        "computed_at": datetime.now(UTC),
        "has_kit": False,
        "intro_status": None,
        "application_status": None,
    }

    serialized = matches._serialize_current_quality_cached_rows(
        [row],
        candidate=_candidate(),
        min_score=0.38,
    )

    assert len(serialized) == 1
    diagnostics = serialized[0]["match_diagnostics"]
    assert diagnostics["accepted"] is True
    assert diagnostics["signals"]["title_affinity"] > 0
    assert diagnostics["signals"]["skill_overlap"] > 0
