"""Regression: truncated LLM JSON should salvage partial parse results."""

from hireloop_api.services.resume_parser import _loads_json_lenient, _repair_truncated_json


def test_repair_truncated_json_closes_open_object() -> None:
    truncated = '{"full_name": "Jane Doe", "skills": ["Python", "FastAPI"'
    out = _repair_truncated_json(truncated)
    assert isinstance(out, dict)
    assert out["full_name"] == "Jane Doe"
    assert out["skills"] == ["Python", "FastAPI"]


def test_loads_json_lenient_uses_repair_on_truncated_payload() -> None:
    truncated = '{"headline": "Senior Engineer", "work_experience": [{"title": "Staff'
    out = _loads_json_lenient(truncated)
    assert isinstance(out, dict)
    assert out["headline"] == "Senior Engineer"
    assert isinstance(out["work_experience"], list)
    assert out["work_experience"][0]["title"] == "Staff"
