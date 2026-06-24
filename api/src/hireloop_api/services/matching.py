"""
Matching engine — computes and stores candidate↔job match scores.

Score composition (all weights sum to 1.0):
  skills_score      0.40  — lexical skill overlap (coverage + Jaccard) blended with
                            skills-embedding cosine when embeddings exist
  profile_score     0.30  — title affinity blended with profile↔JD embedding cosine
  experience_score  0.15  — heuristic: candidate years vs. inferred job seniority range
  location_score    0.10  — exact city match / remote bonus / same state fallback
  ctc_score         0.05  — candidate desired CTC within job's CTC band

The skills/profile dimensions degrade gracefully: with no embeddings they run on
the lexical signals alone (never a blind 0.5), so the feed stays relevant even
before the embedding pipeline / OpenRouter key is configured.

Scores are stored in public.match_scores with:
  - overall_score (REAL 0-1)
  - per-dimension scores
  - plain-English explanation for the candidate UI
  - bias_audit JSONB (DPDP Act 2023, R14)

Called by:
  - POST /api/v1/matches/recompute  (admin trigger)
  - Nightly pg_cron job (after embeddings are refreshed)
  - Inline after resume parse + embed (fast path for a single candidate)
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog

from hireloop_api.services.domain_fit import (
    detect_domains,
    domain_fit_multiplier,
    generic_title_overlap_penalty,
)
from hireloop_api.services.job_preferences import (
    REMOTE_PREFERENCE_ONSITE_ONLY,
    normalize_remote_preference,
)
from hireloop_api.services.skills import canonical_skill
from hireloop_api.services.titles import canonical_title_tokens, title_affinity

logger = structlog.get_logger()


def _candidate_open_to_remote(remote_preference: str | None) -> bool:
    """Whether location scoring should treat remote roles as a strong fit."""
    pref = normalize_remote_preference(remote_preference)
    if pref == REMOTE_PREFERENCE_ONSITE_ONLY:
        return False
    return True


# ── Score weights ─────────────────────────────────────────────────────────────
_W_SKILLS = 0.40
_W_PROFILE = 0.30
_W_EXPERIENCE = 0.15
_W_LOCATION = 0.10
_W_CTC = 0.05

# Seniority → approximate years-of-experience midpoint
_SENIORITY_YEARS: dict[str, tuple[int, int]] = {
    "intern": (0, 1),
    "junior": (0, 2),
    "mid": (2, 5),
    "senior": (5, 10),
    "lead": (7, 15),
    "director": (10, 20),
    "vp": (12, 25),
    "c_level": (15, 30),
}


# ── Cosine similarity (fallback if pgvector not used inline) ──────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    """Pure-Python cosine similarity for fallback use."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Heuristic sub-scorers ─────────────────────────────────────────────────────


def _experience_score(candidate_years: float | None, job_seniority: str | None) -> float:
    """
    Returns 0-1 based on how well candidate experience matches job seniority.
    Generous scoring — we never want to completely exclude a candidate.
    """
    if candidate_years is None:
        return 0.5  # neutral when we don't know

    if job_seniority is None or job_seniority not in _SENIORITY_YEARS:
        return 0.5

    lo, hi = _SENIORITY_YEARS[job_seniority]
    mid = (lo + hi) / 2.0

    if lo <= candidate_years <= hi:
        return 1.0
    # Linear decay outside band
    if candidate_years < lo:
        gap = lo - candidate_years
        return max(0.0, 1.0 - gap / max(mid, 1))
    # Over-qualified — small penalty
    gap = candidate_years - hi
    return max(0.3, 1.0 - gap / (hi + 5))


_VALID_LOCATION_SCOPES = ("city", "state", "country", "global")


def resolve_location_scope(scope: str | None, *, open_to_relocation: bool = False) -> str:
    """Normalise the candidate's location scope, falling back to the legacy
    open_to_relocation flag (True → country, False → city) when scope is unset."""
    s = (scope or "").lower().strip()
    if s in _VALID_LOCATION_SCOPES:
        return s
    return "country" if open_to_relocation else "city"


