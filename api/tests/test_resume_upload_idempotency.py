"""A replayed CV upload must resolve to one durable resume."""

from __future__ import annotations

import inspect
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from hireloop_api.routes.resumes import (
    _find_idempotent_resume,
    _resume_id_for_upload,
    _validate_upload_idempotency_key,
    upload_resume,
)


def test_resume_identity_is_stable_for_same_user_and_key() -> None:
    user_id = uuid.uuid4()
    key = uuid.uuid4()

    first = _resume_id_for_upload(user_id=user_id, idempotency_key=key)
    second = _resume_id_for_upload(user_id=user_id, idempotency_key=key)

    assert first == second
    assert first != _resume_id_for_upload(user_id=uuid.uuid4(), idempotency_key=key)


def test_invalid_supplied_idempotency_key_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_upload_idempotency_key("not-a-uuid")

    assert exc_info.value.status_code == 400
    assert "Idempotency-Key" in str(exc_info.value.detail)


def test_upload_route_accepts_optional_idempotency_header() -> None:
    parameter = inspect.signature(upload_resume).parameters["idempotency_key"]
    assert parameter.default is not inspect.Parameter.empty


@pytest.mark.asyncio
async def test_existing_idempotency_key_returns_original_resume() -> None:
    db = AsyncMock()
    resume_id = uuid.uuid4()
    db.fetchrow.return_value = {
        "id": resume_id,
        "file_path": f"user/{resume_id}.pdf",
        "parsed_data": {},
    }

    replay = await _find_idempotent_resume(
        db,
        candidate_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4(),
    )

    assert replay is not None
    assert replay.resume_id == str(resume_id)
    assert replay.file_path.endswith(f"{resume_id}.pdf")
    assert replay.message == "Resume upload already completed."
