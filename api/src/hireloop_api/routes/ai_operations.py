"""Authenticated, ownership-scoped APIs for durable AI operations."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from hireloop_api.deps import get_db, get_phone_verified_user
from hireloop_api.models.ai_operation import AiOperationResponse
from hireloop_api.services import ai_operations

router = APIRouter(prefix="/ai-operations", tags=["ai-operations"])


def _user_id(current_user: dict[str, object]) -> uuid.UUID:
    return uuid.UUID(str(current_user["id"]))


def _not_found() -> HTTPException:
    # Missing and non-owned IDs deliberately share an indistinguishable response.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI operation not found")


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
    operation_id: uuid.UUID,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> AiOperationResponse:
    operation = await ai_operations.get_owned_operation(db, operation_id, _user_id(current_user))
    if operation is None:
        raise _not_found()
    return operation


@router.post("/{operation_id}/cancel", response_model=AiOperationResponse)
async def cancel_ai_operation(
    operation_id: uuid.UUID,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> AiOperationResponse:
    try:
        async with db.transaction():
            return await ai_operations.cancel_owned_operation(
                db, operation_id, _user_id(current_user)
            )
    except ai_operations.AiOperationNotFoundError as exc:
        raise _not_found() from exc
    except ai_operations.AiOperationLifecycleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{operation_id}/retry", response_model=AiOperationResponse)
async def retry_ai_operation(
    operation_id: uuid.UUID,
    current_user: dict[str, object] = Depends(get_phone_verified_user),
    db: asyncpg.Connection = Depends(get_db),
) -> AiOperationResponse:
    try:
        # The transaction holds retry_owned_operation's source-row lock until
        # descendant detection and the replacement enqueue both complete.
        async with db.transaction():
            return await ai_operations.retry_owned_operation(
                db, operation_id, _user_id(current_user)
            )
    except ai_operations.AiOperationNotFoundError as exc:
        raise _not_found() from exc
    except ai_operations.AiOperationLifecycleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
