"""Broad recall utilities for candidate job search.

The job search stack should collect candidates from several pools, then rank the
union. This module keeps that orchestration pure and inspectable so the DB
queries can stay simple while the retrieval behavior is testable.
"""

from __future__ import annotations

from typing import Any

from hireloop_api.services.ranking import assemble_first_screen, reciprocal_rank_fusion

_SIGNAL_KEYS = ("overall_score", "skills_score", "experience_score", "location_score")


def build_query_terms(
    *,
    query_text: str | None,
    primary_titles: list[str],
    skills: list[str],
    desired_industry: str | None = None,
    limit: int = 12,
) -> list[str]:
    """Return recall terms from user intent, goals, career path, and skills."""
    raw_terms: list[str] = []
    if query_text and query_text.strip():
        raw_terms.append(query_text)
    raw_terms.extend(primary_titles)
    if desired_industry:
        raw_terms.append(desired_industry)
    raw_terms.extend(skills[:6])
    return _unique_nonempty(raw_terms)[:limit]


def annotate_recall_sources(rows: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Attach a recall source to rows without mutating DB records."""
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        sources = list(item.get("recall_sources") or [])
        if source not in sources:
            sources.append(source)
        item["recall_sources"] = sources
        out.append(item)
    return out


def union_and_rank_recall_pools(
    pools: list[tuple[str, list[dict[str, Any]]]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Merge recall pools by job id, preserve source diagnostics, and rank the union.

    Ranking uses RRF over pool order plus numeric relevance signals. This means
    a job can win by being a strong scored match, a strong skill match, or by
    appearing in multiple pools.
    """
    merged: dict[str, dict[str, Any]] = {}
    pool_rankings: list[list[str]] = []

    for source, rows in pools:
        annotated = annotate_recall_sources(rows, source)
        ranking_ids: list[str] = []
        for row in annotated:
            job_id = _job_id(row)
            if not job_id:
                continue
            ranking_ids.append(job_id)
            if job_id not in merged:
                merged[job_id] = row
            else:
                merged[job_id] = _merge_job_rows(merged[job_id], row)
        if ranking_ids:
            pool_rankings.append(ranking_ids)

    if not merged:
        return []

    items = list(merged.values())
    pool_scores = reciprocal_rank_fusion(pool_rankings, k=60) if pool_rankings else {}
    signal_scores = reciprocal_rank_fusion(_signal_rankings(items), k=60)
    for item in items:
        job_id = _job_id(item)
        relevance_lift = (
            0.08 * float(item.get("overall_score") or 0.0)
            + 0.04 * float(item.get("skills_score") or 0.0)
            + 0.02 * float(item.get("experience_score") or 0.0)
        )
        item["_recall_rank_score"] = round(
            pool_scores.get(job_id, 0.0) + signal_scores.get(job_id, 0.0) + relevance_lift,
            8,
        )
        item["recall_diagnostics"] = {
            "sources": list(item.get("recall_sources") or []),
            "rank_score": item["_recall_rank_score"],
        }

    items.sort(
        key=lambda item: (
            -float(item.get("_recall_rank_score") or 0.0),
            -float(item.get("overall_score") or 0.0),
            -float(item.get("skills_score") or 0.0),
            str(item.get("title") or ""),
        )
    )
    ranked = assemble_first_screen(
        items,
        screen_size=min(limit, 8),
        score_key="_recall_rank_score",
    )
    return ranked[:limit]


def _signal_rankings(items: list[dict[str, Any]]) -> list[list[str]]:
    rankings: list[list[str]] = []
    for key in _SIGNAL_KEYS:
        if all(item.get(key) is None for item in items):
            continue
        ordered = sorted(
            items,
            key=lambda item, signal=key: (
                item.get(signal) is None,
                -float(item.get(signal) or 0.0),
            ),
        )
        rankings.append([_job_id(item) for item in ordered if _job_id(item)])
    return rankings


def _merge_job_rows(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key == "recall_sources":
            merged[key] = _unique_nonempty([*merged.get(key, []), *incoming.get(key, [])])
        elif key in _SIGNAL_KEYS:
            merged[key] = _max_numeric(merged.get(key), value)
        elif merged.get(key) in (None, "", []):
            merged[key] = value
    return merged


def _job_id(row: dict[str, Any]) -> str:
    raw = row.get("job_id") or row.get("id")
    return str(raw) if raw else ""


def _max_numeric(a: Any, b: Any) -> Any:
    if a is None:
        return b
    if b is None:
        return a
    try:
        return max(float(a), float(b))
    except (TypeError, ValueError):
        return a


def _unique_nonempty(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out
