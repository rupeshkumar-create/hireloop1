"""
Multi-dimension job fit scoring (culture, career alignment, recommendation, salary).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hireloop_api.services.salary_benchmark import lookup_salary_benchmark


def _enrichment(cand_row: Mapping[str, Any]) -> dict[str, Any]:
    raw = cand_row.get("profile_enrichment")
    return raw if isinstance(raw, dict) else {}


def compute_culture_score(cand_row: Mapping[str, Any], job_row: Mapping[str, Any]) -> float:
    """Behavioral / logistics culture fit (0–1)."""
    score = 0.55
    enrich = _enrichment(cand_row)
    work_style = enrich.get("work_style") if isinstance(enrich.get("work_style"), dict) else {}
    remote_pref = str(cand_row.get("remote_preference") or "any").lower()
    job_remote = bool(job_row.get("is_remote"))

    if job_remote and remote_pref in ("remote", "any"):
        score += 0.2
    elif not job_remote and remote_pref == "onsite":
        score += 0.15
    elif not job_remote and remote_pref == "remote" and not cand_row.get("open_to_relocation"):
        score -= 0.25

    energizing = work_style.get("energizing_tasks") or []
    draining = work_style.get("draining_tasks") or []
    if energizing:
        score += 0.05
    if draining and job_row.get("title"):
        title_l = str(job_row["title"]).lower()
        if any(str(d).lower()[:12] in title_l for d in draining[:3] if d):
            score -= 0.1

    return round(min(1.0, max(0.0, score)), 4)


def compute_career_alignment(
    cand_row: Mapping[str, Any],
    job_row: Mapping[str, Any],
    *,
    title_aff: float | None = None,
) -> float:
    """Career direction alignment (0–1)."""
    base = title_aff if title_aff is not None else 0.5
    prioritized = cand_row.get("prioritized_title")
    looking_for = cand_row.get("looking_for")
    job_title = str(job_row.get("title") or "").lower()

    if prioritized and str(prioritized).lower() in job_title:
        base = max(base, 0.85)
    if looking_for and str(looking_for).lower() in job_title:
        base = max(base, 0.75)

    enrich = _enrichment(cand_row)
    goals = enrich.get("career_goals") or []
    if goals and job_title:
        if any(str(g).lower()[:8] in job_title for g in goals[:3] if g):
            base = max(base, 0.8)

    return round(min(1.0, max(0.0, base)), 4)


def compute_fit_recommendation(
    *,
    overall: float,
    loc_score: float,
    skills_sim: float,
    culture_score: float,
) -> str:
    """apply | stretch | skip — deal-breakers veto weak logistics."""
    if loc_score < 0.25:
        return "skip"
    if overall >= 0.65 and skills_sim >= 0.45:
        return "apply"
    if overall >= 0.45 or (overall >= 0.4 and culture_score >= 0.7):
        return "stretch"
    return "skip"


def build_triage_notes(
    *,
    fit_recommendation: str,
    skills_sim: float,
    exp_score: float,
    career_score: float,
    job_title: str,
) -> str:
    if fit_recommendation == "apply":
        return f"Strong fit for {job_title} — skills {round(skills_sim * 100)}%, career {round(career_score * 100)}%."
    if fit_recommendation == "stretch":
        gaps: list[str] = []
        if skills_sim < 0.55:
            gaps.append("skill gaps")
        if exp_score < 0.5:
            gaps.append("experience level")
        gap_txt = ", ".join(gaps) if gaps else "minor gaps"
        return f"Stretch role — {gap_txt}; worth exploring if motivated."
    return f"Low fit for {job_title} — consider skipping unless you have a strong referral."


def enrich_score_result(
    cand_row: Mapping[str, Any],
    job_row: Mapping[str, Any],
    result: dict[str, Any],
    *,
    title_aff: float | None = None,
) -> dict[str, Any]:
    """Attach culture, career, recommendation, salary benchmark to a score dict."""
    culture = compute_culture_score(cand_row, job_row)
    career = compute_career_alignment(cand_row, job_row, title_aff=title_aff)
    recommendation = compute_fit_recommendation(
        overall=float(result.get("overall") or 0.0),
        loc_score=float(result.get("loc_score") or 0.5),
        skills_sim=float(result.get("skills_sim") or 0.5),
        culture_score=culture,
    )
    salary_benchmark = lookup_salary_benchmark(job_row, cand_row)
    triage_notes = build_triage_notes(
        fit_recommendation=recommendation,
        skills_sim=float(result.get("skills_sim") or 0.5),
        exp_score=float(result.get("exp_score") or 0.5),
        career_score=career,
        job_title=str(job_row.get("title") or "this role"),
    )
    result["culture_score"] = culture
    result["career_alignment_score"] = career
    result["fit_recommendation"] = recommendation
    result["salary_benchmark"] = salary_benchmark
    result["triage_notes"] = triage_notes
    return result
