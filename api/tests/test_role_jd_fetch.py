"""Tests for recruiter role URL import."""

from __future__ import annotations

import pytest

from hireloop_api.services.role_jd_fetch import (
    RoleImportError,
    _parse_greenhouse_url,
    _parse_lever_url,
    _title_from_html,
    _validate_public_url,
)


def test_validate_public_url_rejects_localhost() -> None:
    with pytest.raises(RoleImportError):
        _validate_public_url("http://localhost/jobs/1")


def test_validate_public_url_accepts_https() -> None:
    assert _validate_public_url("https://boards.greenhouse.io/acme/jobs/123") == (
        "https://boards.greenhouse.io/acme/jobs/123"
    )


def test_parse_greenhouse_url() -> None:
    assert _parse_greenhouse_url("https://boards.greenhouse.io/acme/jobs/123456") == (
        "acme",
        "123456",
    )


def test_parse_lever_url() -> None:
    assert _parse_lever_url("https://jobs.lever.co/hireloop/abc-123-def") == (
        "hireloop",
        "abc-123-def",
    )


def test_title_from_html_og_tag() -> None:
    html = """
    <html><head>
    <meta property="og:title" content="Senior Backend Engineer" />
    </head><body></body></html>
    """
    assert _title_from_html(html) == "Senior Backend Engineer"
