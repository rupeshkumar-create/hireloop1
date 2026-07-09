"""
Application dossier — archive posting + kit snapshot per role.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def build_dossier_snapshot(
    *,
    job: dict[str, Any],
    cover_letter: str,
    interview_prep: str,
    resume_id: str | None,
    ats_report: dict[str, Any] | None,
    reviewer_notes: str | None,
) -> dict[str, Any]:
    """Immutable snapshot stored on job_application_kits.dossier."""
    return {
        "archived_at": datetime.now(UTC).isoformat(),
        "posting": {
            "job_id": job.get("id"),
            "title": job.get("title"),
            "company_name": job.get("company_name"),
            "location_city": job.get("location_city"),
            "description": str(job.get("description") or "")[:8000],
            "requirements": str(job.get("requirements") or "")[:4000],
            "skills_required": job.get("skills_required") or [],
            "apply_url": job.get("apply_url"),
        },
        "submitted": {
            "cover_letter": cover_letter,
            "interview_prep": interview_prep,
            "tailored_resume_id": resume_id,
        },
        "ats_report": ats_report,
        "reviewer_notes": reviewer_notes,
    }
