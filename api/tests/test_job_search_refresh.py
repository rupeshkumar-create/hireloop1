"""Tests for fresh job search rotation in chat."""

import uuid

from hireloop_api.services.job_search_refresh import (
    compute_job_search_fetch_limit,
    exclude_job_rows,
    wants_fresh_job_results,
)


def test_wants_fresh_job_results_detects_refresh_phrases() -> None:
    assert wants_fresh_job_results("Find me something new")
    assert wants_fresh_job_results("Show me more roles")
    assert wants_fresh_job_results("find new job")
    assert wants_fresh_job_results("Find my job")
    assert wants_fresh_job_results("find a new job please")
    assert not wants_fresh_job_results("Find me backend jobs in Bangalore")


def test_compute_job_search_fetch_limit_scales_with_exclusions() -> None:
    assert compute_job_search_fetch_limit(limit=3, exclude_count=0) == 9
    assert compute_job_search_fetch_limit(limit=3, exclude_count=5) == 13


def test_exclude_job_rows_skips_seen_ids() -> None:
    jid1 = str(uuid.uuid4())
    jid2 = str(uuid.uuid4())
    jid3 = str(uuid.uuid4())
    rows = [
        {"id": jid1, "title": "A"},
        {"id": jid2, "title": "B"},
        {"id": jid3, "title": "C"},
    ]
    out = exclude_job_rows(rows, exclude_job_ids=[jid1], limit=2)
    assert [r["id"] for r in out] == [jid2, jid3]
