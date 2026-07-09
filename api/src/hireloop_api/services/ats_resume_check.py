"""
ATS parseability check for tailored resume HTML (text-layer + keyword coverage).
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_plain_text(html: str) -> str:
    """Strip tags for ATS-style text extraction."""
    text = unescape(html or "")
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _extract_keywords(job: dict[str, Any]) -> list[str]:
    raw: list[str] = []
    raw.extend(job.get("skills_required") or [])
    title = str(job.get("title") or "")
    if title:
        raw.extend(title.lower().split())
    desc = str(job.get("description") or "")[:3000].lower()
    for token in re.findall(r"[a-z][a-z0-9+#.-]{2,}", desc):
        if token not in raw:
            raw.append(token)
    # Dedupe preserving order, cap size
    seen: set[str] = set()
    out: list[str] = []
    for k in raw:
        key = str(k).strip().lower()
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out[:40]


def run_ats_check(
    html: str,
    *,
    profile: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    """Verify contact text, reading order sanity, and keyword coverage."""
    plain = html_to_plain_text(html)
    plain_l = plain.lower()
    issues: list[str] = []

    email = str(profile.get("email") or "").strip()
    phone = str(profile.get("phone") or "").strip()
    name = str(profile.get("full_name") or "").strip()

    contact_ok = True
    if email and email.lower() not in plain_l:
        contact_ok = False
        issues.append("Email not found as plain text in resume.")
    if phone:
        digits = re.sub(r"\D", "", phone)[-10:]
        if digits and digits not in re.sub(r"\D", "", plain):
            contact_ok = False
            issues.append("Phone not found as plain text in resume.")
    if name and name.split()[0].lower() not in plain_l:
        issues.append("Name may not parse clearly at the top.")

    word_count = len(plain.split())
    if word_count > 850:
        issues.append(f"Resume is long ({word_count} words) — may spill past one page.")
    if word_count < 120:
        issues.append("Resume text is very short — ATS may see an incomplete profile.")

    cand_skills = {str(s).lower() for s in (profile.get("skills") or []) if s}
    keywords = _extract_keywords(job)
    hits: list[str] = []
    gaps: list[str] = []
    for kw in keywords:
        if kw in plain_l or kw in cand_skills:
            hits.append(kw)
        elif len(kw) > 3 and kw not in ("with", "and", "the", "for"):
            # Only flag as gap if candidate also lacks the skill
            if kw not in cand_skills:
                gaps.append(kw)

    coverage = round(len(hits) / max(len(keywords), 1), 2)
    score = 1.0
    if not contact_ok:
        score -= 0.35
    if coverage < 0.35:
        score -= 0.2
    if word_count > 850:
        score -= 0.1
    score = round(max(0.0, min(1.0, score)), 2)

    return {
        "parseable": contact_ok and word_count >= 120,
        "contact_ok": contact_ok,
        "word_count": word_count,
        "keyword_coverage": coverage,
        "keywords_hit": hits[:20],
        "keywords_gap": gaps[:12],
        "issues": issues,
        "ats_score": score,
        "summary": (
            f"ATS score {int(score * 100)}% — "
            f"{len(hits)} posting keywords matched, {len(gaps)} honest gaps."
        ),
    }
