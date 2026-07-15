"""Regression coverage for job-card 'Why this match' chat turns."""

from __future__ import annotations

import uuid

from hireloop_api.routes.chat import (
    SendMessageRequest,
    _build_match_explanation_reply,
    _match_explanation_job_id,
)


def test_structured_job_id_stays_out_of_visible_message() -> None:
    job_id = uuid.UUID("524c5c60-498c-4dec-bb59-2b3ee98525ed")
    body = SendMessageRequest(
        content="Why is Associate Manager at PepsiCo a fit for me?",
        job_id=job_id,
    )

    assert str(job_id) not in body.content
    assert _match_explanation_job_id(body, "match_explanation") == str(job_id)


def test_legacy_visible_job_id_is_still_supported() -> None:
    job_id = "524c5c60-498c-4dec-bb59-2b3ee98525ed"
    body = SendMessageRequest(content=f"Why is this a fit for me? Use job id {job_id}.")

    assert _match_explanation_job_id(body, "match_explanation") == job_id


def test_match_reply_is_specific_and_has_no_unrelated_search_copy() -> None:
    reply = _build_match_explanation_reply(
        {
            "job_title": "Associate Manager - Revenue Growth Management",
            "company_name": "PepsiCo, Inc.",
            "overall_score": 58.2,
            "skills_score": 61.0,
            "experience_score": 72.0,
            "location_score": 100.0,
            "ctc_score": 50.0,
            "explanation": "Your experience aligns, but some role-specific skills are missing.",
        }
    )

    assert "58% match" in reply
    assert "PepsiCo, Inc." in reply
    assert "Skills: **61%**" in reply
    assert "Head of Content" not in reply
    assert "roles found" not in reply
