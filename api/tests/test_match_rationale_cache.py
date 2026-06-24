"""
HIR-20: persisted LLM match rationale. `_serialize_cached_match_row` must serve a
cached rationale only when it's fresh (generated at/after the latest score), and
flag whether the overlay still needs to call the LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hireloop_api.routes.matches import _serialize_cached_match_row

_BASE = {
    "job_id": "11111111-1111-1111-1111-111111111111",
    "title": "Backend Engineer",
    "company_name": "Acme",
    "skills_required": ["python"],
    "explanation": "Rule-based: strong skills overlap.",
}


def _row(**over: object) -> dict:
    computed = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    return {**_BASE, "computed_at": computed, **over}


def test_fresh_cached_rationale_is_used() -> None:
    computed = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    item = _serialize_cached_match_row(
        _row(
            llm_rationale="You led a Django payments rewrite — a direct fit.",
            llm_rationale_at=computed + timedelta(minutes=5),
        )
    )
    assert item["_rationale_cached"] is True
    assert item["explanation"] == "You led a Django payments rewrite — a direct fit."


def test_stale_rationale_is_ignored() -> None:
    computed = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    item = _serialize_cached_match_row(
        _row(
            llm_rationale="Old reasoning from a previous score.",
            llm_rationale_at=computed - timedelta(hours=1),  # generated before re-score
        )
    )
    assert item["_rationale_cached"] is False
    assert item["explanation"] == "Rule-based: strong skills overlap."


def test_no_cached_rationale_flags_for_generation() -> None:
    item = _serialize_cached_match_row(_row(llm_rationale=None, llm_rationale_at=None))
    assert item["_rationale_cached"] is False
    assert item["explanation"] == "Rule-based: strong skills overlap."


def test_missing_columns_are_safe() -> None:
    # career.py path selects no llm_rationale columns at all.
    item = _serialize_cached_match_row(_row())
    assert item["_rationale_cached"] is False
    assert item["job_id"] == _BASE["job_id"]
