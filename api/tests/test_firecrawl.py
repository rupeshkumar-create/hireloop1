"""Firecrawl integration unit tests."""

from __future__ import annotations

import socket

import pytest

from hireloop_api.config import Settings
from hireloop_api.services.firecrawl.client import firecrawl_enabled
from hireloop_api.services.firecrawl.company_intel import get_company_intel_snippet
from hireloop_api.services.firecrawl.jd_fetcher import THIN_JD_MIN_CHARS, is_thin_description
from hireloop_api.services.firecrawl.url_policy import is_scrapable_job_url, validate_firecrawl_url


def test_is_thin_description() -> None:
    assert is_thin_description("")
    assert is_thin_description("x" * (THIN_JD_MIN_CHARS - 1))
    assert not is_thin_description("x" * THIN_JD_MIN_CHARS)


def test_validate_firecrawl_url_blocks_linkedin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("99.86.1.1", 0)),
        ],
    )
    with pytest.raises(ValueError, match="LinkedIn"):
        validate_firecrawl_url("https://www.linkedin.com/jobs/view/123")


def test_is_scrapable_job_url_greenhouse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("99.86.1.1", 0)),
        ],
    )
    assert is_scrapable_job_url("https://boards.greenhouse.io/acme/jobs/123456")


def test_get_company_intel_snippet() -> None:
    data = {
        "firecrawl_intel": {
            "fetched_at": "2026-07-10T12:00:00+00:00",
            "about": "We build AI recruiting tools for global markets.",
            "careers": "Join our engineering team in Bengaluru.",
        }
    }
    snippet = get_company_intel_snippet(data)
    assert "AI recruiting" in snippet
    assert "Bengaluru" in snippet


def test_firecrawl_enabled_requires_key() -> None:
    assert not firecrawl_enabled(Settings(firecrawl_api_key="", firecrawl_enabled=True))
    assert firecrawl_enabled(Settings(firecrawl_api_key="fc-test", firecrawl_enabled=True))
    assert not firecrawl_enabled(Settings(firecrawl_api_key="fc-test", firecrawl_enabled=False))
