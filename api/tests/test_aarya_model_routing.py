"""
Tests for Aarya's per-turn model routing (latency).

The heavy primary model is reserved for tool-selection / reasoning turns;
short conversational turns, voice turns, and the post-tool summarisation pass
use the fast/cheap model. These are pure decisions — no LLM, no network.
"""

from __future__ import annotations

from hireloop_api.agents.aarya.agent import _detect_likely_intent, _prefer_fast_model


def test_voice_tool_selection_uses_primary_model() -> None:
    assert not _prefer_fast_model(
        voice_mode=True, last_human_text="find me backend jobs", has_tool_results=False
    )


def test_voice_synthesis_uses_fast_model() -> None:
    assert _prefer_fast_model(
        voice_mode=True, last_human_text="find me backend jobs", has_tool_results=True
    )


def test_tool_result_summarisation_uses_fast_model() -> None:
    # General chat after tools still uses the fast model.
    assert _prefer_fast_model(
        voice_mode=False, last_human_text="thanks, that helps", has_tool_results=True
    )


def test_job_search_post_tool_uses_primary_model() -> None:
    assert not _prefer_fast_model(
        voice_mode=False, last_human_text="find me backend jobs", has_tool_results=True
    )


def test_job_search_turn_uses_primary_model() -> None:
    assert not _prefer_fast_model(
        voice_mode=False, last_human_text="find backend engineer jobs", has_tool_results=False
    )


def test_intro_turn_uses_primary_model() -> None:
    assert not _prefer_fast_model(
        voice_mode=False,
        last_human_text="can you connect me with the hiring manager?",
        has_tool_results=False,
    )


def test_general_chat_uses_fast_model() -> None:
    assert _prefer_fast_model(
        voice_mode=False, last_human_text="hi, can you help me?", has_tool_results=False
    )


def test_preference_statement_uses_fast_model() -> None:
    # "expected ctc 20 lpa" → preference_update intent → fast.
    assert _detect_likely_intent("my expected ctc is 20 lpa") == "preference_update"
    assert _prefer_fast_model(
        voice_mode=False, last_human_text="my expected ctc is 20 lpa", has_tool_results=False
    )


def test_job_application_intent_detected() -> None:
    assert (
        _detect_likely_intent(
            "I want to apply for Senior Engineer at Acme. "
            "Prepare my full application kit for job abc-123."
        )
        == "job_application"
    )
    assert not _prefer_fast_model(
        voice_mode=False,
        last_human_text="I want to apply for this role",
        has_tool_results=False,
    )


def test_profile_improvement_not_job_search() -> None:
    assert (
        _detect_likely_intent("What should I add to improve my match quality?")
        == "profile_improvement"
    )
    assert not _prefer_fast_model(
        voice_mode=False,
        last_human_text="What should I add to improve my match quality?",
        has_tool_results=False,
    )


def test_profile_post_tool_uses_primary_model() -> None:
    assert not _prefer_fast_model(
        voice_mode=False,
        last_human_text="What should I add to improve my match quality?",
        has_tool_results=True,
    )


def test_default_models_are_valid_openrouter_ids() -> None:
    # Regression guard: `claude-haiku-latest` was NOT a valid OpenRouter model ID
    # and 400'd on every fast-routed turn. Pin the known-good defaults.
    from hireloop_api.config import Settings

    s = Settings(_env_file=None, environment="development")  # type: ignore[call-arg]
    assert s.openrouter_primary_model == "anthropic/claude-opus-4.7"
    assert s.openrouter_fallback_model == "anthropic/claude-haiku-4.5"
    assert s.openrouter_free_model == "openrouter/free"
    assert s.openrouter_chat_max_tokens <= 700
    assert s.openrouter_low_credit_max_tokens <= 256
    for model in (s.openrouter_primary_model, s.openrouter_fallback_model):
        assert model.startswith("anthropic/")
        assert "latest" not in model  # the one that broke (claude-haiku-latest)