def _location_score(
    candidate_city: str | None,
    candidate_state: str | None,
    job_city: str | None,
    job_state: str | None,
    job_is_remote: bool,
    candidate_open_to_remote: bool,
    candidate_open_to_relocation: bool = False,
    location_scope: str | None = None,
) -> float:
    """Returns 0-1 location compatibility score, gated by the candidate's
    location scope (city | state | country | global)."""
    if job_is_remote:
        return 1.0 if candidate_open_to_remote else 0.6

    if not job_city and not job_state:
        return 0.7  # location unknown — neutral

    scope = resolve_location_scope(location_scope, open_to_relocation=candidate_open_to_relocation)
    c_city = (candidate_city or "").lower().strip()
    j_city = (job_city or "").lower().strip()
    c_state = (candidate_state or "").lower().strip()
    j_state = (job_state or "").lower().strip()

    # Same city is always the best fit.
    if c_city and j_city and c_city == j_city:
        return 1.0
    # Open to anywhere (in India / globally): a far-city role is nearly as good
    # (kept just below 1.0 so a same-city match still edges ahead).
    if scope in ("country", "global"):
        return 0.9
    # Same state ranks well for city/state scope.
    if c_state and j_state and c_state == j_state:
        return 0.7
    # Different city + state and the candidate only wants city/state → penalise.
    return 0.2


def _ctc_score(
    candidate_ctc_min: int | None,
    candidate_ctc_max: int | None,
    job_ctc_min: int | None,
    job_ctc_max: int | None,
) -> float:
    """Returns 0-1 CTC compatibility score (all values in INR per annum)."""
    if not any([candidate_ctc_min, candidate_ctc_max, job_ctc_min, job_ctc_max]):
        return 0.5  # neutral when no data

    c_min = candidate_ctc_min or 0
    c_max = candidate_ctc_max or (c_min * 2 if c_min else 0)
    j_min = job_ctc_min or 0
    j_max = job_ctc_max or (j_min * 3 if j_min else 0)

    if j_max == 0 and j_min == 0:
        return 0.5

    # Check overlap between [c_min, c_max] and [j_min, j_max]
    overlap_lo = max(c_min, j_min)
    overlap_hi = min(c_max, j_max)

    if overlap_hi >= overlap_lo:
        # Full overlap
        c_range = max(c_max - c_min, 1)
        overlap = overlap_hi - overlap_lo
        return min(1.0, 0.5 + 0.5 * (overlap / c_range))

    # No overlap
    if c_min > j_max:
        # Candidate wants more than job pays
        gap_pct = (c_min - j_max) / max(j_max, 1)
        return max(0.0, 1.0 - gap_pct)
    # Job pays more than candidate needs (overqualified CTC-wise)
    return 0.8


def _normalize_skill(s: str) -> str:
    """Canonical skill token: lowercase, separators stripped ('Node.js' ==
    'nodejs'), and known aliases collapsed ('reactjs' == 'react', 'k8s' ==
    'kubernetes') via the shared skills service — so alias variants never count
    as a miss in the overlap score."""
    return canonical_skill(s)


def _skill_overlap_score(
    candidate_skills: list[str] | None,
    job_skills: list[str] | None,
) -> float | None:
    """
    Lexical skill fit, 0-1, or None when it can't be assessed (either side has no
    skills listed). This is the signal that was missing — it lets the matcher
    reward a candidate who actually has the job's required skills even when no
    embeddings exist, and tank a candidate who has none of them.

    Combines coverage (share of the job's required skills the candidate has —
    the relevance-critical part) with Jaccard (penalises wildly mismatched sets).
    """
    cand = {n for s in (candidate_skills or []) if (n := _normalize_skill(s))}
    job = {n for s in (job_skills or []) if (n := _normalize_skill(s))}
    if not cand or not job:
        return None
    overlap = cand & job
    coverage = len(overlap) / len(job)
    jaccard = len(overlap) / len(cand | job)
    # Coverage ("how many of the role's required skills does the candidate have")
    # is what a recruiter actually reads as fit, so it dominates. Jaccard is kept
    # as a small guard so a candidate with a wildly broader/narrower set than the
    # role doesn't read as a perfect match on coverage alone.
    return round(min(1.0, 0.85 * coverage + 0.15 * jaccard), 4)


def _title_tokens(title: str | None) -> frozenset[str]:
    # Delegates to the shared taxonomy (#35) so the matcher, parser, and
    # ingester all agree on what a title "means" — synonyms ("developer" ==
    # "engineer") and Indian-market shorthand ("SDE", "PM") included.
    return canonical_title_tokens(title)


