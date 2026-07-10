"""
Inclusive-language / bias scan for recruiter job descriptions.
Rule-based (no LLM required) with optional LLM rewrite suggestions.
"""

from __future__ import annotations

import re
from typing import Any

# Patterns grouped by category — deterministic for tests and fast UX.
_BIAS_PATTERNS: list[tuple[str, str, str, str]] = [
    # category, pattern, flag, suggestion
    (
        "gender",
        r"\b(he|she|his|her|him|guys|manpower|man\-hours)\b",
        "Gendered language may discourage qualified applicants",
        "Use gender-neutral terms (they, team, staff hours)",
    ),
    (
        "gender",
        r"\b(ninja|rockstar|guru|superhero|dominant|aggressive)\b",
        "Masculine-coded or bro-culture terms",
        "Use specific skill descriptors (e.g. experienced, skilled, collaborative)",
    ),
    (
        "age",
        r"\b(young|youthful|digital native|recent graduate only|fresh out of college)\b",
        "Age-biased language",
        "Focus on skills and experience level, not age",
    ),
    (
        "age",
        r"\b(energetic|high energy)\b",
        "Potentially age-coded language",
        "Describe pace or workload instead (fast-paced, dynamic environment)",
    ),
    (
        "exclusion",
        r"\b(native english speaker|mother tongue|local only|indian only)\b",
        "Potentially exclusionary requirement",
        "State communication proficiency needed for the role instead",
    ),
    (
        "disability",
        r"\b(must be able to stand|must be able to lift|perfect vision|able-bodied)\b",
        "Physical requirements without accommodation framing",
        "List essential job functions; note reasonable accommodations available",
    ),
    (
        "degree",
        r"\b(bachelor'?s required|degree required|mba required)\b",
        "Rigid degree requirement",
        "Consider 'degree or equivalent experience' if skills matter more",
    ),
]

_COMPILED = [
    (cat, re.compile(pat, re.IGNORECASE), flag, suggestion)
    for cat, pat, flag, suggestion in _BIAS_PATTERNS
]


def scan_jd_bias(jd_text: str | None) -> dict[str, Any]:
    """Scan JD text for inclusive-hiring issues. Returns report dict."""
    text = (jd_text or "").strip()
    if len(text) < 20:
        return {
            "passed": True,
            "score": 100,
            "issues": [],
            "summary": "Add a job description to run the bias check.",
        }

    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for category, pattern, flag, suggestion in _COMPILED:
        for match in pattern.finditer(text):
            phrase = match.group(0)
            key = f"{category}:{phrase.lower()}"
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                {
                    "category": category,
                    "phrase": phrase,
                    "message": flag,
                    "suggestion": suggestion,
                }
            )

    # Score: start at 100, deduct per issue (min 0)
    score = max(0, 100 - len(issues) * 12)
    passed = len(issues) == 0

    if passed:
        summary = "No major bias flags detected. Good to publish."
    elif len(issues) == 1:
        summary = "1 potential issue found — review before publishing."
    else:
        summary = f"{len(issues)} potential issues found — review suggested rewrites."

    return {
        "passed": passed,
        "score": score,
        "issues": issues[:20],
        "summary": summary,
    }
