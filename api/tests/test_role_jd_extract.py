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


def test_suggest_chips_comp_from_role_post() -> None:
    role = {
        "title": "Go-To-Market Lead",
        "comp_min": 2_800_000,
        "comp_max": 4_500_000,
        "location_city": "Bengaluru",
    }
    chips = suggest_chips_for_reply("What is the comp structure in LPA?", role)
    assert "₹28–45 LPA fixed only" in chips
    assert "₹28–45 LPA + variable" in chips
    assert "₹10 LPA" not in " ".join(chips)


def test_suggest_chips_comp_without_numbers_uses_structure_only() -> None:
    role = {"title": "Developer", "location_city": "Bengaluru", "jd_text": "Hiring in Bangalore"}
    chips = suggest_chips_for_reply("What's the comp budget in LPA?", role)
    assert "Fixed only" in chips
    assert "Fixed + variable" in chips
    assert not any("₹10" in c for c in chips)


def test_suggest_chips_comp_parsed_from_jd_text() -> None:
    role = {
        "title": "Engineer",
        "jd_text": "Compensation: ₹20–32 LPA. Bengaluru hybrid.",
    }
    chips = suggest_chips_for_reply("Confirm the comp range?", role)
    assert "₹20–32 LPA fixed only" in chips


def test_suggest_chips_location_from_role_post() -> None:
    role = {"location_city": "Bengaluru", "remote_policy": "hybrid"}
    chips = suggest_chips_for_reply("Is this remote or Bangalore only?", role)
    assert "Hybrid in Bengaluru" in chips
    assert "Remote only" in chips


def test_suggest_chips_experience_from_jd_structured() -> None:
    role = {
        "jd_structured": {
            "years_experience_min": 5,
            "years_experience_max": 10,
        }
    }
    chips = suggest_chips_for_reply("How many years of experience?", role)
    assert "5–10 years" in chips
