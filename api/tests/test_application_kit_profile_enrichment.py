from __future__ import annotations

import pytest

from hireloop_api.services.application_kit import _normalize_profile_enrichment
from hireloop_api.services.outcome_learning import build_kit_aware_interview_prep


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"star_stories": ["Owned a migration"]}, {"star_stories": ["Owned a migration"]}),
        ('{"star_stories":["Owned a migration"]}', {"star_stories": ["Owned a migration"]}),
        (None, {}),
        ("not-json", {}),
        ('["not", "an", "object"]', {}),
        (42, {}),
    ],
)
def test_normalize_profile_enrichment_accepts_only_json_objects(
    raw: object,
    expected: dict[str, object],
) -> None:
    assert _normalize_profile_enrichment(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["not-json", '["not", "an", "object"]', 42],
)
def test_interview_prep_tolerates_malformed_profile_enrichment(raw: object) -> None:
    prep = build_kit_aware_interview_prep(
        base_prep="## Likely questions",
        dossier=None,
        job={"title": "Engineer", "company_name": "Acme"},
        profile={"profile_enrichment": raw},
    )

    assert "## Likely questions" in prep
    assert "## Your STAR bank" not in prep


def test_interview_prep_uses_star_stories_from_normalized_json_object() -> None:
    prep = build_kit_aware_interview_prep(
        base_prep="## Likely questions",
        dossier=None,
        job={"title": "Engineer", "company_name": "Acme"},
        profile={
            "profile_enrichment": _normalize_profile_enrichment(
                '{"star_stories":["Reduced latency by 40%"]}'
            )
        },
    )

    assert "## Your STAR bank" in prep
    assert "Reduced latency by 40%" in prep
