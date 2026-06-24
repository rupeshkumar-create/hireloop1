"""Candidate remote / on-site job search preferences."""

from __future__ import annotations

import json

REMOTE_PREFERENCE_ANY = "any"
REMOTE_PREFERENCE_REMOTE_ONLY = "remote_only"
REMOTE_PREFERENCE_ONSITE_ONLY = "onsite_only"

VALID_REMOTE_PREFERENCES = frozenset(
    {
        REMOTE_PREFERENCE_ANY,
        REMOTE_PREFERENCE_REMOTE_ONLY,
        REMOTE_PREFERENCE_ONSITE_ONLY,
    }
)


def normalize_remote_preference(value: str | None) -> str:
    if value in VALID_REMOTE_PREFERENCES:
        return value
    return REMOTE_PREFERENCE_ANY


def resolve_remote_preference(
    *,
    stored: str | None,
    override: str | None = None,
) -> str:
    """Persisted preference unless the caller passes a one-off override."""
    if override in VALID_REMOTE_PREFERENCES:
        return override
    return normalize_remote_preference(stored)


def remote_filter_sql(preference: str) -> str:
    """
    SQL fragment appended to job queries (preference must be normalized first).
    """
    pref = normalize_remote_preference(preference)
    if pref == REMOTE_PREFERENCE_REMOTE_ONLY:
        return " AND j.is_remote = TRUE"
    if pref == REMOTE_PREFERENCE_ONSITE_ONLY:
        return " AND j.is_remote = FALSE"
    return ""


def preference_label(preference: str) -> str:
    pref = normalize_remote_preference(preference)
    if pref == REMOTE_PREFERENCE_REMOTE_ONLY:
        return "remote only"
    if pref == REMOTE_PREFERENCE_ONSITE_ONLY:
        return "on-site only (no remote)"
    return "remote and on-site"


# ── Negative preferences (#37) — "not interested in X" ─────────────────────────
# Stored on candidates.aarya_state.negative_preferences as lowercased lists:
#   {"companies": [...], "titles": [...]}
# A job is hard-filtered from the feed when its company matches an excluded
# company, or its title contains an excluded title/keyword.

NEGATIVE_PREFS_KEY = "negative_preferences"
_NEG_KINDS = ("companies", "titles")


def _coerce_state(state: object) -> dict:
    if isinstance(state, dict):
        return state
    if isinstance(state, str) and state.strip():
        try:
            obj = json.loads(state)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def extract_negative_preferences(state: object) -> tuple[frozenset[str], frozenset[str]]:
    """Return (excluded_companies, excluded_titles) as lowercased frozensets."""
    neg = _coerce_state(state).get(NEGATIVE_PREFS_KEY)
    if not isinstance(neg, dict):
        return frozenset(), frozenset()
    companies = {str(c).strip().lower() for c in (neg.get("companies") or []) if str(c).strip()}
    titles = {str(t).strip().lower() for t in (neg.get("titles") or []) if str(t).strip()}
    return frozenset(companies), frozenset(titles)


def apply_negative_preference(
    state: object, *, kind: str, value: str, remove: bool = False
) -> dict:
    """Add/remove a value to a negative-preference list, returning the new state."""
    if kind not in _NEG_KINDS:
        raise ValueError(f"kind must be one of {_NEG_KINDS}")
    new_state = dict(_coerce_state(state))
    neg = dict(new_state.get(NEGATIVE_PREFS_KEY) or {})
    current = [str(v).strip() for v in (neg.get(kind) or []) if str(v).strip()]
    v = value.strip()
    if remove:
        current = [c for c in current if c.lower() != v.lower()]
    elif v and v.lower() not in {c.lower() for c in current}:
        current.append(v)
    neg[kind] = current[:50]  # bound the list
    new_state[NEGATIVE_PREFS_KEY] = neg
    return new_state
