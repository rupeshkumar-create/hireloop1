"""
The mock-interview end-of-session feedback must land in the exact shape the UI
renders (overall_score 0-10, string lists), tolerating model drift.
"""

from __future__ import annotations

from hireloop_api.routes.mock_interview import _normalize_feedback


def test_well_formed_feedback_passes_through() -> None:
    fb = _normalize_feedback(
        {
            "overall_score": 8,
            "summary": "Strong, structured answers.",
            "strengths": ["Clear STAR stories", "Good metrics"],
            "areas_to_improve": ["Be more concise"],
            "communication": "Clear and confident.",
            "technical_accuracy": "Solid depth.",
        }
    )
    assert fb["overall_score"] == 8
    assert fb["strengths"] == ["Clear STAR stories", "Good metrics"]
    assert fb["areas_to_improve"] == ["Be more concise"]


def test_rescales_0_to_100_score() -> None:
    # Model answered on a 0-100 scale → scaled to 0-10.
    assert _normalize_feedback({"overall_score": 80})["overall_score"] == 8
    # Out-of-range clamps.
    assert _normalize_feedback({"overall_score": 130})["overall_score"] == 10


def test_coerces_string_list_fields() -> None:
    fb = _normalize_feedback({"strengths": "Just one strength", "areas_to_improve": None})
    assert fb["strengths"] == ["Just one strength"]
    assert fb["areas_to_improve"] == []


def test_non_dict_falls_back_to_summary() -> None:
    fb = _normalize_feedback("freeform model text")
    assert fb["summary"] == "freeform model text"
    assert fb["strengths"] == []
    assert fb["areas_to_improve"] == []
