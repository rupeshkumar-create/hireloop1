"""
Aarya chat memory & context (HIR-44): captured career_facts must be surfaced into
the turn context so Aarya relies on them instead of re-asking.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from hireloop_api.agents.aarya.agent import build_turn_context_prompt
from hireloop_api.services.memory import format_known_facts


def test_format_known_facts_empty() -> None:
    assert format_known_facts({}) == ""
    assert format_known_facts(None) == ""  # type: ignore[arg-type]


def test_format_known_facts_renders_labels_and_skips_blanks() -> None:
    out = format_known_facts(
        {
            "preferred_name": "Rupesh",
            "desired_title": "Product Manager",
            "work_mode": "Hybrid",
            "visa_status": None,  # skipped
            "citizenship": "  ",  # blank → skipped
        }
    )
    assert "preferred name: Rupesh" in out
    assert "target role: Product Manager" in out
    assert "work mode: Hybrid" in out
    assert "visa" not in out
    assert "citizenship" not in out


def test_format_known_facts_joins_lists() -> None:
    out = format_known_facts({"industry_preference": ["fintech", "saas", "  "]})
    assert "industries of interest: fintech, saas" in out


def test_format_known_facts_respects_max_chars() -> None:
    out = format_known_facts({"preferred_name": "x" * 1000}, max_chars=50)
    assert len(out) == 50


def test_turn_context_injects_known_facts() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="hi")],
        voice_mode=False,
        memory="",
        open_questions=[],
        known_facts="preferred name: Rupesh; work mode: Hybrid",
    )
    assert "known_facts" in prompt
    assert "do NOT" in prompt
    assert "Rupesh" in prompt


def test_turn_context_omits_known_facts_when_empty() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="hi")],
        voice_mode=False,
        memory="",
        open_questions=[],
        known_facts="",
    )
    assert "known_facts" not in prompt


def test_format_known_facts_uses_canonical_name() -> None:
    out = format_known_facts(
        {"preferred_name": "Kavya", "work_mode": "Remote"},
        canonical_name="Vivek Kumar",
    )
    assert "preferred name: Vivek Kumar" in out
    assert "Kavya" not in out


def test_turn_context_includes_authoritative_candidate_name() -> None:
    prompt = build_turn_context_prompt(
        messages=[HumanMessage(content="hello")],
        voice_mode=False,
        memory="",
        open_questions=[],
        candidate_display_name="Vivek Kumar",
    )
    assert "candidate_name: Vivek Kumar" in prompt
    assert "authoritative" in prompt
