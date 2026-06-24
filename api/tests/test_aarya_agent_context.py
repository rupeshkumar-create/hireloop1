from langchain_core.messages import HumanMessage

from hireloop_api.agents.aarya.agent import build_turn_context_prompt


def test_turn_context_prompt_marks_voice_mode_and_short_replies() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="I lead growth at a SaaS startup")],
        voice_mode=True,
        memory="Candidate wants Head of Growth roles.",
        open_questions=["What CTC range are you targeting?"],
    )

    assert "Current turn context" in prompt
    assert "mode: voice" in prompt
    assert "Keep the next reply short and spoken" in prompt
    assert "Head of Growth" in prompt
    assert "What CTC range are you targeting?" in prompt


def test_turn_context_prompt_grounds_profile_completeness() -> None:
    # Regression: chat text said "80% there" while the UI pill said "35% complete".
    # The prompt must surface the authoritative number and forbid inventing one.
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="What should I add to improve my match quality?")],
        voice_mode=False,
        memory="",
        open_questions=[],
        profile_completeness=35,
    )

    assert "profile_completeness: 35%" in prompt
    assert "verbatim" in prompt
    assert "never state a different or estimated percentage" in prompt


def test_turn_context_prompt_omits_completeness_when_unknown() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="hello")],
        voice_mode=False,
        memory="",
        open_questions=[],
        profile_completeness=None,
    )

    assert "profile_completeness" not in prompt


def test_turn_context_prompt_detects_job_search_intent() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="Find me remote Head of Growth jobs")],
        voice_mode=False,
        memory="",
        open_questions=[],
    )

    assert "likely_intent: job_search" in prompt
    assert "build_career_path before job_search" in prompt
    assert "remote" in prompt.lower()
