"""Tests for profile-improvement reply helpers in chat routes."""

from __future__ import annotations

from hireloop_api.routes.chat import (
    _agent_message_text,
    _build_profile_gap_reply,
    _looks_incomplete_profile_reply,
)


def test_agent_message_text_from_blocks() -> None:
    content = [{"type": "text", "text": "Hello "}, {"type": "text", "text": "world"}]
    assert _agent_message_text(content) == "Hello world"


def test_incomplete_profile_reply_detects_preamble_only() -> None:
    assert _looks_incomplete_profile_reply(
        "Let me pull your profile so I can point to exactly what's missing."
    )


def test_complete_profile_reply_not_flagged() -> None:
    text = (
        "**What I found**\n"
        "Your CTC and skills are missing.\n\n"
        "**What I recommend**\n"
        "1. Add expected CTC in LPA.\n"
    )
    assert not _looks_incomplete_profile_reply(text)


def test_profile_gap_fallback_uses_open_questions() -> None:
    reply = _build_profile_gap_reply(["What total compensation are you targeting (in LPA)?"])
    assert "What I recommend" in reply
    assert "LPA" in reply
