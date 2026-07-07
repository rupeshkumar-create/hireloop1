from hireloop_api.services.resume_parser import ResumeParserService


def test_linkedin_grouped_company_duration_title_parses_cleanly() -> None:
    text = """
    Contact Test Candidate
    test-candidate@example.com
    Category Planner at Retail Marketplace
    www.linkedin.com/in/test-candidate
    Bengaluru, Karnataka, India
    Summary
    Experience
    Target
    4 years 4 months
    Category Planner
    July 2025 - Present (1 year 1 month)
    Bengaluru, Karnataka, India
    Senior Category analyst
    February 2024 - July 2025 (1 year 6 months)
    Education
    National Institute of Fashion Technology Delhi
    Bachelor's degree, Fashion Merchandising · (2009 - 2013)
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.current_title == "Category Planner"
    assert parsed.current_company == "Target"
    assert parsed.work_experience[1].title == "Senior Category analyst"
    assert parsed.work_experience[1].company == "Target"


def test_linkedin_sidebar_labels_are_not_companies() -> None:
    text = """
    Contact Test Designer
    test-designer@example.com Building Limedock | Product Designer
    Bengaluru, Karnataka, India
    www.linkedin.com/in/test-
    designer (LinkedIn)
    www.limedock.com/ (Company) Experience
    Top Skills Limedock
    Creative Head
    Adobe Illustrator
    January 2026 - Present (7 months)
    Bengaluru, Karnataka, India
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.linkedin_url == "https://www.linkedin.com/in/test-designer"
    assert parsed.current_title == "Creative Head"
    assert parsed.current_company == "Limedock"
    assert "Top Skills" not in (parsed.current_company or "")
    assert parsed.work_experience[0].company == "Limedock"


def test_linkedin_certifications_sidebar_is_not_company() -> None:
    text = """
    Contact Test Researcher
    researcher@example.com Pre Doctoral Fellow | IACV lab, IISc
    www.linkedin.com/in/test-researcher
    Ranchi, Jharkhand, India
    Summary
    Top Skills
    Computer Vision
    Certifications
    Experience
    Bengali (Native or Bilingual)
    English (Limited Working) Indian Institute of Science (IISc)
    Hindi (Native or Bilingual) 1 year 10 months
    Indian Institute of Science (IISc)
    1 year 10 months
    Pre Doctoral Fellow
    Certifications October 2025 - March 2026 (6 months)
    Bengaluru, Karnataka, India
    Advanced Learning Algorithms Research Assistant
    June 2024 - March 2026 (1 year 10 months)
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.current_title == "Pre Doctoral Fellow"
    assert parsed.current_company == "Indian Institute of Science (IISc)"
    assert parsed.work_experience[0].company == "Indian Institute of Science (IISc)"
    assert parsed.work_experience[1].company == "Indian Institute of Science (IISc)"
    assert parsed.work_experience[1].title == "Advanced Learning Algorithms Research Assistant"


def test_linkedin_wrapped_empty_slug_url_uses_nearby_handle_line() -> None:
    text = """
    Contact Test Strategist
    www.linkedin.com/in/ Senior Product Manager | AI Generalist
    connectteststrategist
    (LinkedIn) Bengaluru, Karnataka, India
    Summary
    Experience
    Self-employed
    Content Strategy & AI Systems for Startups
    December 2025 - Present (8 months)
    Bengaluru
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.linkedin_url == "https://www.linkedin.com/in/connectteststrategist"
    assert parsed.current_title == "Content Strategy & AI Systems for Startups"
    assert parsed.current_company == "Self-employed"


def test_linkedin_certification_course_title_is_not_company() -> None:
    text = """
    Contact Test Founder
    founder@example.com
    www.linkedin.com/in/test-founder
    Brooklyn, New York, United States
    Top Skills
    Summary
    Product Management
    Experience
    Certifications
    Membership Certificate
    Candidately
    Introduction to R
    6 years 3 months
    Academic User Experience Manager
    CMO | Co-Founder
    May 2020 - Present (6 years 3 months)
    Backed by well-known investors and 20+ other operators.
    Co-Founder / Co-Organizer
    September 2020 - Present (5 years 11 months)
    """

    parsed = ResumeParserService.parse_from_text(text)

    assert parsed.current_title == "CMO | Co-Founder"
    assert parsed.current_company == "Candidately"
    assert parsed.work_experience[0].company == "Candidately"
    assert parsed.work_experience[1].company == "Candidately"
