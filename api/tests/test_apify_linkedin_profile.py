from hireloop_api.services.apify.linkedin_profile_scraper import (
    build_actor_input,
    normalize_apify_profile,
)


def test_build_actor_input_dev_fusion() -> None:
    inp = build_actor_input(
        "dev_fusion/linkedin-profile-scraper",
        "https://www.linkedin.com/in/testuser",
    )
    assert inp == {"profileUrls": ["https://www.linkedin.com/in/testuser"]}


def test_normalize_apify_profile_dev_fusion_shape() -> None:
    profile = normalize_apify_profile(
        {
            "fullName": "Ada Lovelace",
            "headline": "VP Sales at Acme",
            "summary": "B2B SaaS GTM leader.",
            "location": "Mumbai, Maharashtra, India",
            "jobTitle": "VP Sales",
            "companyName": "Acme",
            "experiences": [
                {
                    "title": "VP Sales",
                    "companyName": "Acme",
                    "jobStartedOn": "2021-01",
                    "jobStillWorking": True,
                    "jobLocation": "Mumbai, India",
                    "jobDescription": "Led 40-person GTM org.",
                }
            ],
            "educations": [
                {
                    "schoolName": "IIT Bombay",
                    "degreeName": "B.Tech",
                    "fieldOfStudy": "Computer Science",
                }
            ],
            "skills": [{"title": "SaaS"}, {"title": "Sales"}],
        }
    )
    assert profile["fullName"] == "Ada Lovelace"
    assert profile["headline"] == "VP Sales at Acme"
    assert len(profile["experiences"]) == 1
    assert profile["experiences"][0]["company"] == "Acme"
    assert len(profile["education"]) == 1
    assert profile["skills"] == ["SaaS", "Sales"]
    assert profile["linkedin_parser_metadata"]["source"] == "apify"
