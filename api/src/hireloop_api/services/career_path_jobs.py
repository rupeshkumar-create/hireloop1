"""
Filter and rank jobs for a candidate's career-path search.

Career-path titles are multi-word ("Customer Success Manager", "Category
Manager"). Token-level ILIKE on single words like "operations" or "manager"
pulls in unrelated roles (Marketing Operations, Revenue Operations). This module
requires meaningful title overlap before a job is shown on the path.
"""

from __future__ import annotations

from typing import Any

from hireloop_api.services.domain_fit import _GENERIC_FUNCTION
from hireloop_api.services.match_quality import _meaningful_title_overlap
from hireloop_api.services.titles import canonical_title_tokens, title_affinity

# Minimum Jaccard affinity when overlap includes a non-generic function token.
PATH_JOB_MIN_AFFINITY = 0.30

# Extra function tokens in the job title that are not in the path target → reject.
_CROSS_FUNCTION_TOKENS = frozenset(
    {
        "marketing",
        "revenue",
        "gotomarket",
        "sales",
        "finance",
        "engineering",
        "engineer",
        "product",
        "design",
        "recruitment",
        "hr",
        "legal",
        "accounting",
    }
)

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


def _conflicting_function_tokens(job_title: str | None, target: str) -> set[str]:
    job_tokens = canonical_title_tokens(job_title)
    target_tokens = canonical_title_tokens(target)
    extra = job_tokens - target_tokens
    return extra & _CROSS_FUNCTION_TOKENS


def _role_family_conflict(job_title: str | None, target: str) -> bool:
    job_tokens = canonical_title_tokens(job_title)
    target_tokens = canonical_title_tokens(target)
    if not job_tokens or not target_tokens:
        return False

    target_specialties = target_tokens & _ENGINEERING_SPECIALTIES
    job_specialties = job_tokens & _ENGINEERING_SPECIALTIES
    if target_specialties and job_specialties and not (target_specialties & job_specialties):
        return True

    if "scientist" in target_tokens and "engineer" in job_tokens:
        science_tokens = {"scientist", "machine", "learning"}
        if not (job_tokens & science_tokens):
            return True

    return False


def _phrase_matches_title(target: str, job_title: str) -> bool:
    """Whole-phrase match without allowing 'Operations Manager' ⊂ 'Marketing Operations Manager'."""
    if _role_family_conflict(job_title, target):
        return False
    target_lower = target.strip().lower()
    job_lower = job_title.strip().lower()
    if len(target_lower) < 10:
        return False
    if job_lower == target_lower:
        return True
    if job_lower.startswith(f"{target_lower} ") or job_lower.startswith(f"{target_lower}-"):
        return True
    if job_lower.endswith(f" {target_lower}") or job_lower.endswith(f"-{target_lower}"):
        return not _conflicting_function_tokens(job_title, target)
    if target_lower in job_lower:
        return not _conflicting_function_tokens(job_title, target)
    return False


def normalize_path_search_titles(
    target_titles: list[str],
    *,
    prioritized_title: str | None = None,
) -> list[str]:
    """Deduped path titles with the prioritized role first."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        t = raw.strip()
        if not t:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(t)

    if prioritized_title:
        _add(prioritized_title)
    for raw in target_titles:
        _add(raw)
    return ordered


def job_matches_path_titles(job_title: str | None, path_titles: list[str]) -> bool:
    """True when a job title plausibly matches at least one path target role."""
    if not job_title or not path_titles:
        return False

    for target in path_titles:
        if _role_family_conflict(job_title, target):
            continue
        if _meaningful_title_overlap(job_title, [target]):
            return True
        if _phrase_matches_title(target, job_title):
            return True

    job_tokens = canonical_title_tokens(job_title)
    for target in path_titles:
        if _role_family_conflict(job_title, target):
            continue
        aff = title_affinity(target, job_title)
        if aff is None or aff < PATH_JOB_MIN_AFFINITY:
            continue
        if _conflicting_function_tokens(job_title, target):
            continue
        target_tokens = canonical_title_tokens(target)
        if (job_tokens & target_tokens) - _GENERIC_FUNCTION:
            return True
    return False


def _path_match_tier(job_title: str | None, path_titles: list[str]) -> int:
    """Lower is better: 0 = phrase hit, 1 = meaningful overlap, 2 = affinity only."""
    if not job_title:
        return 9
    for target in path_titles:
        if _phrase_matches_title(target, job_title):
            return 0
    if _meaningful_title_overlap(job_title, path_titles):
        return 1
    return 2


def rank_path_job_rows(
    rows: list[dict[str, Any]],
    path_titles: list[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Keep only path-relevant jobs and rank by title fit then match score."""
    matched = [dict(r) for r in rows if job_matches_path_titles(r.get("title"), path_titles)]
    matched.sort(
        key=lambda r: (
            _path_match_tier(r.get("title"), path_titles),
            -(float(r.get("overall_score") or 0.0)),
        )
    )
    return matched[:limit]
