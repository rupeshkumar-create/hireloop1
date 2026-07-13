from hireloop_api.markets import (
    dial_prefix_for_market,
    normalize_market,
    phone_matches_market,
    validate_e164_phone,
)


def test_phone_matches_market_in() -> None:
    assert phone_matches_market("+919876543210", "IN") is True
    assert phone_matches_market("+14155550100", "IN") is False


def test_non_in_market_normalises_to_in() -> None:
    assert normalize_market("US") == "IN"
    assert normalize_market("GB") == "IN"
    assert normalize_market(None) == "IN"


def test_dial_prefix_for_market() -> None:
    assert dial_prefix_for_market("IN") == "+91"
    # Non-IN codes still return +91 (India-only product).
    assert dial_prefix_for_market("US") == "+91"


def test_validate_e164_phone_in() -> None:
    assert validate_e164_phone("+919876543210", "IN") == "+919876543210"


def test_phone_matches_market_empty() -> None:
    assert phone_matches_market(None, "IN") is True
    assert phone_matches_market("", "IN") is True
