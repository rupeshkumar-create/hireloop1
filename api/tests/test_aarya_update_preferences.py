"""
Tests for Aarya's update_job_preferences tool — remote filter + relocation.

"Apply all over India" must actually persist (open_to_relocation=true), not just
be acknowledged in chat. These use a fake connection that captures the UPDATE.
"""

from __future__ import annotations

import uuid

from hireloop_api.agents.aarya.tools import update_job_preferences, update_profile

_USER_ID = str(uuid.uuid4())


class _CaptureDB:
    """Records the UPDATE statement + params; reports one row changed."""

    def __init__(self) -> None:
        self.update_sql: str | None = None
        self.update_args: tuple = ()

    async def execute(self, query: str, *args: object) -> str:
        if "UPDATE public.candidates" in query and "agent_actions" not in query:
            self.update_sql = query
            self.update_args = args
            return "UPDATE 1"
        return "INSERT 0 1"  # _write_action insert

    async def fetchval(self, query: str, *args: object) -> object:
        # enqueue_job: idempotency SELECT -> no existing job; INSERT RETURNING id -> a uuid.
        return uuid.uuid4() if "INSERT" in query else None


async def test_relocation_preference_persists() -> None:
    db = _CaptureDB()
    result = await update_job_preferences(
        db,  # type: ignore[arg-type]
        _USER_ID,
        "sess",
        open_to_relocation=True,
    )

    assert result["open_to_relocation"] is True
    assert result["location_scope"] == "country"  # legacy flag now syncs the scope
    assert "anywhere in India" in result["message"]
    assert db.update_sql is not None
    assert "open_to_relocation =" in db.update_sql
    assert "location_scope =" in db.update_sql
    assert True in db.update_args  # the boolean value was parameterized


async def test_remote_and_relocation_update_together() -> None:
    db = _CaptureDB()
    result = await update_job_preferences(
        db,  # type: ignore[arg-type]
        _USER_ID,
        "sess",
        remote_preference="remote_only",
        open_to_relocation=True,
    )

    assert result["remote_preference"] == "remote_only"
    assert result["open_to_relocation"] is True
    assert "remote_preference =" in (db.update_sql or "")
    assert "open_to_relocation =" in (db.update_sql or "")


async def test_location_scope_persists_and_syncs_relocation() -> None:
    db = _CaptureDB()
    result = await update_job_preferences(
        db,  # type: ignore[arg-type]
        _USER_ID,
        "sess",
        location_scope="country",
    )
    assert result["location_scope"] == "country"
    assert result["open_to_relocation"] is True  # synced off the scope
    assert "location_scope =" in (db.update_sql or "")
    assert "open_to_relocation =" in (db.update_sql or "")
    assert "anywhere in India" in result["message"]


async def test_city_scope_clears_relocation() -> None:
    db = _CaptureDB()
    result = await update_job_preferences(
        db,  # type: ignore[arg-type]
        _USER_ID,
        "sess",
        location_scope="city",
    )
    assert result["open_to_relocation"] is False


async def test_invalid_location_scope_rejected() -> None:
    db = _CaptureDB()
    result = await update_job_preferences(
        db,  # type: ignore[arg-type]
        _USER_ID,
        "sess",
        location_scope="galaxy",
    )
    assert "error" in result
    assert db.update_sql is None


async def test_no_fields_is_a_no_op_error() -> None:
    db = _CaptureDB()
    result = await update_job_preferences(db, _USER_ID, "sess")  # type: ignore[arg-type]

    assert "error" in result
    assert db.update_sql is None  # nothing was written


# ── update_profile (the "call with Aarya" / form save path) ───────────────────


async def test_update_profile_converts_lpa_to_inr_and_persists() -> None:
    db = _CaptureDB()
    result = await update_profile(
        db,  # type: ignore[arg-type]
        _USER_ID,
        "sess",
        current_title="Product Designer",
        expected_ctc_min_lpa=10,
        expected_ctc_max_lpa=18,
        notice_period_days=30,
        skills=["Figma", "UX research"],
    )

    assert "current_title =" in (db.update_sql or "")
    assert "skills =" in (db.update_sql or "")
    # 10 LPA → 1,000,000 INR; 18 LPA → 1,800,000 INR.
    assert 1_000_000 in db.update_args
    assert 1_800_000 in db.update_args
    assert "expected_ctc_min" in result["updated_fields"]
    assert "skills" in result["updated_fields"]


async def test_update_profile_no_fields_errors() -> None:
    db = _CaptureDB()
    result = await update_profile(db, _USER_ID, "sess")  # type: ignore[arg-type]

    assert "error" in result
    assert db.update_sql is None
