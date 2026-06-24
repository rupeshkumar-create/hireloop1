from hireloop_api.services.profile_experience import (
    best_linkedin_headline,
    build_merged_experience,
)


def test_best_linkedin_headline_prefers_apify() -> None:
    headline = best_linkedin_headline(
        {
            "user_metadata": {"headline": "Wrong Name"},
            "apify_profile": {"headline": "Head of Growth at Hireloop"},
        }
    )
    assert headline == "Head of Growth at Hireloop"


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