def _title_affinity(candidate_title: str | None, job_title: str | None) -> float | None:
    """0-1 canonical-token overlap between the candidate's role and the job
    title, or None when either is unknown. Catches role mismatch (e.g. a
    'sales' title vs a 'backend engineer' job) that pure embeddings can blur."""
    return title_affinity(candidate_title, job_title)


def _best_title_affinity(job_title: str | None, candidate_titles: list[str]) -> float | None:
    """
    Best title affinity over the candidate's current role AND their career-path
    target titles. Returns the max, so a job matching ANY of where they are or
    where they want to go scores well — this is what makes the feed follow the
    user's intended trajectory, not just their present job. None if nothing to
    compare.
    """
    scores = [a for t in candidate_titles if (a := _title_affinity(t, job_title)) is not None]
    return max(scores) if scores else None


# ── Embedding calibration (HIR-55) ────────────────────────────────────────────
# Raw text-embedding-3-small cosine is squeezed into a narrow band — measured on
# our own corpus: profile-to-JD ~0.29-0.57 (avg 0.42), skills ~0.08-0.79. Used
# raw, a "perfect" match reads ~0.5, so a cosine-weighted blend would *drag down*
# the strong lexical/title scores once embeddings populate. So we (1) calibrate
# the observed band onto 0-1, then (2) apply embeddings as an ADDITIVE LIFT on top
# of the lexical/title backbone: semantics can only raise a score (surfacing
# kinship exact tokens miss), never lower a solid lexical fit. This is what lets
# the ~600-job embedding backfill turn on without regressing the feed.
_PROFILE_COS_LO, _PROFILE_COS_HI = 0.25, 0.60
_SKILLS_COS_LO, _SKILLS_COS_HI = 0.10, 0.70
_PROFILE_LIFT = 0.50  # max share of remaining headroom semantics may add
_SKILLS_LIFT = 0.40


def _calibrate_cosine(sim: float, lo: float, hi: float) -> float:
    """Map an observed cosine band onto 0-1 (clamped)."""
    return min(1.0, max(0.0, (sim - lo) / (hi - lo)))


def _semantic_lift(base: float, sim: float, lo: float, hi: float, alpha: float) -> float:
    """Raise `base` toward 1.0 by a calibrated-cosine fraction of its headroom —
    monotonic and never below `base`, so embeddings can't regress a strong fit."""
    return round(base + (1.0 - base) * _calibrate_cosine(sim, lo, hi) * alpha, 4)


def _blend_skills(embedding_sim: float | None, lexical: float | None) -> float:
    """Resolve the skills dimension from whatever signals exist (never a blind 0.5).
    Lexical coverage is the backbone; calibrated embedding cosine lifts it."""
    if embedding_sim is not None and lexical is not None:
        return _semantic_lift(lexical, embedding_sim, _SKILLS_COS_LO, _SKILLS_COS_HI, _SKILLS_LIFT)
    if lexical is not None:
        return lexical
    if embedding_sim is not None:
        return round(_calibrate_cosine(embedding_sim, _SKILLS_COS_LO, _SKILLS_COS_HI), 4)
    return 0.5  # genuinely no skill data on either side → neutral


def _role_fit_gate(
    title_aff: float | None,
    lexical_skills: float | None,
    blended_skills: float,
) -> float:
    """Multiplier (0.4-1.0) that pulls down matches with weak role fit.

    Uses lexical skill overlap (not embedding-lifted skills) so semantic cosine
    can't prop up a wrong-function match. A real fit (role_fit >= 0.6) is left
    untouched; a weak one scales toward an honest score (down to 0.4x)."""
    skill_signal = lexical_skills if lexical_skills is not None else blended_skills * 0.5
    role_fit = max(title_aff or 0.0, skill_signal)
    return min(1.0, 0.40 + role_fit)


def _blend_profile(embedding_sim: float | None, title_aff: float | None) -> float:
    """Resolve the profile dimension; title affinity is the backbone, calibrated
    embedding cosine lifts it. Falls back gracefully, never a blind 0.5."""
    if embedding_sim is not None and title_aff is not None:
        return _semantic_lift(
            title_aff, embedding_sim, _PROFILE_COS_LO, _PROFILE_COS_HI, _PROFILE_LIFT
        )
    if title_aff is not None:
        return title_aff
    if embedding_sim is not None:
        return round(_calibrate_cosine(embedding_sim, _PROFILE_COS_LO, _PROFILE_COS_HI), 4)
    return 0.5


