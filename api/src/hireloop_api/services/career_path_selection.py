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
    "fourth": 3,
    "4th": 3,
}

_AFFIRMATIVE_RE = re.compile(
    r"^(?:"
    r"yes(?:\s+do\s+it)?|yeah|yep|yup|sure|ok(?:ay)?|"
    r"do\s+it|go\s+ahead|please|sounds?\s+good|"
    r"that(?:'s| is)?\s+fine|let'?s\s+do\s+it"
    r")[\s.!]*$",
    re.IGNORECASE,
)

_GENERIC_JOB_SEARCH_RE = re.compile(
    r"\b(?:find|search|show|surface|hunt)\b.*\b(?:job|jobs|role|roles|match|matches|opening|openings)\b",
    re.IGNORECASE,
)

_FIND_ROLE_IN_CITY_RE = re.compile(
    r"\b(?:find|search(?:ing)?\s+for|show(?:\s+me)?|looking\s+for)\s+"
    r"(.+?)\s+in\s+([A-Za-z][\w.-]+)"
    r"(?:\s+for\b|\s+with\b|\s+matching\b|[,.]|$)",
    re.IGNORECASE,
)

_ASSISTANT_SEARCH_FOR_RE = re.compile(
    r"(?:search(?:ing)?\s+for|hunt(?:ing)?\s+for|let me search for)\s+(.+?)"
    r"(?:\s+roles?\b|\s+in\b|\s+at\b|\?|$)",
    re.IGNORECASE,
)


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


def extract_job_search_location(message: str) -> str | None:
    """City from 'Find X in Bengaluru' style queries."""
    _role, city = extract_find_role_and_city(message)
    return city


def extract_find_role_and_city(message: str) -> tuple[str | None, str | None]:
    m = _FIND_ROLE_IN_CITY_RE.search(message or "")
    if not m:
        return None, None
    role = m.group(1).strip().rstrip(".,;")
    city = m.group(2).strip().rstrip(".,;")
    return role or None, city or None


def best_option_match(text: str, options: list[str]) -> str | None:
    """Pick the option that best overlaps with free text (longest win)."""
    if not text or not options:
        return None
    lower = text.lower()
    best: str | None = None
    best_len = 0

    for opt in options:
        opt_lower = opt.lower()
        if opt_lower in lower or lower in opt_lower:
            if len(opt_lower) > best_len:
                best = opt
                best_len = len(opt_lower)
        for segment in re.split(r"[/→\-–|]+", opt):
            seg = segment.strip()
            if len(seg) >= 6 and seg.lower() in lower:
                if len(seg) > best_len:
                    best = opt
                    best_len = len(seg)

    return best


def assistant_implied_option(assistant_message: str, options: list[str]) -> str | None:
    """Infer which path the assistant was about to search from its last reply."""
    text = (assistant_message or "").strip()
    if not text or not options:
        return None

    m = _ASSISTANT_SEARCH_FOR_RE.search(text)
    if m:
        fragment = m.group(1).strip().rstrip(".,;")
        matched = best_option_match(fragment, options)
        if matched:
            return matched

    # Last-mentioned numbered option in assistant text (e.g. "1. Senior Category Manager").
    for i in range(len(options) - 1, -1, -1):
        title = options[i]
        if re.search(
            rf"\b{i + 1}\.\s*{re.escape(title[:24])}",
            text,
            flags=re.IGNORECASE,
        ):
            return title

    return best_option_match(text, options)


def is_affirmative_reply(message: str) -> bool:
    return bool(_AFFIRMATIVE_RE.match((message or "").strip()))


def is_generic_job_search_reply(message: str) -> bool:
    return bool(_GENERIC_JOB_SEARCH_RE.search((message or "").strip()))


def parse_career_path_selection(
    message: str,
    options: list[str],
    *,
    recent_assistant_message: str | None = None,
) -> str | None:
    """
    Map a user reply to one of the offered path titles.
    Handles: "2", chip text, "Find X in City", "Yes do it", full/partial title match.
    """
    text = (message or "").strip()
    if not text or not options:
        return None

    lower = text.lower()

    # Explicit "prioritize …" messages from UI chips (straight or curly quotes).
    m = re.search(
        r"prioritize the ['\"\u2018\u2019\u201c\u201d](.+?)['\"\u2018\u2019\u201c\u201d] career path",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        quoted = m.group(1).strip()
        for opt in options:
            if opt.lower() == quoted.lower():
                return opt
        matched = best_option_match(quoted, options)
        if matched:
            return matched

    # Job-search phrasing: "Find Senior Category Manager - Fashion in Bengaluru …"
    role, _city = extract_find_role_and_city(text)
    if role:
        matched = best_option_match(role, options)
        if matched:
            return matched

    # Numbered pick: last standalone 1–3 in the message (e.g. "Yes, show jobs. 2.")
    nums = [int(n) for n in re.findall(r"\b([1-3])\b", text)]
    if nums:
        idx = nums[-1] - 1
        if 0 <= idx < len(options):
            return options[idx]

    for word, idx in _ORDINAL_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower) and idx < len(options):
            return options[idx]

    # Short affirmatives or generic "find me jobs" replies after Aarya asked the
    # picker should not reopen the same picker. Use the implied/first option.
    if (is_affirmative_reply(text) or is_generic_job_search_reply(text)) and recent_assistant_message:
        implied = assistant_implied_option(recent_assistant_message, options)
        if implied:
            return implied
        assistant_lower = recent_assistant_message.lower()
        if any(
            phrase in assistant_lower
            for phrase in (
                "which one",
                "pick one",
                "lock in one",
                "search for first",
                "should i search",
            )
        ):
            return options[0]

    # Full or strong partial title match.
    matched = best_option_match(text, options)
    if matched:
        return matched

    return None


async def try_apply_career_path_selection(
    db: asyncpg.Connection,
    candidate_id: str,
    message: str,
    *,
    recent_assistant_message: str | None = None,
) -> str | None:
    """
    If the candidate picked a path option, persist prioritized_title.
    Returns the locked title, or None if no selection detected / already set.
    """
    path = await CareerPathService.get_latest(db, candidate_id)
    if not path or path.get("prioritized_title"):
        return None

    options = career_path_options(path)
    chosen = parse_career_path_selection(
        message,
        options,
        recent_assistant_message=recent_assistant_message,
    )
    if not chosen:
        return None

    updated = await CareerPathService.prioritize(db, candidate_id, chosen)
    if not updated:
        return None
    return str(updated.get("prioritized_title") or chosen)
