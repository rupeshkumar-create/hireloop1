from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from hireloop_api.config import Settings
from hireloop_api.services import application_kit
from hireloop_api.services.outcome_learning import build_kit_aware_interview_prep


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content

    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=self.content)


def _profile() -> dict[str, Any]:
    return {
        "full_name": "Asha Rao",
        "current_title": "Growth Manager",
        "current_company": "Acme SaaS",
        "skills": ["SQL", "Lifecycle Marketing"],
    }


def _job() -> dict[str, Any]:
    return {
        "title": "Head of Growth",
        "company_name": "Modern SaaS",
        "skills_required": ["SQL", "Experimentation"],
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"star_stories": ["Launch"]}, {"star_stories": ["Launch"]}),
        ('{"star_stories":["Launch"]}', {"star_stories": ["Launch"]}),
        ("not-json", {}),
        (["wrong-shape"], {}),
        (None, {}),
    ],
)
def test_coerce_json_object(value: object, expected: dict[str, object]) -> None:
    assert application_kit._coerce_json_object(value) == expected


def test_interview_prep_ignores_string_profile_enrichment() -> None:
    out = build_kit_aware_interview_prep(
        base_prep="## Likely questions",
        dossier=None,
        job={"title": "Growth Lead", "company_name": "Acme"},
        profile={"profile_enrichment": '{"star_stories":["Launch"]}'},
    )

    assert "## Role focus" in out


@pytest.mark.asyncio
async def test_application_kit_text_assets_repair_placeholder_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _FakeLLM(
        json.dumps(
            {
                "cover_letter": "null",
                "interview_prep": "undefined\n\n## Likely questions\n- null",
            }
        )
    )
    monkeypatch.setattr(application_kit, "_kit_llm", lambda *args, **kwargs: llm)

    cover, prep = await application_kit._generate_text_assets(
        settings=Settings(_env_file=None, openrouter_api_key="test-key"),  # type: ignore[call-arg]
        profile=_profile(),
        job=_job(),
    )

    assert "null" not in cover.lower()
    assert "undefined" not in prep.lower()
    assert "Dear Hiring Team at Modern SaaS" in cover
    assert "## Likely questions" in prep
    assert "## STAR stories to rehearse" in prep
    assert "## Role-specific talking points" in prep
    assert "## Questions to ask them" in prep


def test_application_kit_text_assets_preserve_useful_llm_output() -> None:
    cover = (
        "Dear Hiring Team at Modern SaaS,\n\n"
        "I am excited to apply for the Head of Growth role. My Growth Manager experience "
        "at Acme SaaS spans lifecycle marketing, SQL analysis, experimentation, and "
        "cross-functional launch work that maps closely to the role requirements.\n\n"
        "I would welcome the opportunity to discuss how I can help the team grow."
    )
    prep = (
        "## Likely questions\n- How have you used SQL for growth?\n\n"
        "## STAR stories to rehearse\n- Lifecycle launch story.\n\n"
        "## Role-specific talking points\n- Experiment design and retention.\n\n"
        "## Questions to ask them\n- What growth loops are working today?"
    )

    out_cover, out_prep = application_kit.normalize_application_text_assets(
        cover_letter=cover,
        interview_prep=prep,
        profile=_profile(),
        job=_job(),
    )

    assert "Dear Hiring Team at Modern SaaS" in out_cover
    assert "Growth Manager experience at Acme SaaS" in out_cover
    assert "I am writing to express my interest" not in out_cover
    assert "How have you used SQL for growth?" in out_prep
    assert "Lifecycle launch story." in out_prep
    assert "Experiment design and retention." in out_prep
    assert "What growth loops are working today?" in out_prep
