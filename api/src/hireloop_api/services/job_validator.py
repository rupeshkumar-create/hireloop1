"""
Ingest-time hard validator (backend plan #3, borrowed pattern).

A single source-agnostic gate that runs BEFORE a job is persisted, dropping
structurally unusable postings so they never reach the DB, matching, or a
candidate's feed. This is distinct from `ranking.passes_hard_constraints`, which
is the per-candidate serve-time filter (remote pref, CTC floor) — this one is
about data quality of the posting itself, applied once at ingest for every
source (ATS feeds and Apify scrapers alike).

Rules (a job must pass ALL):
  - has a non-trivial title
  - has a real http(s) apply URL (a job nobody can apply to is noise)
  - is not already expired
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class _ValidatableJob(Protocol):
    title: str | None
    apply_url: str | None
    expires_at: datetime | None


def validate_job_record(rec: _ValidatableJob, *, now: datetime | None = None) -> tuple[bool, str]:
    """Return (ok, reason). reason is "" when ok, else a short drop code."""
    title = (rec.title or "").strip()
    if len(title) < 2:
        return False, "missing_title"

    url = (rec.apply_url or "").strip().lower()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "bad_apply_url"

    now = now or datetime.now(UTC)
    if rec.expires_at is not None:
        expires = rec.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < now:
            return False, "expired"

    return True, ""
