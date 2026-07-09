"""
Relevance-weighted resume trimming when HTML exceeds one-page budget.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from hireloop_api.services.ats_resume_check import html_to_plain_text

_LI_RE = re.compile(r"(<li[^>]*>)(.*?)(</li>)", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _job_terms(job: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for s in job.get("skills_required") or []:
        terms.add(str(s).lower())
    for part in str(job.get("title") or "").lower().split():
        if len(part) > 2:
            terms.add(part)
    for token in re.findall(r"[a-z]{3,}", str(job.get("description") or "").lower()):
        terms.add(token)
    return terms


def _bullet_relevance(text: str, terms: set[str]) -> float:
    plain = unescape(_TAG_RE.sub(" ", text)).lower()
    if not plain.strip():
        return 0.0
    hits = sum(1 for t in terms if t in plain)
    return hits / max(len(terms) * 0.05, 1.0)


def trim_resume_html_for_job(
    html: str,
    *,
    job: dict[str, Any],
    max_words: int = 720,
) -> tuple[str, dict[str, Any]]:
    """Drop lowest-relevance bullets until word count is within budget."""
    plain = html_to_plain_text(html)
    words = len(plain.split())
    if words <= max_words:
        return html, {"trimmed": False, "words_before": words, "words_after": words}

    terms = _job_terms(job)
    bullets: list[tuple[float, str, re.Match[str]]] = []
    for m in _LI_RE.finditer(html):
        score = _bullet_relevance(m.group(2), terms)
        bullets.append((score, m.group(0), m))

    if not bullets:
        return html, {"trimmed": False, "words_before": words, "words_after": words}

    bullets.sort(key=lambda x: x[0])
    trimmed_html = html
    removed = 0
    for _score, _full, match in bullets:
        if len(html_to_plain_text(trimmed_html).split()) <= max_words:
            break
        trimmed_html = trimmed_html.replace(match.group(0), "", 1)
        removed += 1

    after = len(html_to_plain_text(trimmed_html).split())
    return trimmed_html, {
        "trimmed": removed > 0,
        "bullets_removed": removed,
        "words_before": words,
        "words_after": after,
    }
