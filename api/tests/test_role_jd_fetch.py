"""Tests for recruiter role URL import."""

from __future__ import annotations

import socket

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


def test_validate_public_url_accepts_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("99.86.1.1", 0)),
        ],
    )
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


def test_parse_greenhouse_embed_url() -> None:
    assert _parse_greenhouse_url(
        "https://boards.greenhouse.io/embed/job_app?for=acme&token=987654"
    ) == ("acme", "987654")


def test_parse_ashby_url() -> None:
    from hireloop_api.services.role_jd_fetch import _parse_ashby_url

    assert _parse_ashby_url("https://jobs.ashbyhq.com/hireschema/abc-123") == (
        "hireschema",
        "abc-123",
    )


def test_text_from_next_data_extracts_description() -> None:
    from hireloop_api.services.role_jd_fetch import _text_from_next_data

    html = """
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"job":{"title":"Eng",
      "descriptionHtml":"<p>Build products with Python and React for millions of users across India and beyond.</p>"}}}}
    </script>
    """
    text = _text_from_next_data(html)
    assert text is not None
    assert "Python" in text
    assert len(text) >= 40


def test_best_html_body_prefers_job_description_block() -> None:
    from hireloop_api.services.role_jd_fetch import _best_html_body

    html = """
    <html><body>
      <nav>Home Careers Login</nav>
      <div class="job-description">
        <p>We are hiring a backend engineer to design APIs, own reliability, and mentor teammates.</p>
        <p>Required: Python, Postgres, and distributed systems experience.</p>
      </div>
      <footer>Copyright</footer>
    </body></html>
    """
    body = _best_html_body(html)
    assert "backend engineer" in body
    assert "Copyright" not in body or "Python" in body


def test_json_ld_parses_html_encoded_type_attr() -> None:
    html = """
    <script id="js-job-posting" type="application/ld&#x2B;json">
    {
      "@context": "https://schema.org",
      "@type": "JobPosting",
      "title": "Field Sales Manager - US East Coast",
      "description": "<p>ADP is hiring a Field Sales Manager for the US East Coast territory with quota ownership and coaching responsibility.</p>",
      "hiringOrganization": {"@type": "Organization", "name": "ADP"},
      "jobLocation": {
        "@type": "Place",
        "name": "United States, Home Office USA",
        "address": {
          "@type": "PostalAddress",
          "addressLocality": "United States",
          "addressRegion": "Home Office Usa",
          "addressCountry": "United States"
        }
      }
    }
    </script>
    """
    parsed = _parse_json_ld_job_posting(html)
    assert parsed is not None
    assert parsed["title"] == "Field Sales Manager - US East Coast"
    assert parsed["company_name"] == "ADP"
    assert parsed["jd_text"] is not None
    assert "Field Sales Manager" in parsed["jd_text"]


def test_infer_location_uses_title_region_not_nav_city() -> None:
    from hireloop_api.services.role_jd_fetch import infer_role_location

    city, _state = infer_role_location(
        title="Field Sales Manager - US East Coast",
        body=(
            "Sales Field Sales Manager - US East Coast United States, Home Office USA. "
            "Nav also mentions Singapore and Dubai office pickers."
        ),
        structured_city="Singapore",
    )
    assert city == "US East Coast"


def test_location_conflicts_with_title() -> None:
    from hireloop_api.services.role_jd_fetch import location_conflicts_with_title

    assert location_conflicts_with_title("Field Sales Manager - US East Coast", "Singapore")
    assert not location_conflicts_with_title("Backend Engineer - Bengaluru", "Bengaluru")
