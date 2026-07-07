from __future__ import annotations

import json

from hireloop_api.config import Settings
from hireloop_api.services import application_kit
from hireloop_api.services.ai_context import build_candidate_context_block, compose_candidate_prompt
from hireloop_api.services.learning_roadmap import generate_roadmap
from hireloop_api.services.match_rationale import generate_match_rationales
from hireloop_api.services.resume_tailor import generate_tailored_html


def _profile() -> dict:
    return {
        "full_name": "Asha Rao",
        "current_title": "Senior Growth Manager",
        "looking_for": "Head of Growth roles in SaaS",
        "skills": ["Lifecycle Marketing", "SQL", "Experimentation"],
        "career_goals": {
            "desired_title": "Head of Growth",
            "desired_industry": "B2B SaaS",
            "work_mode": "Remote",
        },
        "source_note": "All employers, titles, dates, education, and metrics MUST match this profile exactly.",
        "experience": [{"title": "Growth Lead", "company": "Acme SaaS"}],
        "education": [{"degree": "MBA", "institution": "IIM Bangalore"}],
        "latest_resume_file_name": "asha-resume.pdf",
        "source_inventory": {"resume": True, "memory": True, "career_path": True},
        "memory_summary": "Prefers remote-first SaaS growth leadership.",
        "career_facts": {"desired_title": "Head of Growth"},
    }


def test_candidate_context_block_includes_memory_goals_resume_and_rules() -> None:
    block = build_candidate_context_block(_profile(), task="tailored_resume")

    assert "AI CONTEXT CONTRACT" in block
    assert "Head of Growth" in block
    assert "B2B SaaS" in block
    assert "Prefers remote-first SaaS" in block
    assert "asha-resume.pdf" in block
    assert "All employers, titles, dates" in block
    assert "Do not invent missing facts" in block
    assert len(block) <= 8000


def test_compose_candidate_prompt_puts_context_before_task() -> None:
    prompt = compose_candidate_prompt(
        _profile(),
        task="application_kit",
        task_prompt="Job:\nHead of Growth at Modern SaaS",
    )

    assert prompt.index("AI CONTEXT CONTRACT") < prompt.index("TASK INPUT")
    assert "Head of Growth at Modern SaaS" in prompt


class _CaptureLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages: object | None = None

    async def ainvoke(self, messages: object) -> object:
        self.messages = messages

        class _Resp:
            def __init__(self, content: str) -> None:
                self.content = content

        return _Resp(self.content)


def _human_content(llm: _CaptureLLM) -> str:
    messages = list(llm.messages or [])  # type: ignore[arg-type]
    return str(messages[-1].content)


async def test_tailored_resume_prompt_uses_candidate_context_contract() -> None:
    llm = _CaptureLLM("<h1>Asha Rao</h1><p>Growth leader.</p>")

    await generate_tailored_html(
        llm=llm,  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job={"title": "Head of Growth", "company_name": "Modern SaaS", "description": "SQL"},
        template="modern",
    )

    prompt = _human_content(llm)
    assert prompt.startswith("AI CONTEXT CONTRACT")
    assert prompt.index("AI CONTEXT CONTRACT") < prompt.index("TASK INPUT")
    assert "Prefers remote-first SaaS" in prompt
    assert "Head of Growth" in prompt


async def test_application_kit_prompt_uses_candidate_context_contract(monkeypatch) -> None:
    llm = _CaptureLLM(
        json.dumps(
            {
                "cover_letter": "Dear team, Asha is a fit.",
                "interview_prep": "## Likely questions",
            }
        )
    )
    monkeypatch.setattr(application_kit, "_kit_llm", lambda *args, **kwargs: llm)

    await application_kit._generate_text_assets(
        settings=Settings(_env_file=None, openrouter_api_key="test-key"),  # type: ignore[call-arg]
        profile=_profile(),
        job={"title": "Head of Growth", "company_name": "Modern SaaS", "description": "SQL"},
    )

    prompt = _human_content(llm)
    assert prompt.startswith("AI CONTEXT CONTRACT")
    assert "TASK INPUT" in prompt
    assert "asha-resume.pdf" in prompt


async def test_learning_roadmap_prompt_uses_candidate_context_contract() -> None:
    llm = _CaptureLLM(
        json.dumps(
            {
                "summary": "Plan",
                "target_role": "Head of Growth",
                "current_strengths": [],
                "gaps": [],
                "phases": [],
                "stretch_goals": [],
            }
        )
    )

    await generate_roadmap(
        llm=llm,  # type: ignore[arg-type]
        candidate_profile=_profile(),
        job={"title": "Head of Growth", "company_name": "Modern SaaS", "description": "SQL"},
    )

    prompt = _human_content(llm)
    assert prompt.startswith("AI CONTEXT CONTRACT")
    assert "learning_roadmap" in prompt
    assert "TASK INPUT" in prompt


async def test_match_rationale_prompt_uses_candidate_context_contract() -> None:
    captured: dict[str, str] = {}

    async def _fake_llm(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return json.dumps({"matches": [{"job_id": "j1", "reason": "Strong fit."}]})

    out = await generate_match_rationales(
        _profile(),
        [{"job_id": "j1", "title": "Head of Growth", "company_name": "Modern SaaS"}],
        settings=Settings(_env_file=None, openrouter_api_key=""),  # type: ignore[call-arg]
        llm=_fake_llm,
    )

    assert out == {"j1": "Strong fit."}
    assert captured["user"].startswith("AI CONTEXT CONTRACT")
    assert "match_rationale" in captured["user"]
    assert "TASK INPUT" in captured["user"]
