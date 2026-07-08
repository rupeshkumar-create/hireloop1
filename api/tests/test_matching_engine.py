"""
Tests for the candidate↔job matching engine (P10).

Covers the pure sub-scorers (cosine, experience, location, CTC), the
explanation thresholds, the weight invariant, and a full score_pair pass against
a fake connection — no DB, embeddings API, or Apify token needed.
"""

from __future__ import annotations

import math

from hireloop_api.services.matching import (
    _W_CTC,
    _W_EXPERIENCE,
    _W_LOCATION,
    _W_PROFILE,
    _W_SKILLS,
    MatchingEngine,
    _best_title_affinity,
    _blend_profile,
    _blend_skills,
    _build_explanation,
    _cosine,
    _ctc_score,
    _experience_score,
    _location_score,
    _role_fit_gate,
    _skill_overlap_score,
    _title_affinity,
)

# ── weight invariant ───────────────────────────────────────────────────────────


def test_score_weights_sum_to_one() -> None:
    total = _W_SKILLS + _W_PROFILE + _W_EXPERIENCE + _W_LOCATION + _W_CTC
    assert math.isclose(total, 1.0, abs_tol=1e-9)


# ── cosine ─────────────────────────────────────────────────────────────────────


def test_cosine_identical_is_one() -> None:
    assert math.isclose(_cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0, abs_tol=1e-9)


