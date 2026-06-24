"""Serialize DB job rows into API match-card payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def serialize_job_card(
    row: Any,  # noqa: ANN401
    *,
    explanation: str | None = None,
    computed_at: datetime | None = None,
) -> dict[str, Any]:
    """Shape used by /matches, chat job cards, and saved jobs."""
    job_id = row.get("job_id") or row.get("id")
    overall = row.get("overall_score")
    if overall is None:
        overall = 0.5
    ts = computed_at or row.get("computed_at") or datetime.now(UTC)
    if hasattr(ts, "isoformat"):
        ts_str = ts.isoformat()
    else:
        ts_str = str(ts)

    return {
        "job_id": str(job_id),
        "title": row.get("title") or "Role",
        "company_name": row.get("company_name"),
        "location_city": row.get("location_city"),
        "location_state": row.get("location_state"),
        "is_remote": bool(row.get("is_remote")),
        "employment_type": row.get("employment_type"),
        "seniority": row.get("seniority"),
        "ctc_min": row.get("ctc_min"),
        "ctc_max": row.get("ctc_max"),
        "skills_required": list(row.get("skills_required") or []),
        "apply_url": row.get("apply_url"),
        "overall_score": float(overall),
        "skills_score": (
            float(row["skills_score"]) if row.get("skills_score") is not None else None
        ),
        "experience_score": (
            float(row["experience_score"]) if row.get("experience_score") is not None else None
        ),
        "location_score": (
            float(row["location_score"]) if row.get("location_score") is not None else None
        ),
        "ctc_score": float(row["ctc_score"]) if row.get("ctc_score") is not None else None,
        "explanation": explanation or row.get("explanation"),
        "computed_at": ts_str,
    }