def _build_explanation(
    overall: float,
    skills: float,
    experience: float,
    location: float,
    ctc: float,
    job_title: str,
    company_name: str | None,
    candidate_name: str | None,
) -> str:
    """Generate a plain-English explanation for the candidate."""
    pct = round(overall * 100)
    company = company_name or "this company"
    role = f"{job_title} at {company}"

    # Lead sentence
    if pct >= 80:
        lead = f"Strong match ({pct}%) — you're a great fit for {role}."
    elif pct >= 60:
        lead = f"Good match ({pct}%) — you align well with {role}."
    elif pct >= 40:
        lead = f"Moderate match ({pct}%) — there are some gaps for {role}."
    else:
        lead = f"Weak match ({pct}%) — significant gaps exist for {role}."

    # Strength / gap callouts
    notes: list[str] = []
    if skills >= 0.75:
        notes.append("Your skills align closely with what's needed.")
    elif skills < 0.40:
        notes.append("Skills gap detected — you may need to upskill for this role.")

    if experience < 0.50:
        notes.append("Experience level may not match the seniority expected.")

    if location < 0.30:
        notes.append("Location mismatch — relocation or remote approval needed.")

    if ctc < 0.40:
        notes.append("Salary expectation gap — discuss compensation before applying.")

    explanation = lead
    if notes:
        explanation += " " + " ".join(notes)
    return explanation


def _bias_audit() -> dict[str, Any]:
    """DPDP bias-audit metadata stored alongside every score."""
    return {
        "computed_at": datetime.now(UTC).isoformat(),
        "model": "heuristic+cosine_v1",
        "features_used": [
            "skills_embedding",
            "profile_embedding",
            "experience_years",
            "location",
            "ctc",
        ],
        "features_excluded": ["gender", "age", "religion", "caste", "photo"],
        "dpdp_note": "No protected-characteristic data used in scoring (DPDP Act 2023).",
    }


