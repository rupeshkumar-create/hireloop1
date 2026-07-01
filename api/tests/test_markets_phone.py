import pytest

from hireloop_api.markets import (
    dial_prefix_for_market,
    phone_matches_market,
    validate_e164_phone,
)


def test_phone_matches_market_in() -> None:
    assert phone_matches_market("+919876543210", "IN") is True
    assert phone_matches_market("+14155550100", "IN") is False


def test_phone_matches_market_us() -> None:
    assert phone_matches_market("+14155550100", "US") is True
    assert phone_matches_market("+919876543210", "US") is False


def test_dial_prefix_for_market() -> None:
    assert dial_prefix_for_market("GB") == "+44"


def test_validate_e164_phone_gb() -> None:
    assert validate_e164_phone("+447911123456", "GB") == "+447911123456"


def test_phone_matches_market_empty() -> None:
    assert phone_matches_market(None, "US") is True
    assert phone_matches_market("", "US") is True
