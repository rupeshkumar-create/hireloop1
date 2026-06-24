"""Bundled skills vocabulary: whitelist, display labels, autocomplete."""

from __future__ import annotations

from hireloop_api.services.skills import (
    CANONICAL_SKILLS,
    display_skill,
    is_known_skill,
    suggest_skills,
)


def test_vocabulary_is_large() -> None:
    # Bundled taxonomy should carry the full curated set (~2000).
    assert len(CANONICAL_SKILLS) > 1500


def test_is_known_skill_recognises_real_and_rejects_junk() -> None:
    assert is_known_skill("python")
    assert is_known_skill("ReactJS")  # via alias
    assert is_known_skill("Kubernetes")
    assert not is_known_skill("i personally:")
    assert not is_known_skill("asdfqwerzxcv")


def test_display_skill_canonical_label() -> None:
    assert display_skill("postgres") == "PostgreSQL"
    assert display_skill("k8s") == "Kubernetes"
    # Unknown skill falls back to a title-cased label.
    assert display_skill("some niche tool") == "Some Niche Tool"


def test_suggest_prefix_then_substring() -> None:
    out = suggest_skills("kube", limit=5)
    assert "Kubernetes" in out
    assert all(isinstance(s, str) for s in out)
    assert suggest_skills("", limit=5) == []
    assert len(suggest_skills("e", limit=7)) <= 7
