"""Tests for Apify Google Jobs market configuration."""

from __future__ import annotations

from hireloop_api.services.apify.jobs_scraper import (
    DEFAULT_MAX_PAGINATION,
    ApifyJobsScraper,
    _MARKET_GOOGLE_CONFIG,
)


def test_gb_market_uses_gb_country_code() -> None:
    assert _MARKET_GOOGLE_CONFIG["GB"]["country"] == "gb"
    assert _MARKET_GOOGLE_CONFIG["GB"]["google_domain"] == "google.co.uk"


def test_google_jobs_input_bounded_pagination() -> None:
    payload = ApifyJobsScraper._build_google_jobs_input(
        query="Product Manager",
        location="London",
        max_results=50,
        market="GB",
    )
    assert payload["country"] == "gb"
    assert payload["language"] == "en"
    assert payload["google_domain"] == "google.co.uk"
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
