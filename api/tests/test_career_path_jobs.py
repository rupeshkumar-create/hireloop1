"""Career-path job title matching — block generic token false positives."""

from hireloop_api.services.career_path_jobs import (
    job_matches_path_titles,
    normalize_path_search_titles,
    rank_path_job_rows,
)


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


def test_job_matches_path_titles_accepts_category_roles() -> None:
    titles = ["Category Manager", "Assistant Manager - Category"]
    assert job_matches_path_titles("Category Manager - Fashion", titles)
    assert not job_matches_path_titles("Marketing Operations Manager", titles)


def test_rank_path_job_rows_prefers_phrase_matches() -> None:
    titles = ["Customer Success Manager"]
    rows = [
        {"job_id": "1", "title": "Marketing Operations Manager", "overall_score": 0.9},
        {"job_id": "2", "title": "Customer Success Manager", "overall_score": 0.5},
    ]
    ranked = rank_path_job_rows(rows, titles, limit=5)
    assert [r["job_id"] for r in ranked] == ["2"]
