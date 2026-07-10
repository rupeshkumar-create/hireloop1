"""
Deterministic job retrieval pipeline.

Order of operations:
1. Role-family hard filter (intent titles only).
2. Title/skills lexical filter with occupation-family guard.
3. Raw-feature rerank (no nested composite double-count).
4. LLM rationale selection: only the final top 10 get rationale generation.
"""

from __future__ import annotations

from typing import Any

from hireloop_api.services.career_path_jobs import (
    job_matches_path_titles,
    normalize_path_search_titles,
    should_enforce_path_title_gate,
)
from hireloop_api.services.skills import canonical_skill
from hireloop_api.services.titles import (
    best_intent_title_affinity,
    evidence_titles,
    intent_titles,
    occupation_families_compatible,
    parse_title,
    title_affinity,
)

_ENGINEERING_SPECIALTIES = frozenset(
    {"backend", "frontend", "mobile", "fullstack", "devops", "quality", "reliability", "platform"}
)
_MIN_TITLE_AFFINITY = 0.35
_MIN_SKILL_SIGNAL = 0.35
_MIN_LLM_RATIONALE_JOBS = 10
_RANKING_MODEL_VERSION = "v2_feature_rerank"


def _candidate_intent_titles(candidate: dict[str, Any]) -> list[str]:
    return intent_titles(candidate)


def _candidate_evidence_titles(candidate: dict[str, Any]) -> list[str]:
    return evidence_titles(candidate)


def _candidate_required_specialties(titles: list[str]) -> frozenset[str]:
    out: set[str] = set()
    for title in titles:
        sig = parse_title(title)
        out.update(sig.specialties)
    return frozenset(out)


def _role_family_allowed(job: dict[str, Any], intent: list[str]) -> bool:
    if not intent:
        return True
    return occupation_families_compatible(intent, job.get("title"))


def _best_title_affinity_intent(job: dict[str, Any], candidate: dict[str, Any]) -> float:
    return best_intent_title_affinity(job.get("title"), candidate)


def _required_skill_coverage(job: dict[str, Any], candidate: dict[str, Any]) -> float:
    cand = {canonical_skill(str(s)) for s in candidate.get("skills") or [] if s}
    req = {canonical_skill(str(s)) for s in job.get("skills_required") or [] if s}
    if not cand or not req:
        return 0.0
    overlap = cand & req
    return round(len(overlap) / len(req), 4)


def _skill_signal(job: dict[str, Any], candidate: dict[str, Any]) -> float:
    cand = {canonical_skill(str(s)) for s in candidate.get("skills") or [] if s}
    req = {canonical_skill(str(s)) for s in job.get("skills_required") or [] if s}
    if not cand or not req:
        return 0.0
    overlap = cand & req
    if len(req) == 1 and len(cand) > 8:
        # Single generic skill must not rescue wrong occupation
        coverage = len(overlap) / len(req)
        return round(coverage * 0.4, 4) if coverage else 0.0
    coverage = len(overlap) / len(req)
    jaccard = len(overlap) / len(cand | req)
    return round(min(1.0, 0.85 * coverage + 0.15 * jaccard), 4)


def _occupation_mismatch(intent: list[str], job_title: str | None) -> bool:
    """True when high-confidence intent family conflicts with job family."""
    if not intent or not job_title:
        return False
    job_sig = parse_title(job_title)
    if not job_sig.family_id:
        return False
    for title in intent:
        sig = parse_title(title)
        if sig.confidence < 0.65 or not sig.family_id:
            continue
        if sig.family_id != job_sig.family_id:
            aff = title_affinity(title, job_title)
            if aff is not None and aff < 0.25:
                return True
    return False


