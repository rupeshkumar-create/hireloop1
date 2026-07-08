"""Tests for recruiter role URL import."""

from __future__ import annotations

import pytest

from hireloop_api.services.role_jd_fetch import (
    RoleImportError,
    _humanize_slug,
    _location_from_value,
    _parse_greenhouse_url,
    _parse_json_ld_job_posting,
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


def test_humanize_slug() -> None:
    assert _humanize_slug("hire-loop") == "Hire Loop"


def test_location_from_value_splits_city_state() -> None:
    city, state = _location_from_value("Bengaluru, Karnataka, India")
    assert city == "Bengaluru"
    assert state == "Karnataka"


def test_location_from_job_posting_address() -> None:
    city, state = _location_from_value(
        {
            "address": {
                "@type": "PostalAddress",
                "addressLocality": "San Francisco",
                "addressRegion": "CA",
            }
        }
    )
    assert city == "San Francisco"
    assert state == "CA"


def test_parse_json_ld_job_posting_extracts_core_fields() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "JobPosting",
      "title": "Staff Platform Engineer",
      "description": "<p>Build reliable systems for millions of users across India.</p><p>Must have Python and Kubernetes.</p>",
      "hiringOrganization": {"@type": "Organization", "name": "Acme Labs"},
      "jobLocation": {
        "@type": "Place",
        "address": {
          "@type": "PostalAddress",
          "addressLocality": "Bengaluru",
          "addressRegion": "Karnataka",
          "addressCountry": "IN"
        }
      },
      "jobLocationType": "TELECOMMUTE"
    }
    </script>
    </head><body>Careers</body></html>
    """
    parsed = _parse_json_ld_job_posting(html)
    assert parsed is not None
    assert parsed["title"] == "Staff Platform Engineer"
    assert parsed["company_name"] == "Acme Labs"
    assert parsed["location_city"] == "Bengaluru"
    assert parsed["location_state"] == "Karnataka"
    assert parsed["remote_policy"] == "remote"
    assert parsed["jd_text"] is not None
    assert "Python" in parsed["jd_text"]
    assert len(parsed["jd_text"]) >= 40


def test_parse_json_ld_graph_array() -> None:
    html = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@graph": [
        {"@type": "WebSite", "name": "Careers"},
        {
          "@type": "JobPosting",
          "title": "Frontend Engineer",
          "description": "Ship delightful product experiences with React and TypeScript for customers worldwide.",
          "hiringOrganization": "Pixel Co",
          "jobLocation": "London, England, UK"
        }
      ]
    }
    </script>
    """
    parsed = _parse_json_ld_job_posting(html)
    assert parsed is not None
    assert parsed["title"] == "Frontend Engineer"
    assert parsed["company_name"] == "Pixel Co"
    assert parsed["location_city"] == "London"
    assert "React" in (parsed["jd_text"] or "")
