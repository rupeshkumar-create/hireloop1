"""Resolve career-path option picks from free-text chat (e.g. "2", option titles)."""

from __future__ import annotations

import re
from typing import Any

import asyncpg

from hireloop_api.services.career_path import CareerPathService

_ORDINAL_WORDS: dict[str, int] = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
}


def career_path_options(path: dict[str, Any] | None) -> list[str]:
    """Top 1–3 selectable path titles (matches job_search gate + UI cards)."""
    if not path:
        return []
    from_steps = [
        str(s.get("title") or "").strip()
        for s in (path.get("steps") or [])
        if isinstance(s, dict)
        and s.get("level") in ("next", "future")
        and str(s.get("title") or "").strip()
    ]
    if from_steps:
        return from_steps[:3]
    return [str(t).strip() for t in (path.get("target_titles") or []) if str(t).strip()][:3]


def parse_career_path_selection(message: str, options: list[str]) -> str | None:
    """
    Map a user reply to one of the offered path titles.
    Handles: "2", "option 2", "Yes show jobs 2", full/partial title match.
    """
    text = (message or "").strip()
    if not text or not options:
        return None

    lower = text.lower()

    # Explicit "prioritize …" messages from UI chips.
    m = re.search(
        r'prioritize the ["\u201c](.+?)["\u201d] career path',
        text,
        flags=re.IGNORECASE,
    )
    if m:
        quoted = m.group(1).strip()
        for opt in options:
            if opt.lower() == quoted.lower():
                return opt

    # Numbered pick: last standalone 1–3 in the message (e.g. "Yes, show jobs. 2.")
    nums = [int(n) for n in re.findall(r"\b([1-3])\b", text)]
    if nums:
        idx = nums[-1] - 1
        if 0 <= idx < len(options):
            return options[idx]

    for word, idx in _ORDINAL_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower) and idx < len(options):
            return options[idx]

    # Full or strong partial title match.
    for opt in options:
        opt_lower = opt.lower()
        if opt_lower in lower or lower in opt_lower:
            return opt

    # Partial match on slash-separated segments (e.g. "Head of Buying" → full title).
    for opt in options:
        for segment in re.split(r"[/→\-]+", opt):
            seg = segment.strip()
            if len(seg) >= 8 and seg.lower() in lower:
                return opt

    return None


async def try_apply_career_path_selection(
    db: asyncpg.Connection,
    candidate_id: str,
    message: str,
) -> str | None:
    """
    If the candidate picked a path option, persist prioritized_title.
    Returns the locked title, or None if no selection detected / already set.
    """
    path = await CareerPathService.get_latest(db, candidate_id)
    if not path or path.get("prioritized_title"):
        return None

    options = career_path_options(path)
    chosen = parse_career_path_selection(message, options)
    if not chosen:
        return None

    updated = await CareerPathService.prioritize(db, candidate_id, chosen)
    if not updated:
        return None
    return str(updated.get("prioritized_title") or chosen)