def _passes_lexical_filter(
    job: dict[str, Any],
    candidate: dict[str, Any],
    intent: list[str],
) -> bool:
    if not intent and not candidate.get("skills"):
        return True

    prioritized = str(candidate.get("prioritized_title") or "").strip()
    path_titles = (
        normalize_path_search_titles(
            list(candidate.get("target_titles") or []),
            prioritized_title=prioritized,
        )
        if prioritized
        else intent
    )
    path_locked = should_enforce_path_title_gate(path_titles) if prioritized else False

    if path_titles and job_matches_path_titles(str(job.get("title") or ""), path_titles):
        return True

    if _occupation_mismatch(intent, job.get("title")):
        return False

    if path_locked:
        return _best_title_affinity_intent(job, candidate) >= _MIN_TITLE_AFFINITY

    if _best_title_affinity_intent(job, candidate) >= _MIN_TITLE_AFFINITY:
        return True

    # Skills can rescue adjacent roles, not unrelated occupations
    if intent and _occupation_mismatch(intent, job.get("title")):
        return False
    if _skill_signal(job, candidate) >= _MIN_SKILL_SIGNAL:
        return True
    return False


def _freshness_score(job: dict[str, Any]) -> float:
    """Proxy from scraped_at presence — higher when recently seen."""
    if job.get("scraped_at"):
        return 0.85
    return 0.5


def _source_quality_score(job: dict[str, Any]) -> float:
    src = str(job.get("source") or "")
    if src == "recruiter":
        return 1.0
    if src == "google_jobs":
        return 0.9
    if job.get("apply_url"):
        return 0.8
    return 0.6


def _feature_rerank_score(
    job: dict[str, Any], candidate: dict[str, Any]
) -> tuple[float, dict[str, float]]:
    """Rerank from independent raw features — each signal counted once."""
    title_fit = _best_title_affinity_intent(job, candidate)
    req_skills = _required_skill_coverage(job, candidate)
    resp = float(job.get("profile_score") or job.get("overall_score") or 0.0) * 0.5
    if job.get("vector_score") is not None:
        resp = max(resp, float(job["vector_score"]))
    seniority = float(job.get("experience_score") or 0.7)
    location = float(job.get("location_score") or 0.7)
    industry = float(job.get("domain_fit") or 0.7)
    freshness = _freshness_score(job)
    source_q = _source_quality_score(job)

    final = (
        0.30 * title_fit
        + 0.20 * req_skills
        + 0.15 * resp
        + 0.12 * seniority
        + 0.10 * location
        + 0.05 * industry
        + 0.05 * freshness
        + 0.03 * source_q
    )

    features = {
        "occupation_score": title_fit,
        "title_score": title_fit,
        "required_skill_score": req_skills,
        "responsibility_score": resp,
        "seniority_score": seniority,
        "location_score": location,
        "industry_score": industry,
        "freshness_score": freshness,
        "source_quality_score": source_q,
        "retrieval_score": final,
    }
    return round(final, 6), features


def filter_and_rerank_jobs(
    candidate: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Apply hard role gates, lexical gates, then raw-feature rerank."""
    intent = _candidate_intent_titles(candidate)
    eligible: list[dict[str, Any]] = []
    for job in jobs:
        if not _role_family_allowed(job, intent):
            continue
        if not _passes_lexical_filter(job, candidate, intent):
            continue
        ranked = dict(job)
        score, features = _feature_rerank_score(ranked, candidate)
        ranked["_retrieval_score"] = score
        ranked["_ranking_features"] = features
        ranked["ranking_model_version"] = _RANKING_MODEL_VERSION
        eligible.append(ranked)

    eligible.sort(
        key=lambda item: (
            -float(item.get("_behavior_adjusted_score") or item.get("_retrieval_score") or 0.0),
            -float(item.get("_retrieval_score") or 0.0),
            str(item.get("title") or ""),
        )
    )
    return eligible[:limit]


def rationale_overlay_items(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Only final top-10 cards should spend LLM rationale budget."""
    return [dict(item) for item in items[: min(limit, _MIN_LLM_RATIONALE_JOBS)]]