def _assemble_score(
    cand_row: Mapping[str, Any],
    job_row: Mapping[str, Any],
    embed_skills_sim: float | None,
    embed_profile_sim: float | None,
) -> dict[str, Any]:
    """Pure scoring core shared by ``score_pair`` and the batched ``score_candidate``
    so both paths produce identical scores. Given a candidate row, a job row, and
    the two already-computed embedding cosines, returns the overall + per-dimension
    scores + the candidate-facing explanation. No DB, no I/O."""
    lexical_skills = _skill_overlap_score(
        list(cand_row["skills"] or []),
        list(job_row["skills_required"] or []),
    )
    # Career-path aware: a job aligned with the candidate's current role OR any of
    # their career-path target titles boosts the profile dimension.
    candidate_titles = [
        t for t in [cand_row["current_title"], *(cand_row["target_titles"] or [])] if t
    ]
    title_aff = _best_title_affinity(job_row["title"], candidate_titles)

    skills_sim = _blend_skills(embed_skills_sim, lexical_skills)
    profile_sim = _blend_profile(embed_profile_sim, title_aff)

    exp_score = _experience_score(cand_row["years_experience"], job_row["seniority"])
    loc_score = _location_score(
        candidate_city=cand_row["location_city"],
        candidate_state=cand_row["location_state"],
        job_city=job_row["location_city"],
        job_state=job_row["location_state"],
        job_is_remote=job_row["is_remote"] or False,
        candidate_open_to_remote=_candidate_open_to_remote(cand_row.get("remote_preference")),
        candidate_open_to_relocation=bool(cand_row.get("open_to_relocation")),
        location_scope=cand_row.get("location_scope"),
    )
    ctc_score = _ctc_score(
        candidate_ctc_min=cand_row["expected_ctc_min"],
        candidate_ctc_max=cand_row["expected_ctc_max"],
        job_ctc_min=job_row["ctc_min"],
        job_ctc_max=job_row["ctc_max"],
    )

    # Skills, profile and location are always assessable; experience/CTC only count
    # when the JOB states them (renormalise over the rest otherwise).
    dims: list[tuple[float, float]] = [
        (_W_SKILLS, skills_sim),
        (_W_PROFILE, profile_sim),
        (_W_LOCATION, loc_score),
    ]
    if job_row["seniority"]:
        dims.append((_W_EXPERIENCE, exp_score))
    if job_row["ctc_min"] is not None or job_row["ctc_max"] is not None:
        dims.append((_W_CTC, ctc_score))
    weight_sum = sum(w for w, _ in dims) or 1.0
    overall = sum(w * s for w, s in dims) / weight_sum
    # Gate by role fit (title + lexical skills) so neutral context can't float a
    # wrong-function match; then penalise cross-industry pairs (hotel sales vs
    # SaaS GTM) and generic-only title overlap ("sales" alone).
    overall *= _role_fit_gate(title_aff, lexical_skills, skills_sim)
    cand_domains = detect_domains(
        title=cand_row.get("current_title"),
        company=cand_row.get("current_company"),
        skills=list(cand_row.get("skills") or []),
        extra=cand_row.get("headline") or cand_row.get("summary"),
    )
    job_domains = detect_domains(
        title=job_row.get("title"),
        company=job_row.get("company_name"),
        skills=list(job_row.get("skills_required") or []),
        extra=job_row.get("description"),
    )
    overall *= domain_fit_multiplier(cand_domains, job_domains)
    overall *= generic_title_overlap_penalty(
        cand_row.get("current_title"),
        job_row.get("title"),
    )
    overall = round(min(1.0, max(0.0, overall)), 4)

    explanation = _build_explanation(
        overall=overall,
        skills=skills_sim,
        experience=exp_score,
        location=loc_score,
        ctc=ctc_score,
        job_title=job_row["title"],
        company_name=job_row["company_name"],
        candidate_name=cand_row["full_name"],
    )
    return {
        "overall": overall,
        "skills_sim": skills_sim,
        "exp_score": exp_score,
        "loc_score": loc_score,
        "ctc_score": ctc_score,
        "explanation": explanation,
    }


# ── Main scorer ───────────────────────────────────────────────────────────────


