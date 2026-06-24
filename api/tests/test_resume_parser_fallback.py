from hireloop_api.services.resume_parser import ResumeParserService


def test_parse_from_text_extracts_core_profile_fields() -> None:
    text = """
    Rupesh Kumar
    Senior Software Engineer at Infosys
    Bengaluru, Karnataka
    rupesh@example.com | +91 9876543210
    https://www.linkedin.com/in/rupesh

    Experience: 7 years
    Skills: Python, React, SQL, AWS, FastAPI, TypeScript
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.full_name == "Rupesh Kumar"
    assert parsed.current_title == "Senior Software Engineer"
    assert parsed.current_company == "Infosys"
    assert parsed.years_experience == 7
    assert parsed.location_city == "Bengaluru"
    assert parsed.location_state == "Karnataka"
    assert parsed.linkedin_url == "https://www.linkedin.com/in/rupesh"
    parsed_skills = {skill.lower() for skill in parsed.skills}
    assert {"python", "react", "sql", "aws", "fastapi", "typescript"}.issubset(parsed_skills)
    assert set(parsed.career_profile) == {
        "profile_demographics",
        "experience_career_history",
        "skills_competencies",
        "education_credentials",
        "achievements_leadership",
        "aspirations_market_fit_recommendations",
    }
    assert parsed.career_profile["profile_demographics"]["full_name"] == "Rupesh Kumar"
    assert (
        parsed.career_profile["experience_career_history"]["current_career_snapshot"][
            "current_job_title"
        ]
        == "Senior Software Engineer"
    )
    assert parsed.career_analysis["current_position"] == "Senior Software Engineer"
    assert "next_likely_roles_1_3_years" in parsed.career_analysis


def test_parse_from_text_normalizes_messy_resume_profile() -> None:
    text = """
    PRIYA SHAH
    Bangalore, KA | +91-98765 43210 | priya@example.com
    linkedin.com/in/priya-shah/ | https://github.com/priyashah).

    Staff Frontend Engineer
    Razorpay
    Apr '21 - Present

    Senior UI Developer @ Flipkart | 06/2018 - Mar 2021

    Skills & Technologies
    ReactJS • Node • JS • TypeScript • PostgreSQL • Amazon Web Services • Team player
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.full_name == "Priya Shah"
    assert parsed.phone == "+919876543210"
    assert parsed.linkedin_url == "https://www.linkedin.com/in/priya-shah"
    assert parsed.github_url == "https://github.com/priyashah"
    assert parsed.current_title == "Staff Frontend Engineer"
    assert parsed.current_company == "Razorpay"
    assert parsed.location_city == "Bengaluru"
    assert parsed.location_state == "Karnataka"
    assert parsed.years_experience is not None
    assert 5 <= parsed.years_experience <= 15

    # Known skills resolve to canonical vocabulary display labels.
    parsed_skills = set(parsed.skills)
    assert {"React", "Node.js", "JavaScript", "TypeScript", "PostgreSQL", "AWS"}.issubset(
        parsed_skills
    )
    assert "team player" not in parsed_skills
    assert parsed.parser_metadata["source"] == "regex"
    assert parsed.parser_metadata["quality_score"] >= 70
