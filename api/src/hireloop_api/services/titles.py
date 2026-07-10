"""
Shared title taxonomy — occupation families, specialties, seniority, and affinity.

Replaces flat Jaccard over token sets with structured TitleSignature matching.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# ── Seniority / track ─────────────────────────────────────────────────────────

_SENIORITY_RANK: dict[str, int] = {
    "intern": 1,
    "trainee": 1,
    "junior": 2,
    "associate": 2,
    "mid": 3,
    "senior": 4,
    "lead": 5,
    "staff": 5,
    "principal": 6,
    "head": 6,
    "director": 7,
    "vp": 8,
    "avp": 8,
    "chief": 9,
    "c_level": 9,
}

_SENIORITY_WORDS = frozenset(_SENIORITY_RANK.keys()) | frozenset(
    {"sr", "jr", "i", "ii", "iii", "iv", "v", "1", "2", "3"}
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "for",
        "to",
        "in",
        "at",
        "team",
        "leader",
    }
)

_GENERIC_ROLE_NOUNS = frozenset(
    {
        "manager",
        "engineer",
        "analyst",
        "specialist",
        "consultant",
        "executive",
        "officer",
        "admin",
        "administrator",
        "leader",
        "design",
        "scientist",
        "developer",
        "architect",
        "coordinator",
        "associate",
        "representative",
        "partner",
    }
)

# Engineering specialty compatibility (adjacent specialties allowed)
_SPECIALTY_COMPATIBILITY: dict[str, frozenset[str]] = {
    "fullstack": frozenset({"frontend", "backend", "fullstack"}),
    "backend": frozenset({"backend", "fullstack", "platform", "api", "devops"}),
    "frontend": frozenset({"frontend", "fullstack", "ui", "mobile"}),
    "reliability": frozenset({"reliability", "devops", "platform", "infrastructure", "cloud"}),
    "devops": frozenset({"devops", "reliability", "platform", "infrastructure", "cloud"}),
    "mobile": frozenset({"mobile", "android", "ios", "frontend"}),
    "quality": frozenset({"quality", "automation", "sdet", "testing"}),
    "platform": frozenset({"platform", "backend", "devops", "reliability"}),
}

# Commercial function families — related but NOT identical
_COMMERCIAL_FUNCTIONS = frozenset(
    {
        "sales",
        "business_development",
        "growth_marketing",
        "revenue_operations",
        "partnerships",
        "customer_success",
        "gotomarket_strategy",
    }
)

_COMMERCIAL_RELATED: dict[str, frozenset[str]] = {
    "sales": frozenset({"sales", "business_development"}),
    "business_development": frozenset({"sales", "business_development", "partnerships"}),
    "growth_marketing": frozenset({"growth_marketing", "marketing"}),
    "revenue_operations": frozenset({"revenue_operations", "operations"}),
    "partnerships": frozenset({"partnerships", "business_development"}),
    "customer_success": frozenset({"customer_success", "account_management"}),
    "gotomarket_strategy": frozenset({"gotomarket_strategy", "product", "marketing"}),
    "marketing": frozenset({"marketing", "growth_marketing"}),
    "account_management": frozenset({"account_management", "customer_success", "sales"}),
    "operations": frozenset({"operations", "revenue_operations"}),
}

# Phrase-level normalizations (before tokenization)
_PHRASE_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfront[\s-]?end\b", re.I), "frontend"),
    (re.compile(r"\bback[\s-]?end\b", re.I), "backend"),
    (re.compile(r"\bfull[\s-]?stack\b", re.I), "fullstack"),
    (re.compile(r"\bgo[\s-]?to[\s-]?market\b", re.I), "gtm"),
    (re.compile(r"\bbusiness[\s-]?development\b", re.I), "bizdev"),
    (re.compile(r"\bc\+\+\b", re.I), "cpp"),
    (re.compile(r"\bc#\b", re.I), "csharp"),
    (re.compile(r"\b\.net\b", re.I), "dotnet"),
    (re.compile(r"\bnode\.js\b", re.I), "nodejs"),
    (re.compile(r"\bpower[\s-]?bi\b", re.I), "powerbi"),
    (re.compile(r"\bs/4hana\b", re.I), "s4hana"),
]

# Protected short tokens from structured extraction only
_PROTECTED_SHORT = frozenset({"ai", "ml", "go", "r", "ui", "ux", "qa", "hr", "pm", "rn", "it"})

# Unambiguous expansions
_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "sde": ("software", "engineer"),
    "swe": ("software", "engineer"),
    "sdet": ("software", "engineer", "quality"),
    "hrbp": ("human", "resources", "partner"),
    "sre": ("reliability", "engineer"),
    "qa": ("quality",),
    "tpm": ("technical", "program", "manager"),
    "uiux": ("design",),
    "bizdev": ("business", "development"),
}

# Ambiguous — do not auto-expand without context
_AMBIGUOUS_ABBREVS = frozenset({"pm", "apm", "ba", "da", "ds", "am", "ae", "se", "ta", "cs", "pr"})

_SYNONYMS: dict[str, str] = {
    "developer": "engineer",
    "dev": "engineer",
    "programmer": "engineer",
    "coder": "engineer",
    "engineering": "engineer",
    "tester": "quality",
    "testing": "quality",
    "test": "quality",
    "designer": "design",
    "mgr": "manager",
    "management": "manager",
    "analytics": "analyst",
    "recruiter": "recruitment",
    "recruiting": "recruitment",
    "salesperson": "sales",
    "marketer": "marketing",
    "administrator": "admin",
    "gtm": "gotomarket_strategy",
    "growth": "growth_marketing",
    "revenue": "revenue_operations",
    # sales stays sales — NOT collapsed to gotomarket
}

# Occupation family detection from token sets
_FAMILY_PATTERNS: list[tuple[str, frozenset[str]]] = [
    ("engineering_management", frozenset({"engineer", "manager"})),
    ("software_engineering", frozenset({"software", "engineer"})),
    ("data_science", frozenset({"data", "scientist"})),
    ("data_analytics", frozenset({"data", "analyst"})),
    ("product_management", frozenset({"product", "manager"})),
    ("project_management", frozenset({"project", "manager"})),
    ("program_management", frozenset({"program", "manager"})),
    ("category_management", frozenset({"category", "manager"})),
    ("merchandising", frozenset({"merchandising", "manager"})),
    ("human_resources", frozenset({"human", "resources"})),
    ("quality_engineering", frozenset({"quality", "engineer"})),
    ("design", frozenset({"design"})),
    ("marketing", frozenset({"marketing"})),
    ("sales", frozenset({"sales"})),
    ("finance", frozenset({"finance"})),
    ("operations", frozenset({"operations"})),
    ("customer_success", frozenset({"customer", "success"})),
    ("nursing", frozenset({"nurse", "registered"})),
    ("nursing_single", frozenset({"nursing"})),
]

_ENGINEERING_SPECIALTIES = frozenset(
    {
        "backend",
        "frontend",
        "mobile",
        "fullstack",
        "devops",
        "quality",
        "reliability",
        "platform",
        "api",
    }
)
_SCIENCE_TOKENS = frozenset({"scientist", "machine", "learning", "science", "data"})


@dataclass(frozen=True)
class TitleSignature:
    normalized_title: str
    role_id: str | None
    family_id: str | None
    functions: frozenset[str]
    specialties: frozenset[str]
    level: int | None
    track: str | None  # ic | management | unknown
    residual_tokens: frozenset[str]
    ambiguous: bool
    confidence: float
    candidate_interpretations: tuple[str, ...] = ()


def _normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _apply_phrase_replacements(text: str) -> str:
    out = text
    for pattern, replacement in _PHRASE_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    return out


def _tokenize_title(title: str) -> list[str]:
    t = _apply_phrase_replacements(_normalize_text(title))
    t = re.sub(r"[-\u2010-\u2015_/&]+", " ", t)
    return re.findall(r"[^\W_]+", t, flags=re.UNICODE)


def _extract_seniority(words: list[str]) -> tuple[int | None, str | None, list[str]]:
    """Return (level, track, remaining_words)."""
    level: int | None = None
    track = "unknown"
    remaining: list[str] = []
    for w in words:
        if w in _SENIORITY_WORDS:
            mapped = _SENIORITY_RANK.get(w)
            if mapped:
                level = max(level or 0, mapped)
            if w in {"head", "director", "vp", "avp", "chief", "c_level"}:
                track = "management"
            elif w in {"lead", "staff", "principal"} and track != "management":
                track = "ic"
            continue
        if w in _STOPWORDS:
            continue
        remaining.append(w)
    return level, track, remaining


def _detect_family(tokens: frozenset[str]) -> str | None:
    for family_id, pattern in _FAMILY_PATTERNS:
        if pattern.issubset(tokens):
            return family_id
    return None


def _detect_functions(tokens: frozenset[str]) -> frozenset[str]:
    funcs: set[str] = set()
    for fn in _COMMERCIAL_FUNCTIONS:
        if fn in tokens:
            funcs.add(fn)
    if "sales" in tokens:
        funcs.add("sales")
    if "marketing" in tokens:
        funcs.add("marketing")
    if "product" in tokens and "manager" in tokens:
        funcs.add("product_management")
    if "project" in tokens and "manager" in tokens:
        funcs.add("project_management")
    if "program" in tokens and "manager" in tokens:
        funcs.add("program_management")
    return frozenset(funcs)


def parse_title(title: str | None) -> TitleSignature:
    """Structured occupation representation for matching and query planning."""
    if not title or not str(title).strip():
        return TitleSignature(
            normalized_title="",
            role_id=None,
            family_id=None,
            functions=frozenset(),
            specialties=frozenset(),
            level=None,
            track=None,
            residual_tokens=frozenset(),
            ambiguous=True,
            confidence=0.0,
        )

    raw_words = _tokenize_title(str(title))
    level, track, words = _extract_seniority(raw_words)

    ambiguous = False
    interpretations: list[str] = []
    tokens: set[str] = set()
    specialties: set[str] = set()

    for w in words:
        if w in _AMBIGUOUS_ABBREVS:
            ambiguous = True
            if w == "pm":
                interpretations.extend(["product_manager", "project_manager", "program_manager"])
                # Senior/lead PM in India almost always means product management.
                if level is not None and level >= _SENIORITY_RANK["senior"]:
                    tokens.update({"product", "manager"})
                    ambiguous = False
            elif w == "apm":
                interpretations.extend(["associate_product_manager", "assistant_project_manager"])
            elif w == "ba":
                interpretations.extend(["business_analyst", "brand_ambassador"])
            elif w == "da":
                interpretations.extend(["data_analyst"])
            elif w == "ds":
                interpretations.extend(["data_scientist"])
            # Keep ambiguous token for partial matching
            tokens.add(w)
            continue
        if w in _EXPANSIONS:
            tokens.update(_EXPANSIONS[w])
            continue
        mapped = _SYNONYMS.get(w, w)
        if mapped in _ENGINEERING_SPECIALTIES:
            specialties.add(mapped)
        elif len(mapped) > 1:
            tokens.add(mapped)

    token_frozen = frozenset(tokens)
    family_id = _detect_family(token_frozen | specialties)
    if (
        not family_id
        and specialties & _ENGINEERING_SPECIALTIES
        and ("engineer" in token_frozen or "developer" in token_frozen)
    ):
        family_id = "software_engineering"
    functions = _detect_functions(token_frozen)
    role_id = family_id
    if ambiguous and not family_id:
        confidence = 0.35
    elif family_id:
        confidence = 0.85 if not ambiguous else 0.65
    else:
        confidence = 0.5 if token_frozen else 0.2

    return TitleSignature(
        normalized_title=" ".join(raw_words),
        role_id=role_id,
        family_id=family_id,
        functions=functions,
        specialties=frozenset(specialties),
        level=level,
        track=track,
        residual_tokens=token_frozen,
        ambiguous=ambiguous,
        confidence=confidence,
        candidate_interpretations=tuple(interpretations),
    )


def canonical_title_tokens(title: str | None) -> frozenset[str]:
    """Backward-compatible token set from TitleSignature."""
    sig = parse_title(title)
    out = set(sig.residual_tokens) | set(sig.specialties)
    if sig.family_id:
        for fam_id, pattern in _FAMILY_PATTERNS:
            if fam_id == sig.family_id:
                out.update(pattern)
    return frozenset(out)


def specialties_compatible(required: frozenset[str], job: frozenset[str]) -> bool:
    """True when engineering specialties are exact or adjacent."""
    if not required or not job:
        return True
    for req in required:
        compatible = _SPECIALTY_COMPATIBILITY.get(req, frozenset({req}))
        if job & compatible:
            return True
    return False


def _occupation_score(sig_a: TitleSignature, sig_b: TitleSignature) -> float:
    if sig_a.family_id and sig_b.family_id:
        if sig_a.family_id == sig_b.family_id:
            return 1.0
        # Adjacent families
        adjacent = {
            ("product_management", "project_management"): 0.22,
            ("product_management", "program_management"): 0.28,
            ("project_management", "program_management"): 0.35,
            ("category_management", "merchandising"): 0.65,
            ("data_science", "data_analytics"): 0.5,
            ("data_science", "software_engineering"): 0.25,
            ("quality_engineering", "software_engineering"): 0.62,
        }
        key = (sig_a.family_id, sig_b.family_id)
        rev = (sig_b.family_id, sig_a.family_id)
        if key in adjacent:
            return adjacent[key]
        if rev in adjacent:
            return adjacent[rev]
        return 0.0

    # Function overlap for commercial roles
    if sig_a.functions and sig_b.functions:
        if sig_a.functions & sig_b.functions:
            return 1.0
        for fn_a in sig_a.functions:
            related = _COMMERCIAL_RELATED.get(fn_a, frozenset({fn_a}))
            if sig_b.functions & related:
                return 0.45
        return 0.0

    # Token overlap with generic-noun guard
    ta, tb = sig_a.residual_tokens | sig_a.specialties, sig_b.residual_tokens | sig_b.specialties
    if not ta or not tb:
        return 0.0
    specific_a = ta - _GENERIC_ROLE_NOUNS
    specific_b = tb - _GENERIC_ROLE_NOUNS
    overlap = ta & tb
    specific_overlap = specific_a & specific_b
    if not specific_overlap and overlap <= _GENERIC_ROLE_NOUNS:
        return 0.0

    def weight(tok: str) -> float:
        return 0.15 if tok in _GENERIC_ROLE_NOUNS else 1.0

    intersection = sum(weight(t) for t in overlap)
    union = sum(weight(t) for t in ta | tb)
    return round(intersection / union, 4) if union else 0.0


def _specialty_score(sig_a: TitleSignature, sig_b: TitleSignature) -> float:
    if not sig_a.specialties and not sig_b.specialties:
        return 1.0
    if not sig_a.specialties or not sig_b.specialties:
        return 0.7
    if sig_a.specialties & sig_b.specialties:
        return 1.0
    if specialties_compatible(sig_a.specialties, sig_b.specialties):
        return 0.65
    return 0.0


def _seniority_score(sig_a: TitleSignature, sig_b: TitleSignature) -> float:
    if sig_a.level is None or sig_b.level is None:
        return 0.7
    gap = abs(sig_a.level - sig_b.level)
    if gap == 0:
        return 1.0
    if gap == 1:
        return 0.85
    if gap == 2:
        return 0.6
    if gap >= 4:
        return 0.05
    return 0.4


def _track_score(sig_a: TitleSignature, sig_b: TitleSignature) -> float:
    if sig_a.track == "unknown" or sig_b.track == "unknown":
        return 0.8
    if sig_a.track == sig_b.track:
        return 1.0
    if {sig_a.track, sig_b.track} == {"ic", "management"}:
        return 0.35
    return 0.7


def title_affinity(a: str | None, b: str | None) -> float | None:
    """Feature-based title fit 0-1; None when either side is empty."""
    if not a or not b:
        return None
    sig_a, sig_b = parse_title(a), parse_title(b)
    if not sig_a.residual_tokens and not sig_a.specialties and not sig_a.family_id:
        return None
    if not sig_b.residual_tokens and not sig_b.specialties and not sig_b.family_id:
        return None

    occ = _occupation_score(sig_a, sig_b)
    spec = _specialty_score(sig_a, sig_b)
    sen = _seniority_score(sig_a, sig_b)
    trk = _track_score(sig_a, sig_b)

    # Unrelated occupations must not inherit high scores from seniority/track alone.
    if occ < 0.35:
        spec = min(spec, 0.35)
        sen = min(sen, 0.45)
        trk = min(trk, 0.55)

    score = 0.55 * occ + 0.20 * spec + 0.15 * sen + 0.10 * trk

    if sig_a.family_id and sig_b.family_id and sig_a.family_id != sig_b.family_id:
        score = min(score, 0.34)

    return round(min(1.0, max(0.0, score)), 4)


def occupation_families_compatible(candidate_titles: list[str], job_title: str | None) -> bool:
    """Hard gate: reject obvious wrong occupation families."""
    job_sig = parse_title(job_title)
    if not job_sig.family_id and not job_sig.specialties:
        return True

    intent_families: list[str] = []
    for title in candidate_titles:
        sig = parse_title(title)
        if sig.family_id and sig.confidence >= 0.5:
            intent_families.append(sig.family_id)

    if intent_families and job_sig.family_id:
        if job_sig.family_id in intent_families:
            pass  # same family OK
        else:
            # Any intent title with strong family match to job?
            any_close = any((title_affinity(t, job_title) or 0.0) >= 0.45 for t in candidate_titles)
            if not any_close:
                return False

    req_specialties: set[str] = set()
    candidate_science = False
    for title in candidate_titles:
        sig = parse_title(title)
        req_specialties.update(sig.specialties)
        if (
            sig.family_id in ("data_science", "data_analytics")
            or sig.residual_tokens & _SCIENCE_TOKENS
        ):
            candidate_science = True

    if req_specialties and job_sig.specialties:
        if not specialties_compatible(frozenset(req_specialties), job_sig.specialties):
            return False

    if candidate_science and job_sig.family_id == "software_engineering":
        if not (job_sig.residual_tokens & _SCIENCE_TOKENS or job_sig.family_id == "data_science"):
            if "quality" not in job_sig.specialties:
                return False

    # Reject clearly unrelated families (e.g. engineering vs nursing)
    if intent_families and job_sig.family_id:
        engineering_families = {
            "software_engineering",
            "quality_engineering",
            "data_science",
            "data_analytics",
        }
        non_tech_families = {
            "nursing",
            "human_resources",
            "finance",
            "merchandising",
            "category_management",
        }
        cand_eng = any(f in engineering_families for f in intent_families)
        job_non_tech = job_sig.family_id in non_tech_families
        job_eng = job_sig.family_id in engineering_families
        cand_non_tech = any(f in non_tech_families for f in intent_families)
        if cand_eng and job_non_tech:
            return False
        if cand_non_tech and job_eng and job_sig.family_id not in intent_families:
            return False

    return True


def intent_titles(candidate: dict[str, Any]) -> list[str]:
    """Titles the candidate wants next — primary matching intent."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (
        [candidate.get("prioritized_title")]
        + list(candidate.get("target_titles") or [])
        + ([candidate.get("looking_for")] if candidate.get("looking_for") else [])
    ):
        if not raw:
            continue
        cleaned = str(raw).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def evidence_titles(candidate: dict[str, Any]) -> list[str]:
    """Historical/current titles — transferability only, not primary gates."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in [candidate.get("current_title"), *(candidate.get("previous_titles") or [])]:
        if not raw:
            continue
        cleaned = str(raw).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def best_intent_title_affinity(job_title: str | None, candidate: dict[str, Any]) -> float:
    """Max affinity against intent titles only."""
    titles = intent_titles(candidate)
    if not titles:
        titles = evidence_titles(candidate)
    scores = [s for t in titles if (s := title_affinity(t, job_title)) is not None]
    return max(scores) if scores else 0.0
