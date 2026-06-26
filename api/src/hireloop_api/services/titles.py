"""
Shared title taxonomy (backend plan #35) — ONE place that turns a job/role title
into canonical tokens, used by the matcher (title affinity) and available to the
parser/ingester. Fixes synonym blindness: "Backend Developer" vs "Backend
Engineer" used to score 1/3 Jaccard; "SDE II" vs "Software Engineer" scored 0.

Two layers:
  1. Abbreviation EXPANSION — one token becomes several ("sde" → software,
     engineer) so Indian-market shorthand matches full titles.
  2. Synonym CANONICALIZATION — token → canonical ("developer", "programmer",
     "coder" → engineer).
Seniority/grade words are stopwords (level is scored by experience_score, not
title affinity).
"""

from __future__ import annotations

import re

_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "for", "to", "in", "at",
        "senior", "junior", "lead", "staff", "principal", "associate",
        "sr", "jr", "i", "ii", "iii", "iv", "v", "1", "2", "3",
        "intern", "trainee", "head", "chief", "vp", "avp", "director",
    }
)  # fmt: skip

# One shorthand token → multiple canonical tokens.
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "sde": ("software", "engineer"),
    "swe": ("software", "engineer"),
    "sdet": ("software", "engineer", "quality"),
    "pm": ("product", "manager"),
    "apm": ("product", "manager"),
    "gtm": ("gotomarket",),
    "tpm": ("technical", "program", "manager"),
    "hr": ("human", "resources"),
    "hrbp": ("human", "resources", "partner"),
    "ba": ("business", "analyst"),
    "da": ("data", "analyst"),
    "ds": ("data", "scientist"),
    "ml": ("machine", "learning"),
    "ai": ("machine", "learning"),
    "qa": ("quality", "engineer"),
    "ui": ("design",),
    "ux": ("design",),
    "uiux": ("design",),
    "sre": ("reliability", "engineer"),
    "cto": ("technology", "leader"),
    "ceo": ("executive", "leader"),
    "coo": ("operations", "leader"),
    "cfo": ("finance", "leader"),
}

# token → canonical token.
_SYNONYMS: dict[str, str] = {
    "developer": "engineer",
    "dev": "engineer",
    "programmer": "engineer",
    "coder": "engineer",
    "engineering": "engineer",
    "frontend": "frontend",
    "front": "frontend",
    "backend": "backend",
    "back": "backend",
    "fullstack": "fullstack",
    "full": "fullstack",
    "stack": "fullstack",
    "end": "_drop_",  # consumed by front/back mapping above
    "tester": "quality",
    "testing": "quality",
    "test": "quality",
    "designer": "design",
    "mgr": "manager",
    "management": "manager",
    "scientist": "scientist",
    "analytics": "analyst",
    "devops": "devops",
    "ops": "operations",
    "recruiter": "recruitment",
    "recruiting": "recruitment",
    "talent": "recruitment",
    "salesperson": "gotomarket",
    "marketer": "marketing",
    "architect": "architect",
    "consultant": "consultant",
    "administrator": "admin",
    # Commercial / go-to-market function cluster: GTM = Growth = Revenue = Sales
    # collapse to ONE function token so "Head of Growth" reads as the same
    # function as "Head of GTM" / "Director of Sales". Precision (level, industry)
    # is enforced by the seniority-fit gate and domain-fit multiplier, so
    # clustering function here is safe.
    "gtm": "gotomarket",
    "growth": "gotomarket",
    "revenue": "gotomarket",
    "sales": "gotomarket",
}


def canonical_title_tokens(title: str | None) -> frozenset[str]:
    """Canonical token set for a role title; empty when unknown."""
    if not title:
        return frozenset()
    # Normalise separators (hyphens/dashes/slash/&) to spaces so multi-word
    # commercial phrases are contiguous, then collapse them to the go-to-market
    # function token (the tokenizer would otherwise split "go-to-market").
    t = re.sub(r"[-\u2010-\u2015_/&]+", " ", title.lower())
    t = t.replace("go to market", "gtm")
    t = t.replace("business development", "sales")
    words = re.findall(r"[a-z0-9+#]+", t)
    out: set[str] = set()
    for w in words:
        if w in _STOPWORDS:
            continue
        if w in _EXPANSIONS:
            out.update(_EXPANSIONS[w])
            continue
        mapped = _SYNONYMS.get(w, w)
        if mapped != "_drop_" and len(mapped) > 1:
            out.add(mapped)
    return frozenset(out)


def title_affinity(a: str | None, b: str | None) -> float | None:
    """0-1 Jaccard over canonical tokens; None when either side is unknown."""
    ta, tb = canonical_title_tokens(a), canonical_title_tokens(b)
    if not ta or not tb:
        return None
    return round(len(ta & tb) / len(ta | tb), 4)
