"""
Deterministic job retrieval pipeline.

Order of operations:
1. Role-family hard filter: remove obvious wrong tracks before ranking.
2. Title/skills lexical filter: require at least one concrete role signal.
3. Embedding/composite rerank: use stored overall_score after candidates pass gates.
4. LLM rationale selection: only the final top 10 get rationale generation.
"""

from __future__ import annotations

from typing import Any

from hireloop_api.services.career_path_jobs import job_matches_path_titles
from hireloop_api.services.skills import canonical_skill
from hireloop_api.services.titles import canonical_title_tokens, title_affinity

_ENGINEERING_SPECIALTIES = frozenset(
    {
        "backend",
        "frontend",
        "mobile",
        "fullstack",
        "devops",
        "quality",
        "reliability",
    }
)
_SCIENCE_TOKENS = frozenset({"scientist", "machine", "learning"})
_MIN_TITLE_AFFINITY = 0.25
_MIN_SKILL_SIGNAL = 0.25
_MIN_LLM_RATIONALE_JOBS = 10


def _candidate_titles(candidate: dict[str, Any]) -> list[str]:
    titles: list[str] = []
    for key in ("prioritized_title", "looking_for"):
        raw = candidate.get(key)
        if raw:
            titles.append(str(raw))
    for raw in candidate.get("target_titles") or []:
        if raw:
            titles.append(str(raw))
    if candidate.get("current_title"):
        titles.append(str(candidate["current_title"]))

    out: list[str] = []
    seen: set[str] = set()
    for title in titles:
        cleaned = title.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def _candidate_required_specialties(titles: list[str]) -> frozenset[str]:
    out: set[str] = set()
    for title in titles:
        out.update(canonical_title_tokens(title) & _ENGINEERING_SPECIALTIES)
    return frozenset(out)


def _role_family_allowed(job: dict[str, Any], candidate_titles: list[str]) -> bool:
    if not candidate_titles:
        return True

    job_tokens = canonical_title_tokens(job.get("title"))
    if not job_tokens:
        return True

    required_specialties = _candidate_required_specialties(candidate_titles)
    job_specialties = job_tokens & _ENGINEERING_SPECIALTIES
    if required_specialties and job_specialties and not (required_specialties & job_specialties):
        return False

    candidate_science = any(canonical_title_tokens(title) & _SCIENCE_TOKENS for title in candidate_titles)
    if candidate_science and "engineer" in job_tokens and not (job_tokens & _SCIENCE_TOKENS):
        return False

    return True


def _best_title_affinity(job: dict[str, Any], candidate_titles: list[str]) -> float:
    scores = [
        score
        for title in candidate_titles
        if (score := title_affinity(title, job.get("title"))) is not None
    ]
    return max(scores) if scores else 0.0


def _skill_signal(job: dict[str, Any], candidate: dict[str, Any]) -> float:
    cand = {canonical_skill(str(s)) for s in candidate.get("skills") or [] if s}
    req = {canonical_skill(str(s)) for s in job.get("skills_required") or [] if s}
    if not cand or not req:
        return 0.0
    overlap = cand & req
    coverage = len(overlap) / len(req)
    jaccard = len(overlap) / len(cand | req)
    return round(min(1.0, 0.85 * coverage + 0.15 * jaccard), 4)


def _passes_lexical_filter(
    job: dict[str, Any],
    candidate: dict[str, Any],
    candidate_titles: list[str],
) -> bool:
    if not candidate_titles and not candidate.get("skills"):
        return True

    if candidate_titles and job_matches_path_titles(str(job.get("title") or ""), candidate_titles):
        return True
    if _best_title_affinity(job, candidate_titles) >= _MIN_TITLE_AFFINITY:
        return True
    if _skill_signal(job, candidate) >= _MIN_SKILL_SIGNAL:
        return True
    return False


def _rerank_score(job: dict[str, Any], candidate: dict[str, Any], candidate_titles: list[str]) -> float:
    overall = float(job.get("overall_score") or 0.0)
    skills = float(job.get("skills_score") or 0.0)
    title = _best_title_affinity(job, candidate_titles)
    lexical = _skill_signal(job, candidate)
    return round((0.72 * overall) + (0.14 * skills) + (0.10 * title) + (0.04 * lexical), 6)


def filter_and_rerank_jobs(
    candidate: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Apply hard role gates, lexical gates, then stored embedding/composite rerank."""
    candidate_titles = _candidate_titles(candidate)
    eligible: list[dict[str, Any]] = []
    for job in jobs:
        if not _role_family_allowed(job, candidate_titles):
            continue
        if not _passes_lexical_filter(job, candidate, candidate_titles):
            continue
        ranked = dict(job)
        ranked["_retrieval_score"] = _rerank_score(ranked, candidate, candidate_titles)
        eligible.append(ranked)

    eligible.sort(
        key=lambda item: (
            -float(item.get("_retrieval_score") or 0.0),
            -float(item.get("overall_score") or 0.0),
            str(item.get("title") or ""),
        )
    )
    return eligible[:limit]


def rationale_overlay_items(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Only final top-10 cards should spend LLM rationale budget."""
    return [dict(item) for item in items[: min(limit, _MIN_LLM_RATIONALE_JOBS)]]
