"""Authenticated, ownership-scoped APIs for durable AI operations."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.models.ai_operation import AiOperationResponse
from hireloop_api.services import ai_operations, rate_limit

router = APIRouter(prefix="/ai-operations", tags=["ai-operations"])
logger = structlog.get_logger()

# Retrying can repeat external-AI spend. Other expensive generation endpoints
# allow 5-10 attempts per user each hour, so retries use the conservative bound.
AI_OPERATION_RETRIES_PER_KIND_PER_HOUR = 5
_CANCEL_CONFLICT_MESSAGE = "This operation can no longer be cancelled."
_RETRY_CONFLICT_MESSAGE = "This operation cannot be retried."

OperationIdPath = Annotated[
    str,
    Path(
        description="AI operation UUID",
        examples=["22222222-2222-4222-8222-222222222222"],
    ),
]


def _user_id(current_user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(current_user["id"]))


def _not_found() -> HTTPException:
    # Missing and non-owned IDs deliberately share an indistinguishable response.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI operation not found")


def _parse_operation_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise _not_found() from exc


@router.get("", response_model=list[AiOperationResponse])
async def list_ai_operations(
    operation_status: Annotated[Literal["active"], Query(alias="status")] = "active",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> list[AiOperationResponse]:
    """Return the caller's active operations for reload recovery."""
    del operation_status  # Literal validation documents and enforces the public filter.
    return await ai_operations.list_owned_operations(
        db,
        _user_id(current_user),
        active_only=True,
        limit=limit,
    )


@router.get("/{operation_id}", response_model=AiOperationResponse)
async def get_ai_operation(
    operation_id: OperationIdPath,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> AiOperationResponse:
    parsed_id = _parse_operation_id(operation_id)
    operation = await ai_operations.get_owned_operation(db, parsed_id, _user_id(current_user))
    if operation is None:
        raise _not_found()
    return operation


@router.post("/{operation_id}/cancel", response_model=AiOperationResponse)
async def cancel_ai_operation(
    operation_id: OperationIdPath,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> AiOperationResponse:
    parsed_id = _parse_operation_id(operation_id)
    try:
        async with db.transaction():
            return await ai_operations.cancel_owned_operation(db, parsed_id, _user_id(current_user))
    except ai_operations.AiOperationNotFoundError as exc:
        raise _not_found() from exc
    except ai_operations.AiOperationLifecycleError as exc:
        logger.warning(
            "ai_operation_lifecycle_conflict",
            action="cancel",
            operation_id=str(parsed_id),
            user_id=str(_user_id(current_user)),
            reason=str(exc)[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_CANCEL_CONFLICT_MESSAGE,
        ) from exc


@router.post("/{operation_id}/retry", response_model=AiOperationResponse)
async def retry_ai_operation(
    operation_id: OperationIdPath,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> AiOperationResponse:
    parsed_id = _parse_operation_id(operation_id)
    try:
        # Keep ownership and spend checks in the same transaction as the
        # service's source-row lock, descendant detection, and replacement enqueue.
        async with db.transaction():
            user_id = _user_id(current_user)
            owned = await ai_operations.get_owned_operation(db, parsed_id, user_id)
            if owned is None:
                raise _not_found()
            await rate_limit.check_rate_limit(
                str(user_id),
                f"ai_operation_retry:{owned.kind}",
                max_per_hour=AI_OPERATION_RETRIES_PER_KIND_PER_HOUR,
                db=db,
            )
            return await ai_operations.retry_owned_operation(db, parsed_id, user_id)
    except ai_operations.AiOperationNotFoundError as exc:
        raise _not_found() from exc
    except ai_operations.AiOperationLifecycleError as exc:
        logger.warning(
            "ai_operation_lifecycle_conflict",
            action="retry",
            operation_id=str(parsed_id),
            user_id=str(_user_id(current_user)),
            reason=str(exc)[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_RETRY_CONFLICT_MESSAGE,
        ) from exc
