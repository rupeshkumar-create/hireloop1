"""Shared SSE helpers for Aarya chat streaming (text + voice channels)."""

from __future__ import annotations

import json
from typing import Any


def sse_event(payload: dict[str, Any]) -> str:
    """Format one Server-Sent Events data frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def sse_status(label: str) -> str:
    return sse_event({"status": label})


def sse_text(chunk: str) -> str:
    return sse_event({"text": chunk})


def sse_error(message: str) -> str:
    return sse_event({"error": message[:500]})
