"""Tests for recruiter role JD extraction helpers."""

from hireloop_api.services.role_jd_extract import (
    compute_role_readiness,
    suggest_chips_for_reply,
)


def test_compute_role_readiness_full() -> None:
    readiness = compute_role_readiness(
        {
            "title": "Senior Backend Engineer",
            "jd_text": "x" * 50,
            "comp_min": 2_500_000,
            "location_city": "Bengaluru",
        }
    )
    assert readiness["done_count"] == 4
    assert readiness["ready_for_search"] is True
    assert readiness["ready_to_publish"] is True


def test_compute_role_readiness_missing_comp() -> None:
    readiness = compute_role_readiness(
        {
            "title": "PM",
            "jd_text": "x" * 50,
            "location_city": "Mumbai",
        }
    )
    comp_item = next(i for i in readiness["items"] if i["key"] == "comp")
    assert comp_item["done"] is False
    assert readiness["ready_for_search"] is True


def test_suggest_chips_comp_question() -> None:
    chips = suggest_chips_for_reply("What is the comp budget in LPA?")
    assert "₹10 LPA fixed only" in chips


def test_suggest_chips_location_question() -> None:
    chips = suggest_chips_for_reply("Is this remote or Bangalore only?")
    assert "Remote only" in chips
