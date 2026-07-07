from __future__ import annotations

import pytest

from hireloop_api.services import application_kit
from hireloop_api.services.resume_tailor import (
    generate_tailored_html,
    normalize_tailored_resume_html,
    resume_summary_line,
)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    async def ainvoke(self, messages: object) -> _FakeMessage:
        return _FakeMessage(
            """```html
            <html><head><script>alert('x')</script></head><body>
              <h1>null</h1>
              <p class="resume-contact">None · undefined</p>
              <table><tr><td>bad layout</td></tr></table>
              <h2>Professional Summary</h2><p>null</p>
              <h2>Professional Experience</h2>
              <h3>Growth Lead — Acme SaaS</h3>
            </body></html>
            ```"""
        )


def _profile() -> dict:
    return {
        "full_name": "Asha Rao",
        "email": "asha@example.com",
        "phone": "+919999999999",
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "linkedin_url": "https://linkedin.com/in/asha",
        "summary": "Growth leader with SaaS lifecycle experience.",
        "skills": ["Lifecycle Marketing", "SQL", "Experimentation"],
        "experience": [
            {
                "title": "Growth Lead",
                "company": "Acme SaaS",
                "start_date": "2021-01",
                "end_date": None,
                "location": "Bengaluru",
            },
            {
                "title": "Lifecycle Marketing Manager",
                "company": "BetaCloud",
                "start_date": "2018-02",
                "end_date": "2020-12",
            },
        ],
        "education": [{"degree": "MBA", "institution": "IIM Bangalore", "year": "2017"}],
    }


def test_normalize_tailored_resume_html_removes_nulls_and_restores_source_sections() -> None:
    html = normalize_tailored_resume_html(
        """
        <h1>null</h1>
        <p class="resume-contact">None · undefined</p>
        <script>alert(1)</script><img src=x><table><tr><td>x</td></tr></table>
        <h2>Professional Experience</h2>
        <h3>Growth Lead — Acme SaaS</h3>
        """,
        candidate_profile=_profile(),
    )

    assert "<script" not in html.lower()
    assert "<table" not in html.lower()
    assert "<img" not in html.lower()
    assert ">null<" not in html.lower()
    assert ">none<" not in html.lower()
    assert "undefined" not in html.lower()
    assert "<h1>Asha Rao</h1>" in html
    assert "Bengaluru, Karnataka" in html
    assert "asha@example.com" in html
    assert "<h2>Professional Summary</h2>" in html
    assert "<h2>Core Skills</h2>" in html
    assert "<h3>Lifecycle Marketing Manager — BetaCloud</h3>" in html
    assert "<h2>Education</h2>" in html
    assert "MBA — IIM Bangalore · 2017" in html


@pytest.mark.asyncio
async def test_generate_tailored_html_normalizes_llm_output_before_returning() -> None:
    html = await generate_tailored_html(
        llm=_FakeLLM(),  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job={"title": "Head of Growth", "company_name": "Modern SaaS", "description": "SQL"},
        template="modern",
    )

    assert html.startswith("<h1>Asha Rao</h1>")
    assert "<script" not in html.lower()
    assert "<table" not in html.lower()
    assert "<h3>Lifecycle Marketing Manager — BetaCloud</h3>" in html


def test_resume_summary_line_skips_placeholder_paragraphs() -> None:
    summary = resume_summary_line("<h1>Asha Rao</h1><p>null</p><p>Growth leader for SaaS.</p>")
    assert summary == "Growth leader for SaaS."


@pytest.mark.asyncio
async def test_application_kit_persist_uses_safe_resume_summary(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_save_tailored_resume(*args: object, **kwargs: object) -> str:
        captured.update(kwargs)
        return "11111111-1111-1111-1111-111111111111"

    monkeypatch.setattr(application_kit, "save_tailored_resume", _fake_save_tailored_resume)

    await application_kit._persist_tailored_resume(
        None,  # type: ignore[arg-type]
        candidate_id="22222222-2222-2222-2222-222222222222",  # type: ignore[arg-type]
        job={"id": "33333333-3333-3333-3333-333333333333"},
        html="<h1>Asha Rao</h1><p>null</p><p>Growth leader for SaaS.</p>",
    )

    assert captured["summary_line"] == "Growth leader for SaaS."
