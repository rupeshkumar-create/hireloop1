from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from hireloop_api.services.learning_roadmap import generate_roadmap, render_roadmap_html


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=self.content)


def _profile() -> dict[str, Any]:
    return {
        "full_name": "Asha Rao",
        "current_title": "Growth Manager",
        "skills": ["SQL", "Lifecycle Marketing"],
        "career_goals": {"desired_title": "Head of Growth"},
    }


def _job() -> dict[str, Any]:
    return {
        "title": "Head of Growth",
        "company_name": "Modern SaaS",
        "skills_required": ["SQL", "Experimentation"],
        "description": "Own growth experiments and lifecycle strategy.",
    }


@pytest.mark.asyncio
async def test_learning_roadmap_repairs_placeholder_llm_json() -> None:
    roadmap = await generate_roadmap(
        llm=_FakeLLM(
            json.dumps(
                {
                    "summary": "null",
                    "target_role": "undefined",
                    "current_strengths": ["SQL", "null"],
                    "gaps": ["undefined"],
                    "phases": [],
                    "stretch_goals": ["none"],
                }
            )
        ),  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job=_job(),
    )

    assert roadmap["summary"] != "null"
    assert roadmap["target_role"] == "Head of Growth"
    assert roadmap["current_strengths"] == ["SQL", "Lifecycle Marketing"]
    assert roadmap["gaps"] == ["Experimentation"]
    assert len(roadmap["phases"]) >= 3
    assert all(phase["milestones"] for phase in roadmap["phases"])

    html = render_roadmap_html(
        roadmap,
        job_title="Head of Growth",
        company_name="Modern SaaS",
        candidate_name="Asha Rao",
        storage_key="roadmap-test",
    )
    assert "No phases generated" not in html
    assert "null" not in html.lower()
    assert "undefined" not in html.lower()


@pytest.mark.asyncio
async def test_learning_roadmap_preserves_useful_llm_phases() -> None:
    roadmap = await generate_roadmap(
        llm=_FakeLLM(
            json.dumps(
                {
                    "summary": "A practical plan for growth leadership.",
                    "target_role": "Head of Growth",
                    "current_strengths": ["SQL"],
                    "gaps": ["Experimentation"],
                    "phases": [
                        {
                            "title": "Phase 1: Growth analytics",
                            "duration": "Weeks 1-2",
                            "focus": "Deepen SQL-driven funnel analysis.",
                            "milestones": ["Audit one lifecycle funnel."],
                            "skills": ["SQL", "Lifecycle Marketing"],
                            "resources": [{"label": "SQL practice", "note": "Use real funnels."}],
                        },
                        {
                            "title": "Phase 2: Experiment design",
                            "duration": "Weeks 3-4",
                            "focus": "Design and score experiments.",
                            "milestones": ["Write three experiment briefs."],
                            "skills": ["Experimentation"],
                            "resources": [],
                        },
                        {
                            "title": "Phase 3: Leadership capstone",
                            "duration": "Weeks 5-6",
                            "focus": "Package a growth strategy.",
                            "milestones": ["Build a 90-day growth plan."],
                            "skills": ["Growth Strategy"],
                            "resources": [],
                        },
                    ],
                    "stretch_goals": ["Create a growth portfolio."],
                }
            )
        ),  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job=_job(),
    )

    assert roadmap["summary"] == "A practical plan for growth leadership."
    assert [phase["title"] for phase in roadmap["phases"]] == [
        "Phase 1: Growth analytics",
        "Phase 2: Experiment design",
        "Phase 3: Leadership capstone",
    ]
    assert roadmap["phases"][0]["milestones"] == ["Audit one lifecycle funnel."]
    assert roadmap["stretch_goals"] == ["Create a growth portfolio."]