class MatchingEngine:
    """
    Computes and persists match_scores for candidate↔job pairs.

    Usage:
        engine = MatchingEngine(db)
        await engine.score_candidate(candidate_id)          # score all active jobs
        await engine.score_job(job_id)                      # score all candidates
        await engine.score_pair(candidate_id, job_id)       # single pair
        await engine.recompute_all()                        # full nightly recompute
    """

    def __init__(self, db: asyncpg.Connection) -> None:
        self._db = db
        # Candidate rows are identical across every job in a score_candidate pass.
        # Cache per engine instance so we fetch the (multi-join) candidate once
        # instead of once per job — the dominant cost of scoring a fresh feed.
        self._cand_cache: dict[str, asyncpg.Record | None] = {}

    async def _candidate_row(self, candidate_id: str) -> asyncpg.Record | None:
        """Fetch the candidate + embeddings + target titles, cached per engine."""
        if candidate_id in self._cand_cache:
            return self._cand_cache[candidate_id]
        row = await self._db.fetchrow(
            """
            SELECT
                c.id,
                u.full_name,
                c.current_title,
                c.current_company,
                c.headline,
                c.summary,
                c.years_experience,
                c.skills,
                c.expected_ctc_min,
                c.expected_ctc_max,
                c.location_city,
                c.location_state,
                c.remote_preference,
                c.open_to_relocation,
                c.location_scope,
                ce.profile_embedding,
                ce.skills_embedding,
                ce.resume_embedding,
                (
                    SELECT cp.target_titles
                    FROM public.career_paths cp
                    WHERE cp.candidate_id = c.id AND cp.deleted_at IS NULL
                    ORDER BY cp.created_at DESC
                    LIMIT 1
                ) AS target_titles
            FROM public.candidates c
            JOIN public.users u ON u.id = c.user_id AND u.deleted_at IS NULL
            LEFT JOIN public.candidate_embeddings ce ON ce.candidate_id = c.id
            WHERE c.id = $1::uuid AND c.deleted_at IS NULL
            """,
            candidate_id,
        )
        self._cand_cache[candidate_id] = row
        return row

    async def score_pair(
        self, candidate_id: str, job_id: str, *, notify: bool = True
    ) -> float | None:
        """
        Compute match score for a single candidate↔job pair.
        Returns overall_score (0-1) or None on failure.
        Uses pgvector cosine similarity for embedding dimensions.

        ``notify=False`` for bulk scoring (whole-feed / nightly recompute) so a
        fresh candidate isn't blasted with a notification per job — and we skip
        the per-pair candidate lookup the notifier would do (a latency win on the
        first-feed scoring path).
        """
        cand_row = await self._candidate_row(candidate_id)

        job_row = await self._db.fetchrow(
            """
            SELECT
                j.id,
                j.title,
                j.description,
                j.seniority,
                j.skills_required,
                j.is_remote,
                j.location_city,
                j.location_state,
                j.ctc_min,
                j.ctc_max,
                co.name AS company_name,
                je.jd_embedding,
                je.title_embedding,
                je.skills_embedding
            FROM public.jobs j
            LEFT JOIN public.job_embeddings je ON je.job_id = j.id
            LEFT JOIN public.companies co ON co.id = j.company_id
            WHERE j.id = $1::uuid
              AND j.country_code = 'IN'
              AND j.deleted_at IS NULL
            """,
            job_id,
        )
        # NOTE: scoring is deliberately independent of is_active. Feed visibility
        # is enforced by the feed queries and the bulk score_candidate selector
        # (both filter is_active themselves); requiring it here only blocked
        # recruiter roles — whose mirror job is is_active=FALSE until published —
        # from ever being scored, so every Nitya shortlist came back empty.

        if not cand_row or not job_row:
            return None

        # ── Skills & profile scores ───────────────────────────────────────────
        # Lexical signals always work (no embeddings/key needed); embedding cosine
        # is blended in when available. Critically we NEVER fall back to a blind
        # 0.5 when we actually have skills/titles to compare — that flat default
        # was what made every job score ~0.5 and the ranking look random.
        embed_skills_sim: float | None = None
        embed_profile_sim: float | None = None

        if cand_row["skills_embedding"] and job_row["skills_embedding"]:
            row = await self._db.fetchrow(
                "SELECT 1 - (ce.skills_embedding <=> je.skills_embedding) AS sim "
                "FROM public.candidate_embeddings ce, public.job_embeddings je "
                "WHERE ce.candidate_id = $1::uuid AND je.job_id = $2::uuid",
                candidate_id,
                job_id,
            )
            if row and row["sim"] is not None:
                embed_skills_sim = max(0.0, float(row["sim"]))

        if cand_row["profile_embedding"] and job_row["jd_embedding"]:
            row = await self._db.fetchrow(
                "SELECT 1 - (ce.profile_embedding <=> je.jd_embedding) AS sim "
                "FROM public.candidate_embeddings ce, public.job_embeddings je "
                "WHERE ce.candidate_id = $1::uuid AND je.job_id = $2::uuid",
                candidate_id,
                job_id,
            )
            if row and row["sim"] is not None:
                embed_profile_sim = max(0.0, float(row["sim"]))

        # Shared pure scoring core (identical math to the batched score_candidate).
        result = _assemble_score(cand_row, job_row, embed_skills_sim, embed_profile_sim)
        overall = result["overall"]
        skills_sim = result["skills_sim"]
        exp_score = result["exp_score"]
        loc_score = result["loc_score"]
        ctc_score = result["ctc_score"]
        explanation = result["explanation"]

        # ── Persist ───────────────────────────────────────────────────────────
        prior = await self._db.fetchrow(
            """
            SELECT overall_score FROM public.match_scores
            WHERE candidate_id = $1::uuid AND job_id = $2::uuid
            """,
            candidate_id,
            job_id,
        )
        prior_score = float(prior["overall_score"]) if prior else None

        bias_audit = _bias_audit()

        await self._db.execute(
            """
            INSERT INTO public.match_scores
                (id, candidate_id, job_id,
                 overall_score, skills_score, experience_score, location_score, ctc_score,
                 explanation, bias_audit, computed_at)
            VALUES
                ($1, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10::jsonb, NOW())
            ON CONFLICT (candidate_id, job_id) DO UPDATE SET
                overall_score    = EXCLUDED.overall_score,
                skills_score     = EXCLUDED.skills_score,
                experience_score = EXCLUDED.experience_score,
                location_score   = EXCLUDED.location_score,
                ctc_score        = EXCLUDED.ctc_score,
                explanation      = EXCLUDED.explanation,
                bias_audit       = EXCLUDED.bias_audit,
                computed_at      = NOW()
            """,
            uuid.uuid4(),
            candidate_id,
            job_id,
            overall,
            round(skills_sim, 4),
            round(exp_score, 4),
            round(loc_score, 4),
            round(ctc_score, 4),
            explanation,
            json.dumps(bias_audit),
        )

        # P19: notify on new strong match (first time or material score bump)
        should_notify = prior_score is None or (overall - prior_score) >= 0.08
        if notify and should_notify and overall >= 0.65:
            try:
                from hireloop_api.config import get_settings
                from hireloop_api.services.notifications import notify_job_match

                settings = get_settings()
                await notify_job_match(
                    self._db,
                    settings,
                    candidate_id=candidate_id,
                    job_id=job_id,
                    overall_score=overall,
                    job_title=job_row["title"],
                    company_name=job_row["company_name"],
                )
            except Exception as exc:
                logger.warning("match_notify_failed", error=str(exc))

        return overall

    async def score_candidate(self, candidate_id: str, limit: int = 500) -> int:
        """
        Score all active jobs for a single candidate. Returns count written.

        Batched for speed: one query fetches every job + its embeddings AND the
        skills/profile cosines against this candidate (computed in pgvector), then
        the shared pure scorer runs in Python and all rows are upserted in a single
        executemany — versus the old ~5 round-trips x N jobs. Scores are identical
        to score_pair (same _assemble_score). No per-pair notifications here (this
        path always ran with notify=False).
        """
        cand_row = await self._candidate_row(candidate_id)
        if cand_row is None:
            return 0

        jobs = await self._db.fetch(
            """
            SELECT j.id, j.title, j.description, j.seniority, j.skills_required,
                   j.is_remote, j.location_city, j.location_state, j.ctc_min,
                   j.ctc_max, co.name AS company_name,
                   CASE
                     WHEN ce.skills_embedding IS NOT NULL AND je.skills_embedding IS NOT NULL
                     THEN 1 - (ce.skills_embedding <=> je.skills_embedding)
                   END AS skills_sim,
                   CASE
                     WHEN ce.profile_embedding IS NOT NULL AND je.jd_embedding IS NOT NULL
                     THEN 1 - (ce.profile_embedding <=> je.jd_embedding)
                   END AS profile_sim
            FROM public.jobs j
            LEFT JOIN public.job_embeddings je ON je.job_id = j.id
            LEFT JOIN public.companies co ON co.id = j.company_id
            LEFT JOIN public.candidate_embeddings ce ON ce.candidate_id = $1::uuid
            WHERE j.is_active = TRUE
              AND j.country_code = 'IN'
              AND j.deleted_at IS NULL
              AND j.expires_at > NOW()
            ORDER BY j.scraped_at DESC
            LIMIT $2
            """,
            candidate_id,
            limit,
        )
        if not jobs:
            logger.info("score_candidate_done", candidate_id=candidate_id, scored=0)
            return 0

        bias_audit = json.dumps(_bias_audit())
        records: list[tuple] = []
        for j in jobs:
            es = max(0.0, float(j["skills_sim"])) if j["skills_sim"] is not None else None
            ep = max(0.0, float(j["profile_sim"])) if j["profile_sim"] is not None else None
            r = _assemble_score(cand_row, j, es, ep)
            records.append(
                (
                    uuid.uuid4(),
                    candidate_id,
                    str(j["id"]),
                    r["overall"],
                    round(r["skills_sim"], 4),
                    round(r["exp_score"], 4),
                    round(r["loc_score"], 4),
                    round(r["ctc_score"], 4),
                    r["explanation"],
                    bias_audit,
                )
            )

        await self._db.executemany(
            """
            INSERT INTO public.match_scores
                (id, candidate_id, job_id,
                 overall_score, skills_score, experience_score, location_score, ctc_score,
                 explanation, bias_audit, computed_at)
            VALUES
                ($1, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10::jsonb, NOW())
            ON CONFLICT (candidate_id, job_id) DO UPDATE SET
                overall_score    = EXCLUDED.overall_score,
                skills_score     = EXCLUDED.skills_score,
                experience_score = EXCLUDED.experience_score,
                location_score   = EXCLUDED.location_score,
                ctc_score        = EXCLUDED.ctc_score,
                explanation      = EXCLUDED.explanation,
                bias_audit       = EXCLUDED.bias_audit,
                computed_at      = NOW()
            """,
            records,
        )

        logger.info("score_candidate_done", candidate_id=candidate_id, scored=len(records))
        return len(records)

    async def score_job(self, job_id: str, limit: int = 500, *, notify: bool = True) -> int:
        """
        Score all active candidates for a single newly-ingested job.
        Returns count of scores written.
        """
        rows = await self._db.fetch(
            """
            SELECT c.id FROM public.candidates c
            WHERE c.deleted_at IS NULL
            ORDER BY c.updated_at DESC
            LIMIT $1
            """,
            limit,
        )

        count = 0
        for r in rows:
            result = await self.score_pair(str(r["id"]), job_id, notify=notify)
            if result is not None:
                count += 1

        logger.info("score_job_done", job_id=job_id, scored=count)
        return count

    async def recompute_all(self, candidate_limit: int = 200, job_limit: int = 500) -> dict:
        """
        Full nightly recompute: score the most-active candidates against all live jobs.
        Called by pg_cron (see migration 000900).
        """
        start = datetime.now(UTC)

        cands = await self._db.fetch(
            """
            SELECT c.id FROM public.candidates c
            WHERE c.deleted_at IS NULL
            ORDER BY c.updated_at DESC
            LIMIT $1
            """,
            candidate_limit,
        )

        total_pairs = 0
        for r in cands:
            scored = await self.score_candidate(str(r["id"]))
            total_pairs += scored

        elapsed = (datetime.now(UTC) - start).total_seconds()
        stats = {
            "candidates_processed": len(cands),
            "total_pairs_scored": total_pairs,
            "elapsed_seconds": round(elapsed, 1),
        }
        logger.info("recompute_all_done", **stats)
        return stats


