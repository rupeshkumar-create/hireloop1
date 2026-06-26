"""Shared SSE helpers for Aarya chat streaming (text + voice channels)."""

from __future__ import annotations

import json
from typing import Any


def sse_event(payload: dict[str, Any]) -> str:
    """Format one Server-Sent Events data frame."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def sse_done() -> str:
    return "data: [DONE]\n\n"


def sse_status(
    label: str,
    *,
    spoken_filler: str | None = None,
    eta_sec: int | None = None,
    hinglish_hint: bool = False,
) -> str:
    payload: dict[str, Any] = {"status": label}
    if spoken_filler:
        payload["spoken_filler"] = spoken_filler
    if eta_sec is not None:
        payload["eta_sec"] = eta_sec
    if hinglish_hint:
        payload["hinglish_hint"] = True
    return sse_event(payload)


def sse_text(chunk: str) -> str:
    return sse_event({"text": chunk})


def sse_jobs(jobs: list[dict[str, Any]]) -> str:
    return sse_event({"jobs": jobs})


def sse_error(message: str) -> str:
    return sse_event({"error": message[:500]})