def test_cosine_orthogonal_is_zero() -> None:
    assert math.isclose(_cosine([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_cosine_handles_degenerate_input() -> None:
    assert _cosine([], [1.0]) == 0.0
    assert _cosine([1.0, 2.0], [1.0]) == 0.0  # length mismatch
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0  # zero magnitude


# ── experience ───────────────────────────────────────────────────────────────


def test_experience_in_band_is_perfect() -> None:
    assert _experience_score(3, "mid") == 1.0  # mid = (2, 5)


def test_experience_neutral_when_unknown() -> None:
    assert _experience_score(None, "mid") == 0.5
    assert _experience_score(3, None) == 0.5
    assert _experience_score(3, "unknown-level") == 0.5


def test_experience_overqualified_has_floor() -> None:
    # Far above the band still never drops below the 0.3 floor.
    assert _experience_score(40, "junior") == 0.3


def test_experience_underqualified_decays() -> None:
    score = _experience_score(0, "senior")  # senior = (5, 10)
    assert 0.0 <= score < 1.0


# ── location ─────────────────────────────────────────────────────────────────


def test_location_remote_respects_candidate_preference() -> None:
    assert _location_score(None, None, None, None, True, candidate_open_to_remote=True) == 1.0
    assert _location_score(None, None, None, None, True, candidate_open_to_remote=False) == 0.6


def test_location_city_and_state_matching() -> None:
    assert _location_score("Bengaluru", "Karnataka", "Bengaluru", "Karnataka", False, True) == 1.0
    assert _location_score("Pune", "Maharashtra", "Mumbai", "Maharashtra", False, True) == 0.7
    assert _location_score("Pune", "Maharashtra", "Chennai", "Tamil Nadu", False, True) == 0.2


def test_location_unknown_is_neutral() -> None:
    assert _location_score("Pune", "Maharashtra", None, None, False, True) == 0.7


def test_location_relocation_lifts_out_of_city_roles() -> None:
    # A far-city on-site role is normally docked to 0.2. If the candidate is open
    # to relocating anywhere in India, it should rank nearly as well as local.
    far = ("Pune", "Maharashtra", "Chennai", "Tamil Nadu", False, True)
    assert _location_score(*far, candidate_open_to_relocation=False) == 0.2
    assert _location_score(*far, candidate_open_to_relocation=True) == 0.9
    # A same-city role still edges out a relocation one (1.0 > 0.9).
    same = _location_score(
        "Bengaluru",
        "Karnataka",
        "Bengaluru",
        "Karnataka",
        False,
        True,
        candidate_open_to_relocation=True,
    )
    assert same == 1.0


def test_location_scope_gates_geography() -> None:
    far = ("Pune", "Maharashtra", "Chennai", "Tamil Nadu", False, True)
    same_state = ("Pune", "Maharashtra", "Mumbai", "Maharashtra", False, True)
    # city scope: only same-city ranks; far + other-state docked.
    assert _location_score(*far, location_scope="city") == 0.2
    # state scope: same-state ok, different state docked.
    assert _location_score(*same_state, location_scope="state") == 0.7
    assert _location_score(*far, location_scope="state") == 0.2
    # country / global: far city no longer penalised.
    assert _location_score(*far, location_scope="country") == 0.9
    assert _location_score(*far, location_scope="global") == 0.9


def test_location_scope_falls_back_to_relocation_flag() -> None:
    far = ("Pune", "Maharashtra", "Chennai", "Tamil Nadu", False, True)
    # No scope set → derive from open_to_relocation (legacy back-compat).
    assert _location_score(*far, candidate_open_to_relocation=True) == 0.9
    assert _location_score(*far, candidate_open_to_relocation=False) == 0.2


# ── CTC ──────────────────────────────────────────────────────────────────────


def test_ctc_neutral_without_data() -> None:
    assert _ctc_score(None, None, None, None) == 0.5


def test_ctc_overlap_scores_well() -> None:
    # candidate wants 20-30 LPA, job pays 25-35 LPA → overlapping
    assert _ctc_score(2_000_000, 3_000_000, 2_500_000, 3_500_000) >= 0.5


def test_ctc_candidate_wants_more_than_job_pays() -> None:
    # candidate floor far above job ceiling → penalised below 1.0
    score = _ctc_score(5_000_000, 6_000_000, 1_000_000, 1_500_000)
    assert 0.0 <= score < 1.0


# ── explanation ──────────────────────────────────────────────────────────────


def test_explanation_strong_match_and_skill_gap_note() -> None:
    text = _build_explanation(
        overall=0.85,
        skills=0.3,
        experience=0.9,
        location=0.9,
        ctc=0.9,
        job_title="Backend Engineer",
        company_name="Acme",
        candidate_name="Asha",
    )
    assert "Strong match (85%)" in text
    assert "Backend Engineer at Acme" in text
    assert "upskill" in text  # skills < 0.40 triggers the gap note


def test_explanation_weak_match_wording() -> None:
    text = _build_explanation(0.2, 0.2, 0.2, 0.2, 0.2, "Role", None, None)
    assert "Weak match (20%)" in text
    assert "this company" in text  # company_name=None fallback


# ── score_pair integration (fake connection) ─────────────────────────────────


class _FakeConn:
    """Routes the queries score_pair issues to canned rows; records writes."""

    def __init__(self, *, candidate, job, skills_sim=1.0, profile_sim=1.0) -> None:
        self.executed: list[str] = []
        self._candidate = candidate
        self._job = job
        self._skills_sim = skills_sim
        self._profile_sim = profile_sim

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        q = " ".join(query.split())
        if "FROM public.candidates c" in q:
            return self._candidate
        if "FROM public.jobs j" in q:
            return self._job
        if "ce.skills_embedding <=> je.skills_embedding" in q:
            return {"sim": self._skills_sim}
        if "ce.profile_embedding <=> je.jd_embedding" in q:
            return {"sim": self._profile_sim}
        if "FROM public.match_scores" in q:
            return None  # no prior score
        return None

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append(" ".join(query.split()))
        return "OK"


def _candidate_row() -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "full_name": "Asha",
        "current_title": "Backend Engineer",
        "years_experience": 3,
        "skills": ["python"],
        "expected_ctc_min": None,
        "expected_ctc_max": None,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "remote_preference": "any",
        "profile_embedding": "[0.1,0.2]",
        "skills_embedding": "[0.1,0.2]",
        "resume_embedding": None,
        "target_titles": None,
    }


def _job_row() -> dict:
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "title": "Backend Engineer",
        "seniority": "mid",
        "skills_required": ["python"],
        "is_remote": True,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "ctc_min": None,
        "ctc_max": None,
        "company_name": "Acme",
        "jd_embedding": "[0.1,0.2]",
        "title_embedding": "[0.1,0.2]",
        "skills_embedding": "[0.1,0.2]",
    }


async def test_score_pair_weighted_overall_and_persist() -> None:
    conn = _FakeConn(candidate=_candidate_row(), job=_job_row(), skills_sim=1.0, profile_sim=1.0)
    engine = MatchingEngine(conn)  # type: ignore[arg-type]
    overall = await engine.score_pair(_candidate_row()["id"], _job_row()["id"])

    # The job states no CTC band, so that dimension is dropped and the remaining
    # weights are renormalised (skills .40 + profile .30 + experience .15
    # [seniority="mid"] + location .10 = .95). A candidate who perfectly matches
    # every dimension the job *specifies* scores 1.0 — not docked for data the
    # posting omitted. (.40+.30+.15+.10)*1 / .95 = 1.0
    assert overall == 1.0
    assert any("INSERT INTO public.match_scores" in q for q in conn.executed)


async def test_score_pair_returns_none_when_candidate_missing() -> None:
    conn = _FakeConn(candidate=None, job=_job_row())
    engine = MatchingEngine(conn)  # type: ignore[arg-type]
    assert await engine.score_pair("00000000-0000-0000-0000-000000000000", _job_row()["id"]) is None
    assert conn.executed == []  # nothing persisted


# ── relevance signals: lexical skill overlap + title affinity ─────────────────


def test_skill_overlap_full_partial_none() -> None:
    assert _skill_overlap_score(["python", "django"], ["python", "django"]) == 1.0
    # candidate has 1 of the job's 2 required skills → coverage 0.5
    partial = _skill_overlap_score(["python"], ["python", "django"])
    assert partial is not None and 0.0 < partial < 1.0
    assert _skill_overlap_score(["python"], ["sales", "crm"]) == 0.0


def test_skill_overlap_unknown_returns_none() -> None:
    # None (not 0.5!) when a side has nothing to compare — the caller decides.
    assert _skill_overlap_score([], ["python"]) is None
    assert _skill_overlap_score(["python"], []) is None


def test_skill_overlap_normalizes_variants() -> None:
    # "Node.js" == "nodejs", case-insensitive.
    assert _skill_overlap_score(["Node.js"], ["NodeJS"]) == 1.0


def test_title_affinity() -> None:
    assert (
        _title_affinity("Senior Backend Engineer", "Backend Engineer") == 1.0
    )  # stopwords dropped
    assert _title_affinity("Sales Manager", "Backend Engineer") == 0.0
    assert _title_affinity(None, "Backend Engineer") is None


def test_blend_never_returns_blind_half_when_signal_exists() -> None:
    # Lexical coverage is the backbone; a blind 0.5 must only appear when we
    # truly have no skill signal. Zero overlap on a skill-sparse profile (or a
    # strong title match without embeddings yet) is treated as *missing* so a
    # single junk label can't erase an exact title hit — otherwise keep 0.0.
    assert _blend_skills(None, 0.0) == 0.5  # default: skill-sparse (count=0) → neutral
    assert _blend_skills(None, 0.0, candidate_skill_count=5) == 0.0
    assert _blend_skills(None, 0.0, candidate_skill_count=5, title_aff=0.8) == 0.5
    assert _blend_skills(None, 1.0) == 1.0
    assert _blend_skills(1.0, 1.0) == 1.0
    assert _blend_skills(None, None) == 0.5  # only when truly no data
    assert _blend_profile(None, 0.0) == 0.0
    assert _blend_profile(None, None) == 0.5


def test_role_fit_gate_penalises_wrong_function_not_genuine_fits() -> None:
    # Genuine fit (strong title OR strong lexical skills) → no penalty.
    assert _role_fit_gate(1.0, 0.3, 0.9) == 1.0  # perfect title (e.g. Backend->Backend)
    assert _role_fit_gate(0.1, 0.9, 0.5) == 1.0  # different title but strong lexical skills
    assert _role_fit_gate(0.6, 0.6, 0.8) == 1.0  # role_fit at the 0.6 cap
    # Wrong-function match (weak title AND weak lexical skills) → gated down.
    # e.g. a GTM/sales profile on a PM role: title_aff ~0.29, lexical ~0.33.
    assert _role_fit_gate(0.29, 0.33, 0.85) < 0.8
    assert _role_fit_gate(0.0, 0.0, 0.7) == 0.40  # nothing aligns → hardest floor
    # Monotonic: better role fit never lowers the gate.
    gates = [_role_fit_gate(None, s, s + 0.3) for s in (0.0, 0.2, 0.4, 0.6, 1.0)]
    assert gates == sorted(gates)


def test_embedding_lift_never_regresses_lexical_backbone() -> None:
    # HIR-55: embeddings are an additive lift over the lexical/title backbone, so
    # turning the embedding backfill on can only raise (or hold) a score, never
    # drag a strong lexical/title fit down (the old cosine-weighted blend did).
    # Observed cosine bands: profile ~0.29-0.57, skills ~0.08-0.79.
    for backbone in (0.0, 0.3, 0.6, 0.85, 1.0):
        for cos in (0.29, 0.42, 0.57):
            assert _blend_profile(cos, backbone) >= backbone - 1e-9
        for cos in (0.08, 0.43, 0.79):
            assert _blend_skills(cos, backbone) >= backbone - 1e-9
    # A perfect title is preserved (was ~0.57 under the old 0.75·cosine blend).
    assert _blend_profile(0.42, 1.0) == 1.0
    # A weak-title but semantically-close job gets lifted above its title backbone.
    assert _blend_profile(0.57, 0.3) > 0.3


# ── regression: irrelevant jobs must rank far below relevant ones ─────────────


def _cand_no_embed(skills: list[str], title: str, target_titles: list[str] | None = None) -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "full_name": "Asha",
        "current_title": title,
        "years_experience": 3,
        "skills": skills,
        "expected_ctc_min": None,
        "expected_ctc_max": None,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "remote_preference": "any",
        "profile_embedding": None,
        "skills_embedding": None,
        "resume_embedding": None,
        "target_titles": target_titles,
    }


