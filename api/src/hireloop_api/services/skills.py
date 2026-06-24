"""
Skill canonicalization + bundled vocabulary (HIR — skills expansion).

One shared source of truth so the résumé parser, JD enrichment, the matcher, and
the UI all agree on what a skill is and which variants are the same:

  - CANONICAL_SKILLS  — ~2000 curated skills (normalized tokens) from the bundled
                        taxonomy at ``data/skills_vocab.json``.
  - aliases           — variant → canonical (e.g. "ReactJS" → "react"), so alias
                        variants never dilute skill-overlap scores.

Public API:
  - normalize_skill(s)      → lowercase, separators stripped ("Node.js" → "nodejs")
  - canonical_skill(s)      → normalize + collapse aliases to one canonical token
  - canonical_skill_set(xs) → canonicalized, de-duplicated set (for matching)
  - is_known_skill(s)       → True if it resolves to a vocabulary skill (whitelist)
  - display_skill(s)        → human-readable label for a (canonical) skill
  - suggest_skills(q, n)    → vocabulary suggestions for UI autocomplete

Regenerate the vocabulary with ``uv run python scripts/build_skills_vocab.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_VOCAB_PATH = Path(__file__).resolve().parent.parent / "data" / "skills_vocab.json"


def normalize_skill(s: str) -> str:
    """Lowercase + strip separators ('Node.js' → 'nodejs'); keeps '+'/'#' so
    C++/C# stay distinct."""
    return re.sub(r"[^a-z0-9+#]", "", str(s).lower().strip())


def _load_vocab() -> tuple[frozenset[str], dict[str, str], dict[str, str]]:
    """Load the bundled taxonomy → (canonical token set, normalized→display map,
    normalized alias map). Degrades to a tiny built-in core if the file is missing
    so the service never hard-fails on a packaging slip."""
    try:
        data = json.loads(_VOCAB_PATH.read_text(encoding="utf-8"))
        skill_labels: list[str] = data.get("skills", [])
        raw_aliases: dict[str, str] = data.get("aliases", {})
    except (OSError, ValueError):
        skill_labels = ["Python", "JavaScript", "React", "PostgreSQL", "Kubernetes"]
        raw_aliases = {"reactjs": "React", "postgres": "PostgreSQL", "k8s": "Kubernetes"}

    display: dict[str, str] = {}
    for label in skill_labels:
        token = normalize_skill(label)
        if token:
            display.setdefault(token, label)

    aliases: dict[str, str] = {}
    for variant, canonical in raw_aliases.items():
        nv, nc = normalize_skill(variant), normalize_skill(canonical)
        if nv and nc and nv != nc:
            aliases[nv] = nc

    return frozenset(display), display, aliases


CANONICAL_SKILLS, _DISPLAY, _ALIASES = _load_vocab()


def canonical_skill(s: str) -> str:
    """Normalize, then collapse known aliases to one canonical token."""
    n = normalize_skill(s)
    return _ALIASES.get(n, n)


def canonical_skill_set(skills: list[str] | None) -> set[str]:
    """Canonicalized, de-duplicated skill set (empty strings dropped)."""
    return {c for s in (skills or []) if (c := canonical_skill(s))}


def is_known_skill(s: str) -> bool:
    """True when the input resolves to a skill in the bundled vocabulary —
    used as a whitelist to drop junk extracted from résumés/JDs."""
    return canonical_skill(s) in CANONICAL_SKILLS


def display_skill(s: str) -> str:
    """Human-readable label for a skill (e.g. 'postgres' → 'PostgreSQL'). Falls
    back to a title-cased form when the skill isn't in the vocabulary."""
    c = canonical_skill(s)
    if c in _DISPLAY:
        return _DISPLAY[c]
    return str(s).strip().title()


def suggest_skills(query: str, limit: int = 10) -> list[str]:
    """Vocabulary suggestions for UI autocomplete: prefix matches first, then
    substring matches, both alphabetical. Empty query → []."""
    q = normalize_skill(query)
    if not q:
        return []
    prefix: list[str] = []
    contains: list[str] = []
    for token, label in _DISPLAY.items():
        if token.startswith(q):
            prefix.append(label)
        elif q in token:
            contains.append(label)
    prefix.sort(key=str.lower)
    contains.sort(key=str.lower)
    return (prefix + contains)[:limit]
