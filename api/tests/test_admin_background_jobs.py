from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from hireloop_api.routes.admin import admin_background_jobs


@pytest.mark.asyncio
async def test_admin_background_jobs_defaults_to_failed() -> None:
    job_id = uuid.uuid4()
    db = AsyncMock()
    rows = [
        {
            "id": str(job_id),
            "kind": "job_embed",
            "status": "failed",
            "attempts": 3,
            "max_attempts": 3,
            "last_error": "timeout",
            "idempotency_key": "job_embed:x",
            "run_after": None,
            "started_at": None,
            "completed_at": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    ]

    with patch(
        "hireloop_api.services.background_jobs.list_background_jobs",
        new=AsyncMock(return_value=rows),
    ) as list_mock:
        out = await admin_background_jobs(
            _={"role": "admin"},
            db=db,
            status="failed",
            kind=None,
            limit=50,
        )

    assert len(out) == 1
    assert out[0]["kind"] == "job_embed"
    assert list_mock.await_args is not None
    assert list_mock.await_args.kwargs["status"] == "failed"
    assert list_mock.await_args.kwargs["limit"] == 50
