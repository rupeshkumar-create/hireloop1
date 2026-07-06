from hireloop_api.services.profile_experience import (
    best_linkedin_headline,
    build_merged_experience,
    derive_overview_from_experience,
    reconcile_candidate_overview,
)


def test_reconcile_overview_from_experience_replaces_corrupt_fields() -> None:
    merged = [
        {
            "title": "Category Planner",
            "company": "Target",
            "is_current": True,
            "start_date": "2025-07",
        },
        {
            "title": "Senior Category Analyst",
            "company": "Target",
            "is_current": False,
            "start_date": "2024-02",
            "end_date": "2025-07",
        },
    ]
    candidate = {
        "headline": "Social Media Manager | Video Ads",
        "summary": "Senior C at (1 year 1 month). 12 years of experience.",
        "current_title": "Senior C",
        "current_company": "(1 year 1 month)",
        "looking_for": "Category Manager - Fashion & Apparel",
        "skills": ["merchandising", "apparel"],
    }
    reconciled, fixes = reconcile_candidate_overview(
        candidate,
        merged,
        linkedin_data={"apify_profile": {"headline": "Social Media Manager"}},
    )
    assert reconciled["current_title"] == "Category Planner"
    assert reconciled["current_company"] == "Target"
    assert "Category Planner" in (reconciled["headline"] or "")
    assert "Target" in (reconciled["summary"] or "")
    assert "current_title" in fixes
    assert "current_company" in fixes


def test_derive_overview_prefers_experience_headline_over_linkedin() -> None:
    merged = [{"title": "VP Sales", "company": "Acme", "is_current": True}]
    overview = derive_overview_from_experience(
        merged,
        linkedin_data={"apify_profile": {"headline": "Wrong LinkedIn Headline"}},
    )
    assert overview["headline"] == "VP Sales at Acme"


def test_best_linkedin_headline_prefers_apify() -> None:
    headline = best_linkedin_headline(
        {
            "user_metadata": {"headline": "Wrong Name"},
            "apify_profile": {"headline": "Head of Growth at Hireschema"},
        }
    )
    assert headline == "Head of Growth at Hireschema"


def test_build_merged_experience_linkedin_with_aarya_bullets() -> None:
    items = build_merged_experience(
        resume_experience=[],
        linkedin_data={
            "apify_profile": {
                "headline": "VP Sales",
                "currentPositions": [
                    {
                        "title": "VP Sales",
                        "company": "Acme",
                        "location": "Mumbai, Maharashtra, India",
                        "description": "Led 40-person GTM org.",
                    }
                ],
            }
        },
        career_profile=None,
        career_intelligence=None,
        candidate={"current_title": "VP Sales", "current_company": "Acme"},
        skills=["sales", "saas"],
    )
    assert len(items) == 1
    assert items[0]["title"] == "VP Sales"
    assert items[0]["source"] == "linkedin"
    assert items[0]["aarya_insights"]
    assert any("Acme" in b for b in items[0]["aarya_insights"])
