"""
Short-lived in-process cache for Aarya tool results (per conversation session).

Avoids re-querying profile_read / job_search when the candidate asks again
within a few minutes in the same chat thread.
"""

from __future__ import annotations

import json
import time
from typing import Any

_DEFAULT_TTL_SEC = 300.0
_store: dict[str, tuple[float, Any]] = {}


def _purge_expired(now: float) -> None:
    expired = [k for k, (ts, _) in _store.items() if now - ts > _DEFAULT_TTL_SEC]
    for k in expired:
        del _store[k]


def cache_key(session_id: str, tool_name: str, args: dict[str, Any] | None = None) -> str:
    payload = json.dumps(args or {}, sort_keys=True, default=str)
    return f"{session_id}:{tool_name}:{payload}"


def get_cached(key: str) -> Any | None:
    now = time.monotonic()
    _purge_expired(now)
    entry = _store.get(key)
    if not entry:
        return None
    ts, value = entry
    if now - ts > _DEFAULT_TTL_SEC:
        del _store[key]
        return None
    return value


def set_cached(key: str, value: Any) -> None:
    _store[key] = (time.monotonic(), value)


def clear_session_tool_cache(session_id: str, tool_name: str | None = None) -> None:
    """Drop cached tool results for a conversation (e.g. after career path lock-in)."""
    prefix = f"{session_id}:{tool_name}:" if tool_name else f"{session_id}:"
    for key in [k for k in _store if k.startswith(prefix)]:
        del _store[key]
