# 05 — MatchingEngine

Exact implementation as of `api/src/hireloop_api/services/matching.py` and related modules. All weights/floors cited are **hardcoded constants** unless noted.

---

## Entry points

| Method | Role |
|---|---|
| `MatchingEngine.score_pair` | Single candidate↔job; may notify |
| `MatchingEngine.score_candidate` | Batch jobs for one candidate |
| `MatchingEngine.score_job` | Batch candidates for one job (recruiter search) |
| `_assemble_score` | Pure assembler (no I/O) — shared by pair + batch |

Related: `match_quality.py`, `ranking.py`, `domain_fit.py`, `fit_dimensions.py`, `behavior_ranking.py`, `job_recall_pipeline.py`.

---

## Overall score formula (actual code)

Weights (`matching.py` lines 72–76):

```python
_W_SKILLS = 0.40
_W_PROFILE = 0.30
_W_EXPERIENCE = 0.15
_W_LOCATION = 0.10
_W_CTC = 0.05
```

`_assemble_score` (`matching.py:571-689`):

```text
lexical_skills = _skill_overlap_score(cand.skills, job.skills_required)
title_aff      = best affinity over intent/career-path titles
skills_sim     = _blend_skills(embed_skills_sim, lexical_skills, ...)
profile_sim    = _blend_profile(embed_profile_sim, title_aff)
exp_score      = _experience_score(years, seniority)
loc_score      = _location_score(...)
ctc_score      = _ctc_score(...)

dims = [(0.40, skills_sim), (0.30, profile_sim), (0.10, loc_score)]
+ (0.15, exp_score)  if job.seniority is set
+ (0.05, ctc_score)  if job.ctc_min or job.ctc_max is set

overall = Σ(wᵢ × sᵢ) / Σ(wᵢ)     # renormalize when exp/CTC omitted

overall *= _role_fit_gate(title_aff, lexical_skills, skills_sim)
overall *= domain_fit_multiplier(cand_domains, job_domains)
overall *= generic_title_overlap_penalty(cand_title, job_title)
overall *= _seniority_fit_gate(cand_rank, job_seniority)
overall = clamp(overall, 0, 1) rounded to 4 decimals
```

`culture_score` / `career_alignment_score` / `fit_recommendation` from `fit_dimensions.enrich_score_result` are **metadata only** — they do **not** enter `overall`.

---

## Skills lexical scoring

`_skill_overlap_score` (`matching.py:276-300`):

```text
coverage = |cand ∩ job| / |job|
jaccard  = |cand ∩ job| / |cand ∪ job|
lexical  = min(1, 0.85 × coverage + 0.15 × jaccard)
```

Skills normalized via `canonical_skill`. Returns `None` if either side empty. Mirrored in `match_quality._skill_overlap_score`.

---

## Embedding contribution (semantic lift)

Constants in `matching.py` (~HIR-55 block):

| Constant | Value | Role |
|---|---|---|
| `_PROFILE_COS_LO` / `_HI` | 0.25 / 0.60 | calibrate profile↔JD cosine |
| `_SKILLS_COS_LO` / `_HI` | 0.10 / 0.70 | calibrate skills cosine |
| `_PROFILE_LIFT` | **0.50** | max headroom share for profile |
| `_SKILLS_LIFT` | **0.40** | max headroom share for skills |

```text
calibrated = clamp((sim − lo) / (hi − lo), 0, 1)
lifted     = base + (1 − base) × calibrated × alpha   # never below base
```

- Skills: `_blend_skills` — lexical backbone + embedding lift.
- Profile: `_blend_profile` — title affinity backbone + embedding lift.
- Cosine from pgvector: `1 - (a <=> b)` in `score_pair` / `score_candidate` SQL.

---

## Gates / multipliers

| Gate | Function | Behavior |
|---|---|---|
| Role fit | `_role_fit_gate` | `min(1, 0.40 + max(title_aff, lexical_or_blended×0.5))` → **0.4–1.0** |
| Domain | `domain_fit.domain_fit_multiplier` | hard mismatches → **~0.12–0.2**; else **1.0**; unknown job domains → **1.0** |
| Generic title | `generic_title_overlap_penalty` | only-generic overlap → **0.35** (unless subset/equal) |
| Seniority | `_seniority_fit_gate` | gap≤1 → 1.0; gap2 → 0.9; gap3 → 0.6; else → **0.4** |

Seniority bands: `_SENIORITY_YEARS`, `_SENIORITY_RANK`; title inference `_infer_seniority_from_title`.

---

## Weight renormalization

When job lacks `seniority` and/or CTC band, those dimensions are **omitted** from `dims` and overall is divided by the remaining weight sum (`matching.py:624-636`). Skills + profile + location always contribute.