def _job_no_embed(jid: str, skills: list[str], title: str) -> dict:
    return {
        "id": jid,
        "title": title,
        "seniority": "mid",
        "skills_required": skills,
        "is_remote": True,
        "location_city": "Bengaluru",
        "location_state": "Karnataka",
        "ctc_min": None,
        "ctc_max": None,
        "company_name": "X",
        "jd_embedding": None,
        "title_embedding": None,
        "skills_embedding": None,
    }


async def test_relevant_job_outscores_irrelevant_without_embeddings() -> None:
    """The actual user complaint: with no embeddings, an unrelated job used to
    score the same ~0.5 as a perfect-fit one. It must now rank far lower."""
    cand = _cand_no_embed(["python", "django"], "Backend Engineer")
    relevant = _job_no_embed("rel", ["python", "django"], "Backend Engineer")
    irrelevant = _job_no_embed("irr", ["sales", "crm", "cold calling"], "Sales Manager")

    s_rel = await MatchingEngine(_FakeConn(candidate=cand, job=relevant)).score_pair(  # type: ignore[arg-type]
        cand["id"], "rel"
    )
    s_irr = await MatchingEngine(_FakeConn(candidate=cand, job=irrelevant)).score_pair(  # type: ignore[arg-type]
        cand["id"], "irr"
    )
    assert s_rel is not None and s_irr is not None
    assert s_rel > s_irr
    assert s_rel >= 0.7  # reads as a strong/good match
    assert s_irr < 0.5  # the irrelevant sales role is correctly demoted


