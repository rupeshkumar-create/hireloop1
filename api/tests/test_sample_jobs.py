"""
Tests for the sample-jobs seeding path (P09 testability).

Proves the built-in sample items flow through the real normalise pipeline and
upsert via the same code path as a live Apify scrape — no token, DB, or network.
"""

from __future__ import annotations

import uuid

from hireloop_api.services.apify.job_ingester import JobIngester
from hireloop_api.services.apify.sample_jobs import SAMPLE_RAW_ITEMS, sample_job_records


def test_sample_records_are_valid_jobs() -> None:
    recs = sample_job_records()
    assert len(recs) == len(SAMPLE_RAW_ITEMS) >= 10
    assert all(r.country_code == "IN" for r in recs)
    assert all(r.title for r in recs)
    assert all(r.apify_job_id.startswith("gj_gj_sample_") for r in recs)
    # Skill extraction populated most roles (the matching signal).
    assert sum(1 for r in recs if r.skills_required) >= 8
    # Salary parsing pulled INR bands off the descriptions for most roles.
    assert sum(1 for r in recs if r.ctc_min and r.ctc_max) >= 8


def test_sample_includes_a_remote_role() -> None:
    recs = sample_job_records()
    assert any(r.is_remote for r in recs)


class _FakeConn:
    """Records writes; routes the upsert/company lookups the ingester issues."""

    def __init__(self) -> None:
        self.executes: list[str] = []

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        q = " ".join(query.split())
        if "FROM public.jobs WHERE apify_job_id" in q:
            return None  # no existing job → INSERT path
        if "FROM public.companies" in q:
            return {"id": uuid.uuid4()}  # company resolvable → links job
        return None

    async def execute(self, query: str, *args: object) -> str:
        self.executes.append(" ".join(query.split()))
        return "OK"


async def test_ingest_sample_inserts_all_via_real_upsert_path() -> None:
    conn = _FakeConn()
    ingester = JobIngester(apify_token="", db=conn)  # type: ignore[arg-type]
    stats = await ingester.ingest_sample()

    assert stats["source"] == "sample"
    assert stats["raw_items"] >= 10
    assert stats["inserted"] == stats["raw_items"]  # all new → all inserted
    assert stats["skipped"] == 0
    assert any("INSERT INTO public.jobs" in e for e in conn.executes)
