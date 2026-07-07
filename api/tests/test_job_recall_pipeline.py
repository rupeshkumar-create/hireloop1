from __future__ import annotations

from hireloop_api.services.job_recall_pipeline import (
    annotate_recall_sources,
    build_query_terms,
    union_and_rank_recall_pools,
)


def _job(job_id: str, **kwargs: object) -> dict:
    base = {
        "id": job_id,
        "title": "Growth Manager",
        "company_name": "Acme",
        "skills_required": ["growth"],
        "overall_score": 0.5,
        "skills_score": 0.5,
        "description": "SaaS growth role",
    }
    base.update(kwargs)
    return base


def test_build_query_terms_uses_user_query_goals_path_and_skills() -> None:
    terms = build_query_terms(
        query_text="Find me growth leadership roles",
        primary_titles=["Head of Growth", "Lifecycle Marketing Lead"],
        skills=["SQL", "Lifecycle Marketing", "Retention"],
        desired_industry="SaaS",
        limit=8,
    )

    assert terms[:3] == [
        "Find me growth leadership roles",
        "Head of Growth",
        "Lifecycle Marketing Lead",
    ]
    assert "Lifecycle Marketing" in terms
    assert "SaaS" in terms
    assert len(terms) <= 8


def test_union_and_rank_recall_pools_keeps_broader_more_relevant_jobs() -> None:
    narrow_exact = [
        _job(
            "generic-growth",
            title="Growth Executive",
            skills_required=["cold calling"],
            overall_score=0.42,
            skills_score=0.1,
        )
    ]
    scored_match = [
        _job(
            "head-growth",
            title="Head of Growth - SaaS",
            skills_required=["growth", "sql", "retention"],
            overall_score=0.74,
            skills_score=0.8,
        )
    ]
    skill_pool = [
        _job(
            "lifecycle",
            title="Lifecycle Marketing Lead",
            skills_required=["lifecycle marketing", "sql"],
            overall_score=None,
            skills_score=0.7,
        )
    ]

    out = union_and_rank_recall_pools(
        [
            ("exact_query", narrow_exact),
            ("precomputed_match", scored_match),
            ("skill_overlap", skill_pool),
        ],
        limit=10,
    )

    assert [j["id"] for j in out] == ["head-growth", "lifecycle", "generic-growth"]
    assert out[0]["recall_sources"] == ["precomputed_match"]
    assert out[1]["recall_sources"] == ["skill_overlap"]
    assert out[2]["recall_sources"] == ["exact_query"]
    assert all("recall_diagnostics" in j for j in out)


def test_union_and_rank_recall_pools_merges_duplicate_sources() -> None:
    out = union_and_rank_recall_pools(
        [
            ("exact_query", [_job("same", overall_score=0.5, skills_score=0.4)]),
            ("skill_overlap", [_job("same", overall_score=0.45, skills_score=0.9)]),
        ],
        limit=10,
    )

    assert len(out) == 1
    assert out[0]["recall_sources"] == ["exact_query", "skill_overlap"]
    assert out[0]["skills_score"] == 0.9


def test_annotate_recall_sources_preserves_existing_source_order() -> None:
    rows = annotate_recall_sources([_job("a")], "profile_broad")

    assert rows[0]["recall_sources"] == ["profile_broad"]
