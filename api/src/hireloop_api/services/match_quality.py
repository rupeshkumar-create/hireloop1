"""
Match quality gates — verification layer between scoring and persistence / feed.

Quality-first policy:
  - Persona pool: only score jobs that plausibly match the candidate's role track.
  - Persist gate: weak / cross-industry pairs are not stored in match_scores.
  - Feed floor: DEFAULT_FEED_MIN_SCORE (used by API + frontend defaults).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hireloop_api.services.domain_fit import (
    _GENERIC_FUNCTION,
    detect_domains,
    domain_fit_multiplier,
)
from hireloop_api.services.skills import canonical_skill
from hireloop_api.services.test_jobs import is_test_job
from hireloop_api.services.titles import canonical_title_tokens, title_affinity

# Minimum overall score to write match_scores (below → row deleted / skipped).
MIN_PERSIST_SCORE = 0.35

# Jobs matching the candidate's CHOSEN career path get a lower floor: a
# skill-sparse fresh profile scores ~0.30 against a perfectly-on-path job
# (skill overlap 0 → the 0.40-weight dimension contributes nothing), and the
# 0.35 floor silently erased the exact roles the candidate asked for — the
# recurring "only demo jobs after onboarding" failure.
# Skill-sparse / mislabeled cold profiles score ~0.18–0.22 against exact title
# matches (40% skills weight at ~0). Keep this below that band so Ops Manager →
# Ops Manager still persists; domain + role_signal gates still filter junk.
PATH_ALIGNED_MIN_PERSIST = 0.18
PATH_ALIGNED_MIN_AFFINITY = 0.25

# Default relevance floor for candidate feed (API + app).
# Kept near MIN_PERSIST_SCORE so career-path-aligned roles (e.g. Growth Manager
# for Head of Growth) surface once embeddings are computed — not only test jobs.
DEFAULT_FEED_MIN_SCORE = 0.38

# Persona pool: minimum title affinity to enter the scoring batch.
MIN_TITLE_AFFINITY_POOL = 0.10

# Hard industry mismatch — never score or persist.
MIN_DOMAIN_MULTIPLIER_POOL = 0.25


def candidate_role_titles(cand_row: Mapping[str, Any]) -> list[str]:
    """Current role + prioritized search + career-path targets for persona pooling."""
    titles: list[str] = []
    if cand_row.get("current_title"):
        titles.append(str(cand_row["current_title"]))
    if cand_row.get("looking_for"):
        titles.append(str(cand_row["looking_for"]))
    if cand_row.get("prioritized_title"):
        titles.append(str(cand_row["prioritized_title"]))
    for raw in cand_row.get("target_titles") or []:
        if raw:
            titles.append(str(raw))
    return titles


def _best_title_affinity(job_title: str | None, candidate_titles: list[str]) -> float | None:
    scores = [a for t in candidate_titles if (a := title_affinity(t, job_title)) is not None]
    return max(scores) if scores else None


def _skill_overlap_score(
    candidate_skills: list[str] | None,
    job_skills: list[str] | None,
) -> float | None:
    cand = {canonical_skill(s) for s in (candidate_skills or []) if s}
    job = {canonical_skill(s) for s in (job_skills or []) if s}
    if not cand or not job:
        return None
    overlap = cand & job
    coverage = len(overlap) / len(job)
    jaccard = len(overlap) / len(cand | job)
    return round(min(1.0, 0.85 * coverage + 0.15 * jaccard), 4)


def _meaningful_title_overlap(job_title: str | None, candidate_titles: list[str]) -> bool:
    job_tokens = canonical_title_tokens(job_title)
    if not job_tokens:
        return False
    for ct in candidate_titles:
        ct_tokens = canonical_title_tokens(ct)
        overlap = job_tokens & ct_tokens
        if overlap - _GENERIC_FUNCTION:
            return True
    return False


def job_in_persona_pool(
    job_row: Mapping[str, Any],
    cand_row: Mapping[str, Any],
    *,
    min_title_affinity: float = MIN_TITLE_AFFINITY_POOL,
) -> bool:
    """
    Pre-score filter: should this job even be compared to this candidate?

    Cold-start (no title signals) → allow (recent jobs still scored).
    """
    if is_test_job(job_row):
        return True

    candidate_titles = candidate_role_titles(cand_row)
    job_title = job_row.get("title")

    cand_domains = detect_domains(
        title=cand_row.get("current_title"),
        company=cand_row.get("current_company"),
        skills=list(cand_row.get("skills") or []),
        extra=cand_row.get("headline") or cand_row.get("summary"),
    )
    job_domains = detect_domains(
        title=job_title,
        company=job_row.get("company_name"),
        skills=list(job_row.get("skills_required") or []),
        extra=job_row.get("description"),
    )
    if domain_fit_multiplier(cand_domains, job_domains) < MIN_DOMAIN_MULTIPLIER_POOL:
        return False

    if not candidate_titles:
        return True

    aff = _best_title_affinity(job_title, candidate_titles)
    if aff is not None and aff >= min_title_affinity:
        return True

    return _meaningful_title_overlap(job_title, candidate_titles)


def should_persist_match(
    cand_row: Mapping[str, Any],
    job_row: Mapping[str, Any],
    result: Mapping[str, Any],
) -> bool:
    """
    Verification gate before writing match_scores.

    Returns False for weak overall scores, hard industry mismatch, or when
    neither title nor skills show real role alignment.
    """
    if is_test_job(job_row):
        return True

    overall = float(result.get("overall") or 0.0)
    candidate_titles = candidate_role_titles(cand_row)
    title_aff = _best_title_affinity(job_row.get("title"), candidate_titles)
    path_aligned = title_aff is not None and title_aff >= PATH_ALIGNED_MIN_AFFINITY
    floor = PATH_ALIGNED_MIN_PERSIST if path_aligned else MIN_PERSIST_SCORE
    if overall < floor:
        return False

    cand_domains = detect_domains(
        title=cand_row.get("current_title"),
        company=cand_row.get("current_company"),
        skills=list(cand_row.get("skills") or []),
        extra=cand_row.get("headline") or cand_row.get("summary"),
    )
    job_domains = detect_domains(
        title=job_row.get("title"),
        company=job_row.get("company_name"),
        skills=list(job_row.get("skills_required") or []),
        extra=job_row.get("description"),
    )
    if domain_fit_multiplier(cand_domains, job_domains) < MIN_DOMAIN_MULTIPLIER_POOL:
        return False

    lexical = _skill_overlap_score(
        list(cand_row.get("skills") or []),
        list(job_row.get("skills_required") or []),
    )
    role_signal = max(title_aff or 0.0, lexical or 0.0)
    if role_signal < 0.15:
        return False

    return True