# ── career-path-aware matching ────────────────────────────────────────────────


def test_best_title_affinity_uses_target_titles() -> None:
    # Current role partially matches the aspirational job (shared engineering
    # domain under the #35 taxonomy), but the exact target title wins outright.
    partial = _best_title_affinity("Engineering Manager", ["Backend Engineer"])
    assert partial is not None and 0.0 < partial < 0.5
    assert (
        _best_title_affinity("Engineering Manager", ["Backend Engineer", "Engineering Manager"])
        == 1.0
    )
    assert _best_title_affinity("Engineering Manager", []) is None


async def test_career_path_target_title_lifts_aspirational_role() -> None:
    """A candidate whose career path targets a role they don't hold yet should see
    that role rank above an unrelated one — the feed follows their trajectory."""
    cand = _cand_no_embed(["python"], "Backend Engineer", target_titles=["Engineering Manager"])
    aspirational = _job_no_embed("em", ["python"], "Engineering Manager")
    unrelated = _job_no_embed("sm", ["python"], "Sales Manager")

    s_asp = await MatchingEngine(_FakeConn(candidate=cand, job=aspirational)).score_pair(  # type: ignore[arg-type]
        cand["id"], "em"
    )
    s_unrel = await MatchingEngine(_FakeConn(candidate=cand, job=unrelated)).score_pair(  # type: ignore[arg-type]
        cand["id"], "sm"
    )
    assert s_asp is not None and s_unrel is not None
    # Same skills/exp/location/ctc → the career-path title match is the difference.
    assert s_asp > s_unrel


