"""LinkedIn 'Save to PDF' export parsing (incl. German UI labels)."""

from pathlib import Path

import pytest

from hireloop_api.services.resume_parser import ResumeParserService

# Repaired text shape from Profile (10).pdf — Jan Jedlinski LinkedIn export.
JAN_JEDLINSKI_LINKEDIN = """
Kontakt
Jan Jedlinski
https://www.linkedin.com/in/janjedlinski
Putting 200M Candidates Inside Your ATS — Ask Me How
(LinkedIn)
Brooklyn, New York, Vereinigte Staaten von Amerika
Languages
Zusammenfassung
Building category-defining products for the staffing and recruiting
industry since 2016. Co-founder of Candidately and Candidate Search AI.
Berufserfahrung
Candidately
CEO | Co-founder
August 2021 - Present (5 Jahre)
Brooklyn, New York, United States
Candidate Search AI
CEO | Co-founder
Juni 2025 - Present (1 Jahr 2 Monate)
Pioneer Fund
Venture Partner, Investor, LP
August 2018 - Present (8 Jahre)
Gustav
CEO | Co-founder (Acquired by Fuse)
Januar 2017 - Januar 2023 (6 Jahre 1 Monat)
Beavr
CEO | Co-founder
Oktober 2015 - Januar 2017 (1 Jahr 4 Monate)
Ausbildung
Y Combinator
· (2017 - 2017)
Modul University Vienna
Bachelor of Business Administration (BBA), Hotel and Tourism Management · (2014 - 2017)
"""


def test_linkedin_export_parses_name_headline_and_roles() -> None:
    parsed = ResumeParserService.parse_from_text(JAN_JEDLINSKI_LINKEDIN)

    assert parsed.full_name == "Jan Jedlinski"
    assert parsed.headline == "Putting 200M Candidates Inside Your ATS — Ask Me How"
    assert parsed.current_title == "CEO | Co-founder"
    assert parsed.current_company == "Candidately"
    assert "Candidately" in (parsed.summary or "")
    assert parsed.linkedin_url == "https://www.linkedin.com/in/janjedlinski"

    companies = [w.company for w in parsed.work_experience]
    assert "Candidately" in companies
    assert "Candidate Search AI" in companies
    assert "Pioneer Fund" in companies
    assert "Gustav" in companies
    assert "Beavr" in companies
    assert not any(c and "Jahre" in c for c in companies)
    assert parsed.parser_metadata["source"] == "linkedin_export"


RUPESH_KUMAR_LINKEDIN = """
Contact
Rupesh Kumar
youthinkso@live.in
Helping Recruiters Turn Resumes into Client-Ready Submissions in
https://www.linkedin.com/in/iamrupesh
Seconds | Go-To-Market Lead for AI Resume Builder
(LinkedIn)
New York, New York, United States
www.candidate.ly/book-a-demo
(Company)
Summary
Top Skills
For the last 4+ years at Candidate.ly, I've worked directly with
Artificial Intelligence (AI)
thousands of staffing agencies to improve how they present
Digital Strategy
candidates to clients – especially in Bullhorn-driven workflows.
Automation
Experience
Candidate.ly
Go-To-Market Lead
2021 - Present
"""


def test_english_linkedin_export_parses_contact_name_and_location() -> None:
    parsed = ResumeParserService.parse_from_text(RUPESH_KUMAR_LINKEDIN)
    assert parsed.full_name == "Rupesh Kumar"
    assert parsed.location_city == "New York"
    assert "artificial intelligence" in " ".join(parsed.skills)
    assert parsed.parser_metadata["source"] == "linkedin_export"


@pytest.mark.skipif(
    not Path("/Users/rupesh/Downloads/Profile (10).pdf").is_file(),
    reason="local fixture PDF not present",
)
def test_linkedin_pdf_file_parses_jan_jedlinski() -> None:
    pdf = Path("/Users/rupesh/Downloads/Profile (10).pdf").read_bytes()
    parsed = ResumeParserService.parse_from_bytes_local(pdf, "Profile (10).pdf", "application/pdf")

    assert parsed.full_name == "Jan Jedlinski"
    assert parsed.current_company == "Candidately"
    assert len(parsed.work_experience) >= 5
