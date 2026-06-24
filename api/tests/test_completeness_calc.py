"""
Profile completeness is weighted: foundation vs self-reported preferences.
Regression guards for the 23%→85% jump when only LPA was added.
"""

from __future__ import annotations

from hireloop_api.services.career_intelligence.engine import _completeness


def _ctx(**over: object) -> dict:
    base = {
        "full_name": "Rupesh Kumar",
        "current_title": "GTM Lead",
        "current_company": "Candidately",
        "years_experience": 8,
        "location_city": "Bengaluru",
        "skills": ["gtm", "sales", "saas"],
        "headline": "Helping recruiters…",
        "career_profile": {
            "experience_career_history": {"roles": [{"title": "GTM Lead"}]},
            "education_credentials": {"education": [{"degree": "B.Tech"}]},
        },
    }
    base.update(over)
    return base


def test_linkedin_imported_profile_mid_without_preferences() -> None:
    # Rich LinkedIn/resume import but no CTC/notice/goal yet — capped below 85%.
    pct = _completeness(_ctx())
    assert pct == 62


def test_full_profile_reaches_100() -> None:
    pct = _completeness(
        _ctx(
            expected_ctc_min=2_500_000,
            current_ctc=1_800_000,
            notice_period_days=30,
            looking_for="Head of GTM at AI SaaS",
            remote_preference="hybrid",
        )
    )
    assert pct == 100


def test_sparse_profile_is_low() -> None:
    pct = _completeness({"full_name": "X", "skills": []})
    assert pct <= 12


def test_does_not_depend_on_ci_leaves() -> None:
    assert _completeness(_ctx()) == _completeness(_ctx())


def test_ctc_only_modest_bump() -> None:
    sparse = {"full_name": "Rupesh", "headline": "Builder"}
    with_ctc = {**sparse, "expected_ctc_min": 2_000_000}
    delta = _completeness(with_ctc) - _completeness(sparse)
    assert 10 <= delta <= 18


def test_signup_name_only_not_inflated() -> None:
    pct = _completeness({"full_name": "Rupesh Kumar"})
    assert 6 <= pct <= 12