---

## Persist and feed floors — `match_quality.py`

| Constant | Value | Use |
|---|---|---|
| `MIN_PERSIST_SCORE` | **0.35** | default write floor to `match_scores` |
| `PATH_ALIGNED_MIN_PERSIST` | **0.18** | if title_aff ≥ `PATH_ALIGNED_MIN_AFFINITY` (**0.25**) |
| `DEFAULT_FEED_MIN_SCORE` | **0.38** | API/feed default |
| `MIN_TITLE_AFFINITY_POOL` | **0.10** | persona pool entry |
| `MIN_DOMAIN_MULTIPLIER_POOL` | **0.25** | pool + persist hard stop |
| role_signal persist | **≥ 0.15** | `max(title_aff, lexical)` in `should_persist_match` |

Weak matches are `DELETE`d / skipped in `score_pair` / `score_candidate`.

---

## RRF fusion — `ranking.py`

`reciprocal_rank_fusion` (`ranking.py:288-308`):

```text
score(id) += weight / (k + rank + 1)   # rank 0-based
k = 60  (canonical default)
```

`hybrid_rank` builds ranked ID lists from signal keys (e.g. `overall_score`, `skills_score`), calls RRF with `k=60`, stamps min-max `fusion_score`.

**Feed path:** `matches.py` (~667–685) — `offset==0` and `limit≤20` → `assemble_first_screen(..., fuse_signals=(ranking_or_overall, skills_score))`, `screen_size=min(limit,10)`.

**Aarya recall:** `job_recall_pipeline.union_and_rank_recall_pools` — RRF `k=60` over pools, then `assemble_first_screen`.

RRF/MMR **reorder presentation**; they do **not** redefine stored `overall_score`.

---

## MMR and company cap

| Mechanism | Constants | Function |
|---|---|---|
| MMR | `λ=0.72` default | `mmr_diversify` — `λ×rel − (1−λ)×max_sim` (`ranking.py:247-282`) |
| Company cap | `max_per_company=2` | `cap_company_repeats` (`ranking.py:391-414`) |
| Job similarity | company 0.45, title Jac 0.30, sen 0.15, city 0.10 | `job_similarity` |
| Dedupe threshold | **0.85** | `dedupe_jobs` |
| Saved-job boost | `max_boost=0.12` | `boost_by_saved` (presentation) |

`assemble_first_screen` (`ranking.py:360+`): dedupe → optional hybrid RRF → MMR head → company cap.

---

## Outcome validation & learning-loop plug-in

### Which constants have been validated against real outcomes?

**None in code.** Evidence:

- Embedding calibration bands are labeled corpus/heuristic comments in `matching.py` — not live outcome regression.
- `match_feedback` table + insert paths capture impressions/saves/intros — **not consumed by `_assemble_score`**.
- `behavior_ranking.py` applies **post-score** heuristic multipliers on Aarya search (`save +0.08×n`, `apply_start +0.12×n`, dismiss −0.15×n, clamp 0.5–1.25) — not weight learning.
- `boost_by_saved` is presentation-only.
- Notify threshold `overall ≥ 0.65` and Δ≥0.08 in pair scoring is a product heuristic, not measured hire precision.
- No offline eval harness tying weights to hire/reply rates found in `api/`.

### Where would accept/skip/save signals plug in?

Natural insertion points **without** rewriting the formula first:

1. **`match_feedback` / `candidate_job_impressions` / `application_outcomes`** — already persisted; train a re-ranker that adjusts `assemble_first_screen` `score_key` or `fuse_signals` weights.
2. **`behavior_ranking.py`** — extend multipliers (already the soft personalization layer on search).
3. **`boost_by_saved`** — generalize from saves to accept/skip.
4. **`_assemble_score` dims** — only after labeled outcomes; would need weight config (today all hardcoded).
5. **Persist floor** — per-user calibration of `MIN_PERSIST_SCORE` based on skip rates (risky for inventory).

Safest MVP learning loop: keep `_assemble_score` fixed; learn a **second-stage ranker** over `(overall, skills, title_aff, behavior_features)` used only in `assemble_first_screen` / `job_search`.

---

## Discrepancies

1. Internal docs that claim “LLM scores matches” overstate — LLMs produce rationale/kit content; **score is heuristic + embeddings**.
2. Fit-dimension culture/career scores look like they contribute to ranking but are metadata via `enrich_score_result`.

---

## Unverified — needs human confirmation

1. Whether any offline notebook/spreadsheet outside the repo validated floors (0.35/0.38) against recruiter judgment.
2. Whether production `match_feedback` volume is enough for a learning experiment.
