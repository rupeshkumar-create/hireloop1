"""#30: JD enrichment parsing — validate + canonicalize LLM output."""

from __future__ import annotations

from hireloop_api.services.jd_enrichment import _parse_enrichment


def test_parses_clean_json() -> None:
    out = _parse_enrichment(
        '{"skills_required": ["Python", "ReactJS", "AWS"], '
        '"seniority": "senior", "ctc_min": 2500000, "ctc_max": 4000000}'
    )
    assert out is not None
    # Skills canonicalized to vocabulary display labels (reactjs -> React) + deduped.
    assert "React" in out["skills_required"]
    assert out["seniority"] == "senior"
    assert out["ctc_min"] == 2500000


def test_strips_markdown_fences() -> None:
    out = _parse_enrichment('```json\n{"skills_required": ["sql"], "seniority": null}\n```')
    assert out is not None and out["skills_required"] == ["SQL"]
    assert out["seniority"] is None


def test_invalid_seniority_nulled() -> None:
    out = _parse_enrichment('{"skills_required": [], "seniority": "wizard"}')
    assert out is not None and out["seniority"] is None


def test_implausible_ctc_rejected() -> None:
    # Bare "25" (LPA misread) or absurd values must not become a salary.
    out = _parse_enrichment('{"skills_required": ["x"], "ctc_min": 25, "ctc_max": 999999999999}')
    assert out is not None
    assert out["ctc_min"] is None and out["ctc_max"] is None


def test_garbage_returns_none() -> None:
    assert _parse_enrichment("not json") is None
    assert _parse_enrichment("") is None


def test_skill_artifacts_dropped() -> None:
    out = _parse_enrichment(
        '{"skills_required": ["product management", "i personally:", "languages"]}'
    )
    assert out is not None
    assert "Product Management" in out["skills_required"]
    assert "i personally:" not in out["skills_required"]
    assert "languages" not in out["skills_required"]
