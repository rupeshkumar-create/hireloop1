"""Reusable candidate context contract for LLM calls.

This module does not call an LLM. It prepares a compact, source-aware context
block so candidate-facing generators consume memory, goals, resume facts, and
task rules before the task-specific prompt.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_CONTEXT_CHARS = 8000


def build_candidate_context_block(
    candidate_profile: dict[str, Any],
    *,
    task: str,
    max_chars: int = _MAX_CONTEXT_CHARS,
) -> str:
    """Build the required candidate context block for a task-specific LLM prompt."""
    profile = candidate_profile or {}
    context = {
        "identity": {
            "full_name": profile.get("full_name"),
            "current_title": profile.get("current_title"),
            "current_company": profile.get("current_company"),
            "years_experience": profile.get("years_experience"),
            "location_city": profile.get("location_city"),
            "location_state": profile.get("location_state"),
        },
        "goals": profile.get("career_goals") or _goals_from_flat_profile(profile),
        "memory": {
            "summary": profile.get("memory_summary") or profile.get("candidate_memory") or "",
            "career_facts": profile.get("career_facts") or {},
        },
        "preferences": {
            "looking_for": profile.get("looking_for"),
            "expected_ctc_min": profile.get("expected_ctc_min"),
            "expected_ctc_max": profile.get("expected_ctc_max"),
            "notice_period_days": profile.get("notice_period_days"),
        },
        "skills": _list(profile.get("skills"))[:30],
        "experience": _list(profile.get("experience"))[:12],
        "education": _list(profile.get("education"))[:8],
        "source_inventory": profile.get("source_inventory") or {},
        "latest_resume_file_name": profile.get("latest_resume_file_name"),
        "source_note": profile.get("source_note"),
    }
    rules = _task_rules(task)
    payload = json.dumps(context, default=str, ensure_ascii=False, indent=2)
    block = (
        "AI CONTEXT CONTRACT\n"
        f"Task: {task}\n"
        "Use this context before producing the answer. Treat it as the candidate-owned source of truth.\n"
        f"{rules}\n\n"
        f"Candidate context JSON:\n{payload}"
    )
    return block[:max_chars]


def compose_candidate_prompt(
    candidate_profile: dict[str, Any],
    *,
    task: str,
    task_prompt: str,
) -> str:
    """Put candidate context before task input for candidate-facing LLM calls."""
    return (
        f"{build_candidate_context_block(candidate_profile, task=task)}\n\n"
        "TASK INPUT\n"
        f"{task_prompt.strip()}"
    )


def _task_rules(task: str) -> str:
    common = (
        "- Do not invent missing facts.\n"
        "- Preserve employers, titles, dates, education, credentials, and metrics exactly.\n"
        "- Use goals, memory, preferences, and resume facts to adapt the output."
    )
    if task in {"tailored_resume", "path_resume"}:
        return (
            f"{common}\n"
            "- For resume output, include every source role and degree unless the context is empty.\n"
            "- Rewrite positioning and bullets only where truthful."
        )
    if task == "application_kit":
        return (
            f"{common}\n"
            "- Cover letters and prep must be job-specific, truthful, and grounded in candidate facts."
        )
    if task == "learning_roadmap":
        return (
            f"{common}\n"
            "- Build skill gaps from candidate facts vs the target job; do not assume hidden experience."
        )
    if task == "match_rationale":
        return (
            f"{common}\n"
            "- Explain fit using concrete overlap and gaps; never overstate weak evidence."
        )
    return common


def _goals_from_flat_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "desired_title": profile.get("desired_title") or profile.get("looking_for"),
        "desired_industry": profile.get("desired_industry"),
        "work_mode": profile.get("work_mode"),
    }


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
