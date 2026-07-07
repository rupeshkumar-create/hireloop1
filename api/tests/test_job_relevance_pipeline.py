"""Role-family -> lexical -> embedding rerank pipeline for job relevance."""

from hireloop_api.services.job_relevance_pipeline import (
    filter_and_rerank_jobs,
    rationale_overlay_items,
)


def _candidate(**kwargs: object) -> dict:
    base = {
        "current_title": "Backend Engineer",
        "looking_for": "Senior Backend Engineer",
        "prioritized_title": "Senior Backend Engineer",
        "target_titles": ["Backend Engineer", "Platform Engineer"],
        "skills": ["Python", "PostgreSQL", "AWS"],
    }
    base.update(kwargs)
    return base


def _job(job_id: str, **kwargs: object) -> dict:
    base = {
        "job_id": job_id,
        "title": "Backend Engineer",
        "skills_required": ["Python"],
        "overall_score": 0.5,
        "skills_score": 0.5,
    }
    base.update(kwargs)
    return base


def test_pipeline_rejects_role_family_conflicts_before_score_ranking() -> None:
    jobs = [
        _job("frontend", title="Frontend Engineer", overall_score=0.99, skills_score=0.9),
        _job("backend", title="Backend Engineer - Python", overall_score=0.62, skills_score=0.6),
    ]

    out = filter_and_rerank_jobs(_candidate(), jobs, limit=10)

    assert [j["job_id"] for j in out] == ["backend"]


def test_pipeline_requires_title_or_skill_lexical_signal() -> None:
    jobs = [
        _job(
            "sales",
            title="Sales Manager",
            skills_required=["CRM", "Negotiation"],
            overall_score=0.95,
            skills_score=0.1,
        ),
        _job(
            "platform",
            title="Platform Engineer",
            skills_required=["AWS", "Kubernetes"],
            overall_score=0.58,
            skills_score=0.6,
        ),
    ]

    out = filter_and_rerank_jobs(_candidate(), jobs, limit=10)

    assert [j["job_id"] for j in out] == ["platform"]


def test_pipeline_reranks_by_embedding_composite_after_hard_filters() -> None:
    jobs = [
        _job("lower", title="Backend Engineer", skills_required=["Python"], overall_score=0.55),
        _job("higher", title="Backend Engineer", skills_required=["Python"], overall_score=0.82),
    ]

    out = filter_and_rerank_jobs(_candidate(), jobs, limit=10)

    assert [j["job_id"] for j in out] == ["higher", "lower"]


def test_rationale_overlay_items_only_returns_final_top_ten() -> None:
    jobs = [_job(str(i), overall_score=1 - i / 100) for i in range(12)]

    out = rationale_overlay_items(jobs, limit=50)

    assert len(out) == 10
    assert [j["job_id"] for j in out] == [str(i) for i in range(10)]
