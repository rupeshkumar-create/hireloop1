"""
Skill canonicalization (#21): alias variants must count as the SAME skill in
matching, instead of diluting overlap scores.
"""

from __future__ import annotations

from hireloop_api.services.matching import _skill_overlap_score
from hireloop_api.services.skills import canonical_skill, canonical_skill_set


def test_aliases_collapse() -> None:
    assert canonical_skill("ReactJS") == canonical_skill("react.js") == "react"
    assert canonical_skill("K8s") == canonical_skill("Kubernetes") == "kubernetes"
    assert canonical_skill("Postgres") == canonical_skill("PostgreSQL") == "postgresql"
    assert canonical_skill("Node") == canonical_skill("Node.js") == "nodejs"
    assert canonical_skill("JS") == "javascript"


def test_distinct_skills_stay_distinct() -> None:
    assert canonical_skill("C++") != canonical_skill("C#")
    assert canonical_skill("java") != canonical_skill("javascript")


def test_canonical_set_dedupes() -> None:
    assert canonical_skill_set(["React", "ReactJS", "react.js"]) == {"react"}
    assert canonical_skill_set(None) == set()
    assert canonical_skill_set(["", "  "]) == set()


def test_overlap_score_counts_aliases_as_hits() -> None:
    # Candidate writes variants; job lists canonical names. Without the alias
    # map this scored as 0 overlap — now it must be a perfect skill match.
    score = _skill_overlap_score(
        ["ReactJS", "Node", "Postgres", "K8s"],
        ["react", "nodejs", "postgresql", "kubernetes"],
    )
    assert score == 1.0


def test_overlap_score_still_penalises_real_misses() -> None:
    score = _skill_overlap_score(["ReactJS"], ["java", "spring", "hibernate"])
    assert score is not None and score < 0.2
