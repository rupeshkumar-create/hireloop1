"""Typed lifecycle service for user-visible durable AI operations.

All write helpers rely on guarded SQL updates so lifecycle invariants hold even
when multiple workers race. Enqueue and lifecycle writes compose with the
caller's connection and transaction. ``retry_owned_operation`` preserves an
existing caller transaction, or opens one only when necessary to hold its
source-row lock through descendant detection and enqueue.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx
import structlog

from hireloop_api.models.ai_operation import AiOperationResponse

logger = structlog.get_logger()

MAX_SAFE_ERROR_MESSAGE_LENGTH = 240
_MAX_STAGE_LENGTH = 80
_RETRYABLE_CODES = frozenset(
    {"network_unreachable", "provider_timeout", "provider_rate_limited", "provider_unavailable"}
)

_OPERATION_COLUMNS = """
id, kind, status, progress_percent, stage, message,
result_type, result_id, error_code, error_message,
created_at, updated_at, completed_at
"""


class AiOperationNotFoundError(LookupError):
    """The operation does not exist or is not owned by the requesting user."""


class AiOperationLifecycleError(ValueError):
    """The requested operation transition is not legal."""


@dataclass(frozen=True, slots=True)
class ClassifiedOperationError:
    """Stable public classification for an internal exception."""

    code: str
    message: str
    retryable: bool


_ERROR_DETAILS: dict[str, tuple[str, bool]] = {
    "network_unreachable": (
        "The service could not reach the AI provider. Please try again.",
        True,
    ),
    "provider_timeout": (
        "The AI provider took too long to respond. Please try again.",
        True,
    ),
    "provider_rate_limited": (
        "The AI provider is temporarily busy. Please try again shortly.",
        True,
    ),
    "provider_unavailable": (
        "The AI provider is temporarily unavailable. Please try again.",
        True,
    ),
    "invalid_input": (
        "Some information needed for this request is invalid. Please review it and try again.",
        False,
    ),
    "insufficient_profile": (
        "Your profile needs more information before this can be generated.",
        False,
    ),
    "permission_denied": (
        "You do not have permission to complete this request.",
        False,
    ),
    "job_expired": ("This job is no longer available.", False),
    "cancelled": ("This request was cancelled.", False),
    "internal_error": (
        "Something went wrong while generating your result. Please try again later.",
        False,
    ),
}


def _safe_text(value: str, *, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _classified(code: str) -> ClassifiedOperationError:
    message, retryable = _ERROR_DETAILS[code]
    return ClassifiedOperationError(
        code=code,
        message=_safe_text(message, limit=MAX_SAFE_ERROR_MESSAGE_LENGTH),
        retryable=retryable,
    )


def classify_operation_error(error: BaseException) -> ClassifiedOperationError:
    """Map internal failures to the stable, non-sensitive public error contract."""
    chain: list[BaseException] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__

    if any(isinstance(item, asyncio.CancelledError) for item in chain):
        return _classified("cancelled")
    if any(isinstance(item, PermissionError) for item in chain):
        return _classified("permission_denied")

    http_statuses = [
        item.response.status_code for item in chain if isinstance(item, httpx.HTTPStatusError)
    ]
    if any(status in {401, 403} for status in http_statuses):
        return _classified("permission_denied")
    if any(isinstance(item, (TimeoutError, httpx.TimeoutException)) for item in chain):
        return _classified("provider_timeout")
    if 429 in http_statuses:
        return _classified("provider_rate_limited")
    if any(500 <= status <= 599 for status in http_statuses):
        return _classified("provider_unavailable")

    # ConnectError is how httpx exposes DNS lookup failures, unreachable hosts,
    # and exhausted connection attempts. SDKs frequently wrap it, so inspect
    # the bounded cause chain rather than only the outer exception.
    if any(isinstance(item, httpx.ConnectError) for item in chain):
        return _classified("network_unreachable")
    if any(isinstance(item, ConnectionError) for item in chain):
        return _classified("provider_unavailable")
    if any(
        isinstance(item, httpx.TransportError)
        and not isinstance(item, (httpx.TimeoutException, httpx.ConnectError))
        for item in chain
    ):
        return _classified("provider_unavailable")

    # DNS resolution and unreachable-network failures are commonly surfaced as
    # OSError subclasses. Keep this after TimeoutError and ConnectionError so
    # those more specific retry categories retain precedence, and do not label
    # unrelated local OS errors (for example, a full disk) as network failures.
    for item in chain:
        if not isinstance(item, OSError):
            continue
        os_detail = f"{type(item).__name__} {item}".lower()
        if any(
            token in os_detail
            for token in (
                "gaierror",
                "dns",
                "network unreachable",
                "no route to host",
                "name resolution",
                "nodename nor servname",
            )
        ):
            return _classified("network_unreachable")

    searchable = " ".join(f"{type(item).__name__} {item}".lower() for item in chain)

    if any(token in searchable for token in ("cancelled", "canceled")):
        return _classified("cancelled")
    if any(
        token in searchable for token in ("permission", "forbidden", "unauthorized", "401", "403")
    ):
        return _classified("permission_denied")
    if any(token in searchable for token in ("expired", "expiry", "job is no longer available")):
        return _classified("job_expired")
    if any(
        token in searchable
        for token in (
            "insufficient profile",
            "profile is insufficient",
            "profile incomplete",
            "missing profile",
        )
    ):
        return _classified("insufficient_profile")
    if any(
        token in searchable for token in ("rate limit", "ratelimit", "too many requests", "429")
    ):
        return _classified("provider_rate_limited")
    if any(token in searchable for token in ("timeout", "timed out", "deadline exceeded")):
        return _classified("provider_timeout")
    if any(
        token in searchable
        for token in (
            "unavailable",
            "connection refused",
            "connection reset",
            "bad gateway",
            "502",
            "503",
            "504",
        )
    ):
        return _classified("provider_unavailable")
    if isinstance(error, ValueError) or any(
        token in searchable for token in ("invalid input", "validation", "malformed")
    ):
        return _classified("invalid_input")
    return _classified("internal_error")


def is_retryable_error_code(code: str | None) -> bool:
    """Return whether a terminal public error may create a new operation attempt."""
    return code in _RETRYABLE_CODES


def _to_response(row: asyncpg.Record | dict[str, Any]) -> AiOperationResponse:
    data = dict(row)
    data["retryable"] = is_retryable_error_code(data.get("error_code"))
    return AiOperationResponse.model_validate(data)


async def enqueue_ai_operation(
    db: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str,
    candidate_id: uuid.UUID | None = None,
    recruiter_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    retry_of: uuid.UUID | None = None,
    stage: str = "queued",
    message: str = "Your request is queued.",
    run_after: datetime | None = None,
    max_attempts: int = 3,
    expires_at: datetime | None = None,
) -> AiOperationResponse:
    """Create/reuse an operation and enqueue its private job on ``db``.

    The partial-conflict clause handles duplicate concurrent submissions. The
    caller must wrap this call and any domain changes in its own transaction.
    """
    row = await db.fetchrow(
        f"""
        INSERT INTO public.ai_operations
          (user_id, candidate_id, recruiter_id, kind, resource_type, resource_id,
           retry_of, idempotency_key, status, progress_percent, stage, message,
           expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'queued', 0, $9, $10, $11)
        ON CONFLICT (idempotency_key)
          WHERE status IN ('queued', 'running') AND deleted_at IS NULL
        DO NOTHING
        RETURNING {_OPERATION_COLUMNS}
        """,
        user_id,
        candidate_id,
        recruiter_id,
        kind,
        resource_type,
        resource_id,
        retry_of,
        idempotency_key,
        _safe_text(stage, limit=_MAX_STAGE_LENGTH),
        _safe_text(message, limit=MAX_SAFE_ERROR_MESSAGE_LENGTH),
        expires_at,
    )
    if row is None:
        row = await db.fetchrow(
            f"""
            SELECT {_OPERATION_COLUMNS}
            FROM public.ai_operations
            WHERE idempotency_key = $1
              AND user_id = $2
              AND status IN ('queued', 'running')
              AND deleted_at IS NULL
            """,
            idempotency_key,
            user_id,
        )
        if row is None:
            raise AiOperationLifecycleError("Active idempotency key belongs to another operation")
        return _to_response(row)

    operation_id = uuid.UUID(str(row["id"]))
    private_payload = dict(payload)
    private_payload["operation_id"] = str(operation_id)

    # Local import avoids a service import cycle when the worker becomes
    # operation-aware in the next implementation task.
    from hireloop_api.services.background_jobs import enqueue_job

    background_job_id = await enqueue_job(
        db,
        kind=kind,
        payload=private_payload,
        idempotency_key=f"ai_operation:{operation_id}",
        run_after=run_after,
        max_attempts=max_attempts,
    )
    queue_row = await db.fetchrow(
        """
        SELECT id, kind, payload, idempotency_key
        FROM public.background_jobs
        WHERE id = $1
          AND status IN ('pending', 'running')
        """,
        background_job_id,
    )
    if queue_row is None:
        raise AiOperationLifecycleError("The operation queue job is unavailable")
    queue_data = dict(queue_row)
    queue_payload = queue_data.get("payload")
    if isinstance(queue_payload, str):
        try:
            queue_payload = json.loads(queue_payload)
        except json.JSONDecodeError as exc:
            raise AiOperationLifecycleError("The operation queue payload is invalid") from exc
    expected_queue_key = f"ai_operation:{operation_id}"
    if (
        queue_data.get("kind") != kind
        or queue_data.get("idempotency_key") != expected_queue_key
        or not isinstance(queue_payload, dict)
        or queue_payload.get("operation_id") != str(operation_id)
    ):
        raise AiOperationLifecycleError("The operation queue job is incompatible")

    linked = await db.fetchrow(
        f"""
        UPDATE public.ai_operations
        SET background_job_id = $2
        WHERE id = $1
          AND status = 'queued'
          AND deleted_at IS NULL
        RETURNING {_OPERATION_COLUMNS}
        """,
        operation_id,
        background_job_id,
    )
    if linked is None:
        raise AiOperationLifecycleError("Operation changed before its queue job could be linked")
    return _to_response(linked)


async def get_owned_operation(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AiOperationResponse | None:
    row = await db.fetchrow(
        f"""
        SELECT {_OPERATION_COLUMNS}
        FROM public.ai_operations
        WHERE id = $1
          AND user_id = $2
          AND deleted_at IS NULL
        """,
        operation_id,
        user_id,
    )
    return _to_response(row) if row is not None else None


async def list_owned_operations(
    db: asyncpg.Connection,
    user_id: uuid.UUID,
    *,
    active_only: bool = True,
    limit: int = 50,
) -> list[AiOperationResponse]:
    status_filter = "AND status IN ('queued', 'running')" if active_only else ""
    rows = await db.fetch(
        f"""
        SELECT {_OPERATION_COLUMNS}
        FROM public.ai_operations
        WHERE user_id = $1
          AND deleted_at IS NULL
          {status_filter}
        ORDER BY created_at DESC
        LIMIT $2
        """,
        user_id,
        max(1, min(limit, 100)),
    )
    return [_to_response(row) for row in rows]


async def mark_operation_running(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    *,
    stage: str = "starting",
    message: str = "Starting your request.",
) -> AiOperationResponse | None:
    row = await db.fetchrow(
        f"""
        UPDATE public.ai_operations
        SET status = 'running',
            progress_percent = GREATEST(progress_percent, 1),
            stage = $2,
            message = $3,
            attempts = attempts + 1,
            started_at = COALESCE(started_at, NOW())
        WHERE id = $1
          AND status = 'queued'
          AND deleted_at IS NULL
        RETURNING {_OPERATION_COLUMNS}
        """,
        operation_id,
        _safe_text(stage, limit=_MAX_STAGE_LENGTH),
        _safe_text(message, limit=MAX_SAFE_ERROR_MESSAGE_LENGTH),
    )
    return _to_response(row) if row is not None else None


async def update_operation_progress(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    progress_percent: int,
    stage: str,
    message: str,
) -> AiOperationResponse | None:
    row = await db.fetchrow(
        f"""
        UPDATE public.ai_operations
        SET progress_percent = $2,
            stage = $3,
            message = $4
        WHERE id = $1
          AND status = 'running'
          AND $2 BETWEEN 0 AND 99
          AND $2 >= progress_percent
          AND deleted_at IS NULL
        RETURNING {_OPERATION_COLUMNS}
        """,
        operation_id,
        progress_percent,
        _safe_text(stage, limit=_MAX_STAGE_LENGTH),
        _safe_text(message, limit=MAX_SAFE_ERROR_MESSAGE_LENGTH),
    )
    return _to_response(row) if row is not None else None


async def mark_operation_succeeded(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    *,
    result_type: str | None = None,
    result_id: uuid.UUID | None = None,
    message: str = "Your result is ready.",
) -> AiOperationResponse | None:
    normalized_result_type = result_type.strip() if result_type is not None else None
    has_result_type = bool(normalized_result_type)
    has_result_id = result_id is not None
    if has_result_type != has_result_id:
        raise AiOperationLifecycleError(
            "Successful operations require both result_type and result_id"
        )
    if not has_result_type:
        raise AiOperationLifecycleError("Successful operations require a result reference")

    row = await db.fetchrow(
        f"""
        UPDATE public.ai_operations
        SET status = 'succeeded',
            progress_percent = 100,
            stage = 'ready',
            message = $2,
            result_type = $3,
            result_id = $4,
            error_code = NULL,
            error_message = NULL,
            completed_at = NOW()
        WHERE id = $1
          AND status = 'running'
          AND deleted_at IS NULL
        RETURNING {_OPERATION_COLUMNS}
        """,
        operation_id,
        _safe_text(message, limit=MAX_SAFE_ERROR_MESSAGE_LENGTH),
        normalized_result_type,
        result_id,
    )
    return _to_response(row) if row is not None else None


async def mark_operation_failed(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    error: BaseException,
) -> AiOperationResponse | None:
    """Persist a classified failure and retain raw detail only on the private job."""
    classified = classify_operation_error(error)
    terminal_status = "cancelled" if classified.code == "cancelled" else "failed"
    row = await db.fetchrow(
        f"""
        UPDATE public.ai_operations
        SET status = $2,
            stage = $3,
            message = $4,
            error_code = $5,
            error_message = $4,
            completed_at = NOW()
        WHERE id = $1
          AND status = 'running'
          AND deleted_at IS NULL
        RETURNING {_OPERATION_COLUMNS}
        """,
        operation_id,
        terminal_status,
        terminal_status,
        classified.message,
        classified.code,
    )
    if row is None:
        return None

    raw_error = str(error)[:2000]
    await db.execute(
        """
        UPDATE public.background_jobs
        SET last_error = $2,
            updated_at = NOW()
        WHERE id = (
          SELECT background_job_id
          FROM public.ai_operations
          WHERE id = $1 AND deleted_at IS NULL
        )
        """,
        operation_id,
        raw_error,
    )
    logger.warning(
        "ai_operation_failed",
        operation_id=str(operation_id),
        error_code=classified.code,
        raw_error=raw_error,
    )
    return _to_response(row)


async def _raise_owned_transition_error(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    user_id: uuid.UUID,
    action: str,
) -> None:
    status = await db.fetchval(
        """
        SELECT status
        FROM public.ai_operations
        WHERE id = $1 AND user_id = $2 AND deleted_at IS NULL
        """,
        operation_id,
        user_id,
    )
    if status is None:
        raise AiOperationNotFoundError("AI operation not found")
    raise AiOperationLifecycleError(f"Cannot {action} an operation with status '{status}'")


async def cancel_owned_operation(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AiOperationResponse:
    row = await db.fetchrow(
        f"""
        UPDATE public.ai_operations
        SET status = 'cancelled',
            stage = 'cancelled',
            message = $3,
            error_code = 'cancelled',
            error_message = $3,
            completed_at = NOW()
        WHERE id = $1
          AND user_id = $2
          AND status IN ('queued', 'running')
          AND deleted_at IS NULL
        RETURNING {_OPERATION_COLUMNS}, background_job_id
        """,
        operation_id,
        user_id,
        _ERROR_DETAILS["cancelled"][0],
    )
    if row is None:
        await _raise_owned_transition_error(db, operation_id, user_id, "cancel")
        raise AssertionError("unreachable")

    await db.execute(
        """
        UPDATE public.background_jobs
        SET status = 'cancelled',
            completed_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
          AND status IN ('pending', 'running')
        """,
        row.get("background_job_id"),
    )
    return _to_response(row)


async def retry_owned_operation(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> AiOperationResponse:
    """Retry once per failed source attempt under a source-row lock.

    When the caller has not already opened a transaction, this service opens
    one so ``FOR UPDATE`` remains held through descendant detection and enqueue.
    """
    if not db.is_in_transaction():
        async with db.transaction():
            return await _retry_owned_operation_locked(db, operation_id, user_id, now=now)
    return await _retry_owned_operation_locked(db, operation_id, user_id, now=now)


async def _retry_owned_operation_locked(
    db: asyncpg.Connection,
    operation_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    now: datetime | None,
) -> AiOperationResponse:
    row = await db.fetchrow(
        """
        SELECT o.id, o.kind, o.candidate_id, o.recruiter_id,
               o.resource_type, o.resource_id, o.idempotency_key,
               o.error_code, o.expires_at, j.payload, j.max_attempts
        FROM public.ai_operations o
        JOIN public.background_jobs j
          ON j.id = o.background_job_id
         AND j.payload IS NOT NULL
        WHERE o.id = $1
          AND o.user_id = $2
          AND o.status = 'failed'
          AND o.deleted_at IS NULL
        FOR UPDATE OF o
        """,
        operation_id,
        user_id,
    )
    if row is None:
        await _raise_owned_transition_error(db, operation_id, user_id, "retry")
        raise AssertionError("unreachable")

    child = await db.fetchrow(
        f"""
        SELECT {_OPERATION_COLUMNS}, user_id, deleted_at
        FROM public.ai_operations
        WHERE retry_of = $1
        ORDER BY created_at ASC
        LIMIT 1
        """,
        operation_id,
    )
    if child is not None:
        child_data = dict(child)
        if (
            child_data.get("user_id") == user_id
            and child_data.get("deleted_at") is None
            and child_data.get("status") in {"queued", "running"}
        ):
            return _to_response(child_data)
        raise AiOperationLifecycleError("This operation attempt has already been retried")

    data = dict(row)
    if not is_retryable_error_code(data.get("error_code")):
        raise AiOperationLifecycleError("This failure cannot be retried")
    expires_at = data.get("expires_at")
    current_time = now or datetime.now(UTC)
    if isinstance(expires_at, datetime) and expires_at <= current_time:
        raise AiOperationLifecycleError("This operation has expired")

    payload = data.get("payload")
    if payload is None:
        raise AiOperationLifecycleError("The original queue payload is unavailable")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AiOperationLifecycleError("The original queue payload is invalid") from exc
    if not isinstance(payload, dict):
        raise AiOperationLifecycleError("The original queue payload is unavailable")
    private_payload = dict(payload)
    private_payload.pop("operation_id", None)

    return await enqueue_ai_operation(
        db,
        user_id=user_id,
        candidate_id=data.get("candidate_id"),
        recruiter_id=data.get("recruiter_id"),
        kind=str(data["kind"]),
        payload=private_payload,
        idempotency_key=str(data["idempotency_key"]),
        resource_type=data.get("resource_type"),
        resource_id=data.get("resource_id"),
        retry_of=operation_id,
        stage="queued",
        message="Your retry is queued.",
        max_attempts=int(data.get("max_attempts") or 3),
        expires_at=expires_at,
    )