# ── candidate fetch caching (perf: fast first-feed scoring) ────────────────────


class _CountingConn(_FakeConn):
    """Counts candidate-row fetches to prove they're cached across pairs."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.candidate_fetches = 0

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        # `target_titles` subquery is unique to _candidate_row's SELECT (the
        # cached one) — not the notify path's candidate lookup.
        if "target_titles" in query:
            self.candidate_fetches += 1
        return await super().fetchrow(query, *args)


async def test_candidate_row_cached_across_pairs() -> None:
    conn = _CountingConn(candidate=_candidate_row(), job=_job_row())
    engine = MatchingEngine(conn)  # type: ignore[arg-type]
    await engine.score_pair("11111111-1111-1111-1111-111111111111", "job-a")
    await engine.score_pair("11111111-1111-1111-1111-111111111111", "job-b")
    await engine.score_pair("11111111-1111-1111-1111-111111111111", "job-c")
    # The (multi-join) candidate row is fetched ONCE, not once per job.
    assert conn.candidate_fetches == 1


# ── seniority fit (relevant-level matching) ───────────────────────────────────


def test_seniority_inference_and_fit_gate() -> None:
    from hireloop_api.services.matching import (
        _candidate_seniority_rank,
        _infer_seniority_from_title,
        _seniority_fit_gate,
    )

    # Title → level inference (scraped JDs rarely state a level).
    assert _infer_seniority_from_title("Business Development Representative") == "junior"
    assert _infer_seniority_from_title("Business Development Executive") == "junior"
    assert _infer_seniority_from_title("Head of Growth") == "director"
    assert _infer_seniority_from_title("VP Marketing") == "vp"
    assert _infer_seniority_from_title("Senior Backend Engineer") == "senior"
    assert _infer_seniority_from_title("Data Scientist") is None  # no level signal

    # A 13-yr "Go-To-Market Lead" reads as lead (title primary, not VP-by-years).
    leader = _candidate_seniority_rank("Go-To-Market Lead", 13)
    assert leader == 4

    # Big level gap penalised; adjacent level untouched; unknown → no penalty.
    assert _seniority_fit_gate(leader, "junior") < 0.7  # leader vs entry BDR → drop
    assert _seniority_fit_gate(leader, "director") == 1.0  # peer level → kept
    assert _seniority_fit_gate(leader, "mid") == 0.9  # one extra step → gentle
    assert _seniority_fit_gate(leader, None) == 1.0  # unknown job level → no penalty
    assert _seniority_fit_gate(None, "junior") == 1.0  # unknown candidate → no penalty