async def rank_candidates_for_job(
    db: asyncpg.Connection,
    *,
    job_id: uuid.UUID | str,
    limit: int = 25,
    openrouter_api_key: str = "",  # reserved for per-criterion LLM scoring (P17+)
) -> list[dict]:
    """
    Return top candidates for a job from precomputed match_scores (P17 recruiter search).
    """
    _ = openrouter_api_key
    rows = await db.fetch(
        """
        SELECT
          ms.candidate_id::text,
          ms.overall_score,
          ms.skills_score,
          ms.experience_score,
          ms.location_score,
          ms.ctc_score,
          ms.explanation,
          c.headline,
          c.current_title,
          c.years_experience,
          c.location_city
        FROM public.match_scores ms
        JOIN public.candidates c ON c.id = ms.candidate_id AND c.deleted_at IS NULL
        WHERE ms.job_id = $1::uuid
        ORDER BY ms.overall_score DESC
        LIMIT $2
        """,
        str(job_id),
        limit,
    )
    return [
        {
            "candidate_id": r["candidate_id"],
            "overall_score": float(r["overall_score"]),
            "scores": {
                "skills": r["skills_score"],
                "experience": r["experience_score"],
                "location": r["location_score"],
                "ctc": r["ctc_score"],
            },
            "explanation": r["explanation"],
            "headline": r["headline"],
            "current_title": r["current_title"],
            "years_experience": r["years_experience"],
            "location_city": r["location_city"],
        }
        for r in rows
    ]


async def run_job_scoring(settings: Any, job_id: str, limit: int = 500) -> None:  # noqa: ANN401
    """
    Fire-and-forget: score a freshly published/ingested job against active
    candidates so it surfaces in their match feed immediately — not only after
    the nightly recompute. Uses lexical signals when embeddings aren't ready yet
    (score_pair never returns a blind 0.5). Runs on its own pooled connection.
    Never raises.
    """
    from hireloop_api.deps import get_db_pool

    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as db:
            engine = MatchingEngine(db)
            await engine.score_job(job_id, limit=limit)
    except Exception as exc:  # background task — never propagate
        logger.warning("job_scoring_bg_failed", job_id=job_id, error=str(exc))
