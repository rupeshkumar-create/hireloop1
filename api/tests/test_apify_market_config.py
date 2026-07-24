"""Tests for Apify Google Jobs market configuration (India-only)."""

from __future__ import annotations

from hireloop_api.services.apify.jobs_scraper import (
    _MARKET_GOOGLE_CONFIG,
    DEFAULT_MAX_PAGINATION,
    ApifyJobsScraper,
)


def test_only_india_market_configured() -> None:
    assert set(_MARKET_GOOGLE_CONFIG.keys()) == {"IN"}
    assert _MARKET_GOOGLE_CONFIG["IN"]["country"] == "in"
    assert _MARKET_GOOGLE_CONFIG["IN"]["google_domain"] == "google.co.in"


def test_google_jobs_input_bounded_pagination() -> None:
    payload = ApifyJobsScraper._build_google_jobs_input(
        query="Product Manager",
        location="Bengaluru",
        max_results=50,
        market="IN",
    )
    assert payload["country"] == "in"
    assert payload["language"] == "en"
    assert payload["google_domain"] == "google.co.in"
    assert payload["max_pagination"] == DEFAULT_MAX_PAGINATION
    assert payload["max_pagination"] > 0
    assert "None" not in str(payload.get("language"))


def test_in_market_uses_co_in() -> None:
    payload = ApifyJobsScraper._build_google_jobs_input(
        query="Software Engineer",
        location="Bengaluru",
        max_results=25,
        market="IN",
    )
    assert payload["country"] == "in"
    assert payload["google_domain"] == "google.co.in"
