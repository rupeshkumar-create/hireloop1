"""Tests for career path prioritization."""

from hireloop_api.services.career_path import _serialize_path


def test_serialize_path_includes_prioritized_title() -> None:
    row = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "current_role": "Engineer",
        "summary": "Growing into leadership",
        "steps": [],
        "target_titles": ["Senior Engineer"],
        "target_locations": ["Bengaluru"],
        "model": "test",
        "prioritized_title": "Staff Engineer",
        "created_at": None,
        "updated_at": None,
    }
    out = _serialize_path(row)
    assert out["prioritized_title"] == "Staff Engineer"
