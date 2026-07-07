"""Explainable match-quality audit signals.

This sits beside the scorer/gates: it does not change ranking by itself. It
records why a job was accepted or would be rejected, using the same deterministic
signals as the match quality layer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hireloop_api.services.domain_fit import detect_domains, domain_fit_multiplier
from hireloop_api.services.match_quality import (
    MIN_DOMAIN_MULTIPLIER_POOL,
    MIN_PERSIST_SCORE,
    PATH_ALIGNED_MIN_AFFINITY,
    PATH_ALIGNED_MIN_PERSIST,
    _skill_overlap_score,
    candidate_role_titles,
)
from hireloop_api.services.titles import title_affinity


class MatchQualityAudit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    signals: dict[str, float | None] = Field(default_factory=dict)
    thresholds: dict[str, float] = Field(default_factory=dict)


def audit_match_quality(
    candidate: Mapping[str, Any],
    job: Mapping[str, Any],
    result: Mapping[str, Any],
) -> MatchQualityAudit:
    """Return deterministic accept/reject diagnostics for a candidate/job pair."""
    overall = float(result.get("overall") or result.get("overall_score") or 0.0)
    titles = candidate_role_titles(candidate)
    title_score = _best_title_affinity(job.get("title"), titles)
    skill_score = _skill_overlap_score(
        list(candidate.get("skills") or []),
        list(job.get("skills_required") or []),
    )
    domain_multiplier = _domain_multiplier(candidate, job)
    path_aligned = title_score is not None and title_score >= PATH_ALIGNED_MIN_AFFINITY
    floor = PATH_ALIGNED_MIN_PERSIST if path_aligned else MIN_PERSIST_SCORE
    role_signal = max(title_score or 0.0, skill_score or 0.0)

    reasons: list[str] = []
    if overall < floor:
        reasons.append("below_score_floor")
    if domain_multiplier < MIN_DOMAIN_MULTIPLIER_POOL:
        reasons.append("domain_mismatch")
    if role_signal < 0.15:
        reasons.append("weak_role_signal")

    return MatchQualityAudit(
        accepted=not reasons,
        reasons=reasons,
        signals={
            "overall": round(overall, 4),
            "title_affinity": round(title_score, 4) if title_score is not None else None,
            "skill_overlap": round(skill_score, 4) if skill_score is not None else None,
            "domain_multiplier": round(domain_multiplier, 4),
            "role_signal": round(role_signal, 4),
        },
        thresholds={
            "score_floor": round(floor, 4),
            "domain_multiplier_floor": MIN_DOMAIN_MULTIPLIER_POOL,
            "role_signal_floor": 0.15,
        },
    )


def _best_title_affinity(job_title: Any, candidate_titles: list[str]) -> float | None:
    scores = [
        score
        for title in candidate_titles
        if (score := title_affinity(title, job_title)) is not None
    ]
    return max(scores) if scores else None


def _domain_multiplier(candidate: Mapping[str, Any], job: Mapping[str, Any]) -> float:
    cand_domains = detect_domains(
        title=candidate.get("current_title"),
        company=candidate.get("current_company"),
        skills=list(candidate.get("skills") or []),
        extra=candidate.get("headline") or candidate.get("summary"),
    )
    job_domains = detect_domains(
        title=job.get("title"),
        company=job.get("company_name"),
        skills=list(job.get("skills_required") or []),
        extra=job.get("description"),
    )
    return domain_fit_multiplier(cand_domains, job_domains)
