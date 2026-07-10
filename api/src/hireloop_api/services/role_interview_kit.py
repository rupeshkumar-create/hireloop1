"""
Recruiter-facing interview kit generated from role brief.
Template-based (deterministic) — works without LLM.
"""

from __future__ import annotations

import json
from typing import Any


def _parse_list(val: object | None) -> list[str]:
    if isinstance(val, list):
        return [str(x) for x in val if x]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return [str(x) for x in parsed if x] if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _parse_criteria(val: object | None) -> list[dict[str, Any]]:
    if isinstance(val, list):
        return [x for x in val if isinstance(x, dict)]
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return [x for x in parsed if isinstance(x, dict)] if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def generate_interview_kit(role: dict[str, Any]) -> dict[str, Any]:
    """Build structured interview kit from role fields."""
    title = (role.get("title") or "Role").strip()
    must_haves = _parse_list(role.get("must_haves"))
    nice = _parse_list(role.get("nice_to_haves"))
    criteria = _parse_criteria(role.get("evaluation_criteria"))
    brief = (role.get("hiring_brief") or "").strip()

    stages = [
        {
            "name": "Recruiter screen",
            "duration_minutes": 30,
            "goal": "Validate motivation, comp alignment, and must-have basics",
            "questions": [
                f"What attracted you to this {title} role?",
                "Walk me through your most relevant recent project.",
                "What are your compensation expectations and notice period?",
            ],
        },
        {
            "name": "Technical / skills deep-dive",
            "duration_minutes": 60,
            "goal": "Assess core skills against must-haves",
            "questions": _skill_questions(must_haves),
        },
        {
            "name": "Hiring manager interview",
            "duration_minutes": 45,
            "goal": "Evaluate judgment, collaboration, and role fit",
            "questions": [
                "Describe a time you disagreed with a stakeholder. How did you resolve it?",
                "What would you accomplish in your first 90 days?",
                "What questions do you have about the team and role?",
            ],
        },
    ]

    scorecard = []
    for c in criteria[:6]:
        name = c.get("criterion") or "Criterion"
        weight = c.get("weight", 0)
        scorecard.append(
            {
                "criterion": name,
                "weight": weight,
                "rubric": {
                    "1": f"No evidence of {name.lower()}",
                    "3": f"Adequate demonstration of {name.lower()}",
                    "5": f"Strong, concrete examples of {name.lower()}",
                },
            }
        )
    if not scorecard and must_haves:
        for skill in must_haves[:5]:
            scorecard.append(
                {
                    "criterion": skill,
                    "weight": round(100 / min(len(must_haves), 5)),
                    "rubric": {
                        "1": f"Cannot demonstrate {skill}",
                        "3": f"Working knowledge of {skill}",
                        "5": f"Expert-level {skill} with examples",
                    },
                }
            )

    red_flags = [
        "Vague answers with no concrete examples",
        "Misalignment on compensation or notice period",
        "Cannot explain their own resume claims",
    ]
    if must_haves:
        red_flags.append(f"Missing experience in core must-haves: {', '.join(must_haves[:3])}")

    return {
        "role_title": title,
        "summary": brief[:300] if brief else f"Interview plan for {title}",
        "stages": stages,
        "scorecard": scorecard,
        "nice_to_probe": nice[:5],
        "red_flags": red_flags,
        "generated_from": "brief",
    }


def _skill_questions(skills: list[str]) -> list[str]:
    if not skills:
        return [
            "Describe the most complex problem you solved in your last role.",
            "How do you approach learning a new technology or domain?",
        ]
    questions = []
    for skill in skills[:4]:
        questions.append(
            f"Tell me about a project where you used {skill}. What was your specific contribution?"
        )
    questions.append("What trade-offs did you consider in that project?")
    return questions
