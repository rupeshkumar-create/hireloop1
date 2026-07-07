"""
Ranking & presentation layer for the candidate match feed (P10/P11).

Turns raw scored matches into an *impressive first screen*. Everything here is
pure and deterministic — plain dicts in, plain dicts out, no DB / network / LLM —
so it is trivially testable and needs no API keys:

  * `score_to_tier`        — map a 0-1 score to a human confidence badge.
  * `dedupe_jobs`          — collapse the same role appearing from two sources.
  * `job_similarity`       — 0-1 likeness of two postings (company/title/etc).
  * `mmr_diversify`        — Maximal Marginal Relevance re-rank for variety.
  * `passes_hard_constraints` — deal-breaker filter (remote pref, CTC floor…).
  * `assemble_first_screen`— dedupe + diversify the opening screen so the user
                             doesn't see eight near-identical cards on load.

Design note: hard constraints are *filters* (a remote-only candidate should
never see an on-site role), while everything else is a soft score. Keeping that
split is what stops the feed from looking "dumb" on first view.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Confidence tiers ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tier:
    key: str
    label: str


# Thresholds are intentionally generous at the top so a strong cold-start match
# reads as "Strong fit" rather than a lukewarm percentage.
_TIERS: tuple[tuple[float, Tier], ...] = (
    (0.80, Tier("strong", "Strong fit")),
    (0.62, Tier("good", "Good match")),
    (0.45, Tier("worth_a_look", "Worth a look")),
    (0.0, Tier("exploratory", "Exploratory")),
)


def score_to_tier(score: float) -> Tier:
    """Map an overall 0-1 score to a confidence badge for the UI."""
    s = max(0.0, min(1.0, float(score)))
    for threshold, tier in _TIERS:
        if s >= threshold:
            return tier
    return _TIERS[-1][1]


# ── Job similarity (for de-dup + diversity) ───────────────────────────────────

_TITLE_STOPWORDS = frozenset(
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
        "senior",
        "junior",
        "lead",
        "staff",
        "principal",
        "i",
        "ii",
        "iii",
        "sr",
        "jr",
    }
)


def _title_tokens(title: str | None) -> frozenset[str]:
    if not title:
        return frozenset()
    words = re.findall(r"[a-z0-9+#]+", title.lower())
    return frozenset(w for w in words if w not in _TITLE_STOPWORDS and len(w) > 1)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def job_similarity(a: dict, b: dict) -> float:
    """
    0-1 similarity between two job postings, used for de-dup and MMR diversity.

    Weighted: same company (0.45) + title-token Jaccard (0.30) +
    same seniority (0.15) + same city (0.10).
    """
    sim = 0.0

    company_a, company_b = _norm(a.get("company_name")), _norm(b.get("company_name"))
    if company_a and company_a == company_b:
        sim += 0.45

    ta, tb = _title_tokens(a.get("title")), _title_tokens(b.get("title"))
    if ta and tb:
        jaccard = len(ta & tb) / len(ta | tb)
        sim += 0.30 * jaccard

    sen_a, sen_b = _norm(a.get("seniority")), _norm(b.get("seniority"))
    if sen_a and sen_a == sen_b:
        sim += 0.15

    city_a, city_b = _norm(a.get("location_city")), _norm(b.get("location_city"))
    if city_a and city_a == city_b:
        sim += 0.10

    return min(1.0, sim)


# ── De-duplication ────────────────────────────────────────────────────────────


def _normalize_url(url: str | None) -> str:
    """
    Canonicalise an apply URL for dedup: drop scheme, query, and fragment, and
    the trailing slash; lower-case. So the same posting at `?utm=…`, with a
    trailing slash, or http-vs-https collapses to one key.
    """
    if not url:
        return ""
    u = str(url).strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = u.split("?", 1)[0].split("#", 1)[0]
    return u.rstrip("/")


def dedupe_jobs(
    items: list[dict],
    *,
    score_key: str = "overall_score",
    threshold: float = 0.85,
) -> list[dict]:
    """
    Drop near-duplicate postings (the same role surfaced by two sources/ATSs, or
    re-posted across daily/weekly runs). Keeps the highest-scoring representative.

    Two items are duplicates when their canonicalised apply_url matches, or their
    `job_similarity` is >= `threshold` (default 0.85 → same company + same title
    catches cross-source dupes even when seniority/city differ slightly).
    """
    kept: list[dict] = []
    seen_urls: set[str] = set()

    for item in sorted(items, key=lambda it: float(it.get(score_key) or 0.0), reverse=True):
        url = _normalize_url(item.get("apply_url"))
        if url and url in seen_urls:
            continue
        if any(job_similarity(item, k) >= threshold for k in kept):
            continue
        kept.append(item)
        if url:
            seen_urls.add(url)

    return kept


def boost_by_saved(
    items: list[dict],
    saved_jobs: list[dict],
    *,
    score_key: str = "overall_score",
    output_key: str | None = None,
    max_boost: float = 0.12,
) -> list[dict]:
    """
    Personalise the feed from the candidate's saved jobs: nudge an item's score
    up in proportion to how much it resembles something they've already saved
    (same company / title / seniority / city signal, via `job_similarity`).

    Writes `max_boost * best_similarity_to_any_saved_job` to `output_key` when
    provided, leaving `score_key` untouched for display. Without `output_key`,
    the historical behaviour is preserved and `score_key` is updated in-place.
    Records `saved_affinity` for transparency. No-op when nothing is saved, so
    it never hurts a cold-start feed.
    """
    if not saved_jobs:
        return items
    for item in items:
        affinity = max((job_similarity(item, s) for s in saved_jobs), default=0.0)
        item["saved_affinity"] = round(affinity, 4)
        base = float(item.get(score_key) or 0.0)
        boosted = round(min(1.0, base + max_boost * affinity), 4) if affinity > 0 else base
        item[output_key or score_key] = boosted
    return items


# ── Hard constraints (deal-breakers) ──────────────────────────────────────────


@dataclass(frozen=True)
class HardConstraints:
    remote_preference: str = "any"  # any | remote_only | onsite_only
    ctc_floor: int | None = None  # candidate's minimum acceptable CTC (INR p.a.)
    # Fraction of the floor a job's ceiling may still satisfy (negotiation slack).
    ctc_slack: float = 0.8
    # #37: candidate "not interested" lists (lowercased). A job is dropped when
    # its company matches an excluded company, or its title contains an excluded
    # title/keyword. Repeated bad matches erode trust fastest, so these are hard.
    excluded_companies: frozenset[str] = frozenset()
    excluded_titles: frozenset[str] = frozenset()


def passes_hard_constraints(job: dict, c: HardConstraints) -> bool:
    """Return False for deal-breakers that should be filtered out entirely."""
    is_remote = bool(job.get("is_remote"))

    if c.remote_preference == "remote_only" and not is_remote:
        return False
    if c.remote_preference == "onsite_only" and is_remote:
        return False

    if c.ctc_floor:
        ceiling = job.get("ctc_max") or job.get("ctc_min")
        # Only reject when the job *states* a band below the candidate's floor
        # (minus slack). Unknown pay is never a deal-breaker.
        if ceiling is not None and ceiling < c.ctc_floor * c.ctc_slack:
            return False

    if c.excluded_companies:
        company = _norm(job.get("company_name"))
        if company and company in c.excluded_companies:
            return False

    if c.excluded_titles:
        title = (job.get("title") or "").lower()
        if any(kw in title for kw in c.excluded_titles):
            return False

    return True


# ── MMR diversification ───────────────────────────────────────────────────────


def mmr_diversify(
    items: list[dict],
    *,
    k: int,
    lambda_: float = 0.72,
    score_key: str = "overall_score",
) -> list[dict]:
    """
    Greedy Maximal Marginal Relevance re-rank of the first `k` slots.

    Each pick maximises `lambda_ * relevance - (1 - lambda_) * max_similarity`
    to the already-selected set, so the opening screen stays high-relevance but
    avoids eight near-identical cards. Items beyond `k` keep their relevance
    order and are appended unchanged.
    """
    if k <= 1 or len(items) <= 1:
        return list(items)

    pool = list(items)
    selected: list[dict] = []

    while pool and len(selected) < k:
        if not selected:
            best = max(pool, key=lambda it: float(it.get(score_key) or 0.0))
        else:

            def _mmr(it: dict) -> float:
                rel = float(it.get(score_key) or 0.0)
                max_sim = max(job_similarity(it, s) for s in selected)
                return lambda_ * rel - (1.0 - lambda_) * max_sim

            best = max(pool, key=_mmr)
        selected.append(best)
        pool.remove(best)

    return selected + pool


# ── First-screen curation ─────────────────────────────────────────────────────


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
) -> dict[str, float]:
    """
    Reciprocal Rank Fusion: combine several ranked ID lists into one score per ID.

    Each list contributes ``weight / (k + rank + 1)`` (rank 0-based), so an item
    near the top of multiple lists wins. ``k=60`` is the canonical constant. This
    is the fusion core of hybrid retrieval — e.g. a dense (embedding) ranking and
    a sparse (lexical / exact-skill) ranking combine into one order, robust to the
    two signals being on different scales.
    """
    ws = weights if weights is not None else [1.0] * len(ranked_lists)
    scores: dict[str, float] = {}
    for lst, weight in zip(ranked_lists, ws, strict=False):
        for rank, item_id in enumerate(lst):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (k + rank + 1)
    return scores


def hybrid_rank(
    items: list[dict],
    *,
    signal_keys: tuple[str, ...],
    id_key: str = "job_id",
    weights: tuple[float, ...] | None = None,
    k: int = 60,
) -> list[dict]:
    """
    Re-order ``items`` by RRF over multiple per-item signals (e.g. the composite
    ``overall_score`` and the lexical ``skills_score``). A signal that is null on
    every item is skipped — so this degrades gracefully when embeddings aren't
    populated. Stamps a min-max-normalised ``fusion_score`` (0-1) on each item so
    it stays on the same scale as MMR's similarity term, and returns items sorted
    by it (desc). Pure; no DB.
    """
    if len(items) <= 1:
        return list(items)

    ranked_lists: list[list[str]] = []
    used_weights: list[float] = []
    wmap = weights if weights is not None else tuple(1.0 for _ in signal_keys)
    for key, weight in zip(signal_keys, wmap, strict=False):
        if all(it.get(key) is None for it in items):
            continue  # signal absent everywhere (e.g. embeddings off) → ignore it
        order = sorted(
            items,
            key=lambda it, _k=key: (it.get(_k) is None, -float(it.get(_k) or 0.0)),
        )
        ranked_lists.append([str(it.get(id_key)) for it in order])
        used_weights.append(weight)

    if not ranked_lists:
        return list(items)

    fused = reciprocal_rank_fusion(ranked_lists, k=k, weights=used_weights)
    hi = max(fused.values())
    lo = min(fused.values())
    span = (hi - lo) or 1.0
    for it in items:
        raw = fused.get(str(it.get(id_key)), lo)
        it["fusion_score"] = round((raw - lo) / span, 6)
    return sorted(items, key=lambda it: it.get("fusion_score", 0.0), reverse=True)


def assemble_first_screen(
    items: list[dict],
    *,
    screen_size: int = 8,
    lambda_: float = 0.72,
    score_key: str = "overall_score",
    fuse_signals: tuple[str, ...] | None = None,
) -> list[dict]:
    """
    Produce the curated opening screen: de-duplicate, then MMR-diversify the
    first `screen_size` cards for variety while keeping strong matches on top.

    When ``fuse_signals`` is given (e.g. ``("overall_score", "skills_score")``),
    items are first hybrid-ranked via RRF over those signals and the normalised
    ``fusion_score`` drives relevance — so a role that's an exceptional direct
    skill match isn't buried just because its composite is a touch lower.

    Returns the full re-ordered list (diversified head + relevance-ordered
    tail), so pagination/`limit` semantics downstream are preserved.
    """
    rank_key = score_key
    if fuse_signals:
        items = hybrid_rank(items, signal_keys=fuse_signals)
        rank_key = "fusion_score"
    deduped = dedupe_jobs(items, score_key=rank_key)
    diversified = mmr_diversify(
        deduped, k=min(screen_size, len(deduped)), lambda_=lambda_, score_key=rank_key
    )
    # #39: guarantee company variety on the opening screen. MMR reduces
    # near-duplicates but doesn't cap a single employer, so a candidate could
    # still see 4+ roles from one company up top. Push a company's 3rd+ role
    # below the fold.
    return cap_company_repeats(diversified, screen_size=screen_size)


def cap_company_repeats(
    items: list[dict], *, screen_size: int, max_per_company: int = 2
) -> list[dict]:
    """
    Ensure the first `screen_size` cards contain at most `max_per_company` roles
    from any one company; overflow is moved just below the screen. Items already
    past the screen keep their order. Stable for items without a company name.
    """
    head: list[dict] = []
    deferred: list[dict] = []
    tail: list[dict] = []
    counts: dict[str, int] = {}
    for it in items:
        if len(head) >= screen_size:
            tail.append(it)
            continue
        company = _norm(it.get("company_name"))
        if company and counts.get(company, 0) >= max_per_company:
            deferred.append(it)
        else:
            head.append(it)
            if company:
                counts[company] = counts.get(company, 0) + 1
    return head + deferred + tail


def attach_tiers(items: list[dict], *, score_key: str = "overall_score") -> list[dict]:
    """Annotate each item in-place with `tier` / `tier_label` from its score."""
    for item in items:
        tier = score_to_tier(float(item.get(score_key) or 0.0))
        item["tier"] = tier.key
        item["tier_label"] = tier.label
    return items
