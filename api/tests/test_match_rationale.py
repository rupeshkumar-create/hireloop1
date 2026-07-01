"""
Tests for the LLM match-rationale service (P10).

A fake LLM caller is injected, so these run with no API key and no network.
The key guarantees: it parses model JSON, ignores hallucinated job_ids, and
degrades gracefully to {} on any failure (so the feed keeps its rule-based
explanation).
"""

from __future__ import annotations

import json

from hireloop_api.config import Settings
from hireloop_api.services.match_rationale import (
    _parse_matches,
    generate_match_rationales,
)

_CANDIDATE = {
    "current_title": "Backend Engineer",
    "years_experience": 4,
    "skills": ["python", "django", "postgres"],
    "location_city": "Bengaluru",
    "location_state": "Karnataka",
    "expected_ctc_min": 2_000_000,
}


def _jobs() -> list[dict]:
    return [
        {
            "job_id": "j1",
            "title": "Senior Backend Engineer",
            "company_name": "Acme",
            "skills_required": ["python"],
        },
        {
            "job_id": "j2",
            "title": "Platform Engineer",
            "company_name": "Bolt",
            "skills_required": ["go"],
        },
    ]


def _settings() -> Settings:
    # No OpenRouter key — exercises the injected-llm path without network.
    return Settings(environment="development", openrouter_api_key="")


def _fake_llm(payload: dict):
    async def _complete(system: str, user: str) -> str:
        return json.dumps(payload)

    return _complete


# ── parsing ──────────────────────────────────────────────────────────────────


def test_parse_matches_handles_code_fences() -> None:
    raw = '```json\n{"matches": [{"job_id": "j1", "reason": "Great fit."}]}\n```'
    assert _parse_matches(raw) == {"j1": "Great fit."}


def test_parse_matches_returns_empty_on_garbage() -> None:
    assert _parse_matches("not json at all") == {}
    assert _parse_matches("") == {}


# ── generation ───────────────────────────────────────────────────────────────


async def test_generate_returns_reason_per_job() -> None:
    llm = _fake_llm(
        {
            "matches": [
                {
                    "job_id": "j1",
                    "reason": "Your Python/Django + 4 yrs match this senior role in Bengaluru.",
                },
                {"job_id": "j2", "reason": "Strong backend base; you'd ramp on Go quickly."},
            ]
        }
    )
    out = await generate_match_rationales(_CANDIDATE, _jobs(), settings=_settings(), llm=llm)
    assert set(out) == {"j1", "j2"}
    assert "Python" in out["j1"]


async def test_generate_ignores_hallucinated_job_ids() -> None:
    llm = _fake_llm(
        {
            "matches": [
                {"job_id": "j1", "reason": "Real match."},
                {"job_id": "DOES_NOT_EXIST", "reason": "Hallucinated."},
            ]
        }
    )
    out = await generate_match_rationales(_CANDIDATE, _jobs(), settings=_settings(), llm=llm)
    assert out == {"j1": "Real match."}


async def test_generate_truncates_long_reasons() -> None:
    llm = _fake_llm({"matches": [{"job_id": "j1", "reason": "x" * 500}]})
    out = await generate_match_rationales(_CANDIDATE, _jobs(), settings=_settings(), llm=llm)
    assert len(out["j1"]) <= 200


async def test_generate_falls_back_to_empty_on_llm_error() -> None:
    async def _boom(system: str, user: str) -> str:
        raise RuntimeError("provider down")

    out = await generate_match_rationales(_CANDIDATE, _jobs(), settings=_settings(), llm=_boom)
    assert out == {}


async def test_generate_returns_empty_without_key_or_llm() -> None:
    # No injected llm and no OpenRouter key → no network call, empty result.
    out = await generate_match_rationales(_CANDIDATE, _jobs(), settings=_settings())
    assert out == {}


async def test_generate_returns_empty_for_no_jobs() -> None:
    called = False

    async def _spy(system: str, user: str) -> str:
        nonlocal called
        called = True
        return "{}"

    out = await generate_match_rationales(_CANDIDATE, [], settings=_settings(), llm=_spy)
    assert out == {}
    assert called is False  # never bothers the LLM when there's nothing to rank
