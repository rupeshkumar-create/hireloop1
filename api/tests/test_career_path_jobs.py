"""Career-path job title matching — block generic token false positives."""

from hireloop_api.routes.career import needs_path_job_top_up
from hireloop_api.services.career_path_jobs import (
    job_matches_path_titles,
    normalize_path_search_titles,
    rank_path_job_rows,
    should_enforce_path_title_gate,
)


def test_should_enforce_path_title_gate_for_customer_success_only() -> None:
    cs = normalize_path_search_titles(
        ["Customer Success Team Lead"],
        prioritized_title="Customer Success Team Lead",
    )
    generic = normalize_path_search_titles(
        ["Assistant Manager"],
        prioritized_title="Assistant Manager",
    )
    assert should_enforce_path_title_gate(cs)
    assert not should_enforce_path_title_gate(generic)


def test_job_matches_path_titles_rejects_plain_operations_for_customer_success_team_lead() -> None:
    titles = normalize_path_search_titles(
        ["Customer Success Team Lead"],
        prioritized_title="Customer Success Team Lead",
    )
    assert not job_matches_path_titles("Lead Operations Manager - MFI South", titles)
    assert not job_matches_path_titles("Head - Revenue Operations and Monetisation", titles)
    assert job_matches_path_titles("Customer-Success (Bengaluru)", titles)
    assert job_matches_path_titles("Customer Success Manager", titles)


def test_job_matches_path_titles_rejects_marketing_ops_for_customer_success_path() -> None:
    titles = normalize_path_search_titles(
        [
            "Senior Customer Success Manager",
            "Category Manager",
            "Operations Manager",
            "Customer Experience Manager",
        ],
        prioritized_title="Senior Manager - Customer Success / CX Operations",
    )
    assert not job_matches_path_titles("Marketing Operations Manager", titles)
    assert not job_matches_path_titles("Revenue Operations Manager", titles)


def test_job_matches_path_titles_accepts_relevant_customer_roles() -> None:
    titles = [
        "Senior Customer Success Manager",
        "Customer Experience Manager",
    ]
    assert job_matches_path_titles("Customer Success Manager", titles)
    assert job_matches_path_titles("Customer Experience Manager - SaaS", titles)


def test_job_matches_path_titles_rejects_bare_team_lead_false_positive() -> None:
    titles = [
        "Customer Success Manager",
        "Implementation Team Lead",
        "CX Operations Lead",
    ]
    assert not job_matches_path_titles("Team Lead", titles)
    assert job_matches_path_titles("Implementation Team Lead", titles)


def test_job_matches_path_titles_accepts_category_roles() -> None:
    titles = ["Category Manager", "Assistant Manager - Category"]
    assert job_matches_path_titles("Category Manager - Fashion", titles)
    assert not job_matches_path_titles("Marketing Operations Manager", titles)


def test_job_matches_path_titles_rejects_opposite_engineering_specialties() -> None:
    titles = ["Senior Backend Engineer", "Backend Developer"]
    assert not job_matches_path_titles("Frontend Engineer", titles)
    assert not job_matches_path_titles("Mobile Engineer", titles)
    assert job_matches_path_titles("Backend Engineer - Python", titles)


def test_job_matches_path_titles_rejects_data_engineer_for_scientist_path() -> None:
    titles = ["Data Scientist", "Machine Learning Scientist"]
    assert not job_matches_path_titles("Data Engineer", titles)
    assert job_matches_path_titles("Senior Data Scientist", titles)


def test_rank_path_job_rows_prefers_phrase_matches() -> None:
    titles = ["Customer Success Manager"]
    rows = [
        {"job_id": "1", "title": "Marketing Operations Manager", "overall_score": 0.9},
        {"job_id": "2", "title": "Customer Success Manager", "overall_score": 0.5},
    ]
    ranked = rank_path_job_rows(rows, titles, limit=5)
    assert [r["job_id"] for r in ranked] == ["2"]


def test_path_discovery_tops_up_until_ten_relevant_jobs() -> None:
    assert needs_path_job_top_up(0)
    assert needs_path_job_top_up(9)
    assert not needs_path_job_top_up(10)
    assert not needs_path_job_top_up(20)
