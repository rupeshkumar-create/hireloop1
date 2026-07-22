"""Public API models for durable, user-visible AI operation state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AiOperationStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class AiOperationResponse(BaseModel):
    """Safe lifecycle projection; private queue fields are deliberately ignored."""

    model_config = ConfigDict(extra="ignore")

    id: uuid.UUID
    kind: str
    status: AiOperationStatus
    progress_percent: int = Field(ge=0, le=100)
    stage: str
    message: str
    result_type: str | None = None
    result_id: uuid.UUID | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class AiOperationAccepted(BaseModel):
    """Response returned by feature submission routes for durable work."""

    operation_id: uuid.UUID
    status: Literal["queued", "running"]
    status_url: str
    retry_after_ms: int = 1500
