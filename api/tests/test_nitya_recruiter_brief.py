"""Nitya recruiter brief parsing — comp LPA and remote policy normalization."""

from hireloop_api.services.role_jd_extract import (
    normalize_role_remote_policy,
    parse_lpa_inr,
)


def test_parse_lpa_inr_from_plain_number() -> None:
    assert parse_lpa_inr(40) == 4_000_000
    assert parse_lpa_inr("40") == 4_000_000


def test_parse_lpa_inr_from_indian_comp_strings() -> None:
    assert parse_lpa_inr("₹40 LPA") == 4_000_000
    assert parse_lpa_inr("40 LPA") == 4_000_000
    assert parse_lpa_inr("40-50 LPA") == 4_000_000


def test_parse_lpa_inr_invalid_returns_none() -> None:
    assert parse_lpa_inr(None) is None
    assert parse_lpa_inr("negotiable") is None


def test_normalize_role_remote_policy_maps_llm_values() -> None:
    assert normalize_role_remote_policy("remote") == "remote"
    assert normalize_role_remote_policy("Fully Remote") == "remote"
    assert normalize_role_remote_policy("Hybrid") == "hybrid"
    assert normalize_role_remote_policy("on-site") == "onsite"
    assert normalize_role_remote_policy("unknown") is None
    assert normalize_role_remote_policy("maybe") is None
