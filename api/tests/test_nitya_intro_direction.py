"""
Nitya only drives the HM cold-email pipeline. In-app intros (candidate↔recruiter)
and unregistered-recruiter invites are progressed elsewhere — Nitya must NOT run
HM enrichment on them (empty hm_id) or it would wrongly decline a valid request.

These exercise the direction guard in NityaIntroHandler.handle with no DB calls.
"""

from __future__ import annotations

import pytest

from hireloop_api.agents.nitya.agent import NityaIntroHandler
from hireloop_api.config import Settings


def _settings() -> Settings:
    return Settings(_env_file=None, environment="development", openrouter_api_key="test-key")  # type: ignore[call-arg]


def _handler() -> NityaIntroHandler:
    # db is unused on the skip path; pass None so any DB access would blow up loudly.
    return NityaIntroHandler(settings=_settings(), db=None)  # type: ignore[arg-type]


async def test_skips_candidate_to_recruiter_in_app() -> None:
    result = await _handler().handle(
        {"id": "11111111-1111-1111-1111-111111111111", "direction": "candidate_to_recruiter"}
    )
    assert result["skipped"] == "in_app_flow"
    assert result["direction"] == "candidate_to_recruiter"


async def test_skips_recruiter_to_candidate_in_app() -> None:
    result = await _handler().handle(
        {"id": "22222222-2222-2222-2222-222222222222", "direction": "recruiter_to_candidate"}
    )
    assert result["skipped"] == "in_app_flow"


async def test_missing_intro_id_still_errors_before_direction() -> None:
    result = await _handler().handle({"direction": "candidate_to_recruiter"})
    assert "error" in result


async def test_candidate_to_hm_is_not_skipped() -> None:
    # The HM path must fall through to the real pipeline. With db=None the first DB
    # call raises — proving it did NOT take the skip branch (which never touches db).
    with pytest.raises(Exception):
        await _handler().handle(
            {"id": "33333333-3333-3333-3333-333333333333", "direction": "candidate_to_hm"}
        )
