"""
Tests for the match-feed ranking & presentation layer (P10/P11).

Pure functions — no DB, network, or keys.
"""

from __future__ import annotations

from hireloop_api.services.ranking import (
    HardConstraints,
    assemble_first_screen,
    attach_tiers,
    boost_by_saved,
    dedupe_jobs,
    hybrid_rank,
    job_similarity,
    mmr_diversify,
    passes_hard_constraints,
    reciprocal_rank_fusion,
    score_to_tier,
)


def _job(
    job_id: str,
    *,
    company: str = "Acme",
    title: str = "Backend Engineer",
    seniority: str = "mid",
    city: str = "Bengaluru",
    score: float = 0.8,
    is_remote: bool = False,
    ctc_min: int | None = None,
    ctc_max: int | None = None,
    apply_url: str | None = None,
) -> dict:
    return {
        "job_id": job_id,
        "company_name": company,
        "title": title,
        "seniority": seniority,
        "location_city": city,
        "overall_score": score,
        "is_remote": is_remote,
        "ctc_min": ctc_min,
        "ctc_max": ctc_max,
        "apply_url": apply_url,
    }


# ── tiers ────────────────────────────────────────────────────────────────────


def test_score_to_tier_boundaries() -> None:
    assert score_to_tier(0.85).key == "strong"
    assert score_to_tier(0.80).key == "strong"
    assert score_to_tier(0.62).key == "good"
    assert score_to_tier(0.45).key == "worth_a_look"
    assert score_to_tier(0.20).key == "exploratory"


def test_score_to_tier_clamps_out_of_range() -> None:
    assert score_to_tier(1.5).key == "strong"
    assert score_to_tier(-0.2).key == "exploratory"


def test_attach_tiers_annotates_each_item() -> None:
    items = [_job("a", score=0.9), _job("b", score=0.3)]
    attach_tiers(items)
    assert items[0]["tier"] == "strong" and items[0]["tier_label"] == "Strong fit"
    assert items[1]["tier"] == "exploratory"


# ── similarity ───────────────────────────────────────────────────────────────


def test_job_similarity_identical_is_one() -> None:
    a = _job("a")
    b = _job("b")  # same company/title/seniority/city
    assert job_similarity(a, b) == 1.0


def test_job_similarity_unrelated_is_low() -> None:
    a = _job("a", company="Acme", title="Backend Engineer", seniority="mid", city="Bengaluru")
    b = _job("b", company="Bolt", title="Data Scientist", seniority="senior", city="Mumbai")
    assert job_similarity(a, b) == 0.0


# ── de-dup ───────────────────────────────────────────────────────────────────


def test_dedupe_collapses_same_apply_url_keeping_best() -> None:
    items = [
        _job("low", score=0.70, apply_url="https://x.test/role"),
        _job("high", score=0.90, apply_url="https://x.test/role"),
    ]
    out = dedupe_jobs(items)
    assert len(out) == 1
    assert out[0]["job_id"] == "high"


def test_dedupe_collapses_near_identical_postings() -> None:
    items = [_job("a", score=0.88), _job("b", score=0.91)]  # similarity 1.0
    out = dedupe_jobs(items)
    assert len(out) == 1
    assert out[0]["job_id"] == "b"  # higher score kept


def test_dedupe_on_long_feed_like_limit_50() -> None:
    """Matches sidebar uses limit=50; dedupe must still collapse near-dupes."""
    items = [
        _job("a1", company="Acme", title="Backend Engineer", score=0.91),
        _job("a2", company="Acme", title="Backend Engineer", score=0.88),
        _job("a3", company="Acme", title="Backend Engineer", score=0.85),
        _job(
            "b1",
            company="Bolt",
            title="Data Scientist",
            seniority="senior",
            city="Mumbai",
            score=0.80,
        ),
        _job(
            "b2",
            company="Bolt",
            title="Data Scientist",
            seniority="mid",
            city="Mumbai",
            score=0.78,
            apply_url="https://jobs.example/bolt-ds",
        ),
    ]
    # Pad to a long list like the default feed page size.
    for i in range(45):
        items.append(
            _job(
                f"unique-{i}",
                company=f"Co{i}",
                title=f"Role {i}",
                seniority="mid",
                city="Pune",
                score=0.70 - (i * 0.001),
            )
        )
    out = dedupe_jobs(items)
    ids = {it["job_id"] for it in out}
    assert "a1" in ids
    assert "a2" not in ids and "a3" not in ids
    assert "b1" in ids
    assert "b2" not in ids
    assert len(out) == 1 + 1 + 45  # one Acme, one Bolt, 45 unique


def test_dedupe_keeps_distinct_roles() -> None:
    items = [
        _job("a", company="Acme", title="Backend Engineer"),
        _job("b", company="Bolt", title="Data Scientist", seniority="senior", city="Mumbai"),
    ]
    assert len(dedupe_jobs(items)) == 2


def test_dedupe_normalizes_apply_urls() -> None:
    # Same canonical URL despite scheme / query / trailing slash → one kept.
    items = [
        _job("a", score=0.9, apply_url="https://x.test/role?utm=linkedin"),
        _job(
            "b",
            company="Bolt",
            title="Data Scientist",
            seniority="senior",
            city="Mumbai",
            score=0.8,
            apply_url="http://x.test/role/",
        ),
    ]
    out = dedupe_jobs(items)
    assert len(out) == 1
    assert out[0]["job_id"] == "a"  # higher score kept


def test_dedupe_catches_cross_source_same_company_title() -> None:
    # The screenshot case: "Sales Manager @ AccorHotel" from two ATSs — same
    # company + title + city, seniority differs → similarity 0.85 → deduped.
    items = [
        _job("smart", company="AccorHotel", title="Sales Manager", seniority="mid", score=0.6),
        _job("oracle", company="AccorHotel", title="Sales Manager", seniority="senior", score=0.5),
    ]
    assert len(dedupe_jobs(items)) == 1


# ── saved-job personalisation ─────────────────────────────────────────────────


def test_boost_by_saved_lifts_similar_jobs() -> None:
    saved = [_job("s", company="Acme", title="Backend Engineer")]
    items = [
        _job("x", company="Acme", title="Backend Engineer", score=0.60),  # ~ saved
        _job(
            "y",
            company="Bolt",
            title="Data Scientist",
            seniority="senior",
            city="Mumbai",
            score=0.60,
        ),
    ]
    boost_by_saved(items, saved, output_key="_ranking_score")
    bx = next(i for i in items if i["job_id"] == "x")
    by = next(i for i in items if i["job_id"] == "y")
    assert bx["overall_score"] == 0.60  # displayed match percentage stays canonical
    assert bx["_ranking_score"] > 0.60 and bx["saved_affinity"] == 1.0  # ranking boosted
    assert by["overall_score"] == 0.60 and by["_ranking_score"] == 0.60
    assert by["saved_affinity"] == 0.0  # untouched


def test_boost_by_saved_is_noop_when_nothing_saved() -> None:
    items = [_job("x", score=0.6)]
    boost_by_saved(items, [])
    assert items[0]["overall_score"] == 0.6
    assert "saved_affinity" not in items[0]


# ── hard constraints ─────────────────────────────────────────────────────────


def test_remote_only_rejects_onsite() -> None:
    c = HardConstraints(remote_preference="remote_only")
    assert passes_hard_constraints(_job("a", is_remote=True), c) is True
    assert passes_hard_constraints(_job("b", is_remote=False), c) is False


def test_onsite_only_rejects_remote() -> None:
    c = HardConstraints(remote_preference="onsite_only")
    assert passes_hard_constraints(_job("a", is_remote=False), c) is True
    assert passes_hard_constraints(_job("b", is_remote=True), c) is False


def test_any_allows_both() -> None:
    c = HardConstraints(remote_preference="any")
    assert passes_hard_constraints(_job("a", is_remote=True), c) is True
    assert passes_hard_constraints(_job("b", is_remote=False), c) is True


def test_ctc_floor_rejects_low_band_but_allows_unknown() -> None:
    c = HardConstraints(ctc_floor=2_000_000)  # slack 0.8 → reject ceilings < 1.6M
    assert passes_hard_constraints(_job("low", ctc_max=1_000_000), c) is False
    assert passes_hard_constraints(_job("ok", ctc_max=1_800_000), c) is True
    assert passes_hard_constraints(_job("unknown"), c) is True  # no pay stated → allowed


# ── MMR diversity ────────────────────────────────────────────────────────────


def test_mmr_promotes_diverse_item_into_top_slots() -> None:
    items = [
        _job("a1", company="Acme", title="Backend Engineer", score=0.90),
        _job("a2", company="Acme", title="Backend Engineer", score=0.88),
        _job("a3", company="Acme", title="Frontend Engineer", score=0.86),
        _job(
            "b1",
            company="Bolt",
            title="Data Scientist",
            seniority="senior",
            city="Mumbai",
            score=0.80,
        ),
    ]
    out = mmr_diversify(items, k=3)
    assert out[0]["job_id"] == "a1"  # top relevance still leads
    assert out[1]["job_id"] == "b1"  # diverse pick promoted above the near-dupes
    # The near-duplicate a2 is pushed out of the diversified head.
    assert out[-1]["job_id"] == "a2"


def test_mmr_is_noop_for_tiny_lists() -> None:
    items = [_job("a")]
    assert mmr_diversify(items, k=3) == items


# ── first-screen curation ────────────────────────────────────────────────────


def test_assemble_first_screen_dedupes_then_diversifies() -> None:
    items = [
        _job("a1", company="Acme", title="Backend Engineer", score=0.90),
        _job("a2", company="Acme", title="Backend Engineer", score=0.88),  # near-dup of a1
        _job("a3", company="Acme", title="Frontend Engineer", score=0.86),
        _job(
            "b1",
            company="Bolt",
            title="Data Scientist",
            seniority="senior",
            city="Mumbai",
            score=0.80,
        ),
    ]
    out = assemble_first_screen(items, screen_size=8)
    ids = [it["job_id"] for it in out]
    assert "a2" not in ids  # de-duplicated away
    assert out[0]["job_id"] == "a1"
    assert out[1]["job_id"] == "b1"  # variety on the opening screen
    # First two cards are not from the same company.
    assert out[0]["company_name"] != out[1]["company_name"]


# ── Hybrid retrieval (RRF) — HIR-22 ────────────────────────────────────────────


def test_rrf_rewards_items_high_in_multiple_lists() -> None:
    # "b" is #1 in list two and #2 in list one → should beat "a" (top of one only).
    scores = reciprocal_rank_fusion([["a", "b", "c"], ["b", "c", "a"]])
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]


def test_rrf_weights_bias_a_list() -> None:
    base = reciprocal_rank_fusion([["a", "b"], ["b", "a"]])
    assert base["a"] == base["b"]  # symmetric → tie
    weighted = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], weights=[3.0, 1.0])
    assert weighted["a"] > weighted["b"]  # first list weighted heavier


def test_hybrid_rank_promotes_item_strong_in_both_signals() -> None:
    # j1 tops the composite but is weak on skills; j2 is high in BOTH signals.
    # RRF (rank-based) rewards the consistently-strong j2 over the one-list leader.
    items = [
        {"job_id": "j1", "overall_score": 0.90, "skills_score": 0.40},
        {"job_id": "j2", "overall_score": 0.80, "skills_score": 0.85},
        {"job_id": "j3", "overall_score": 0.70, "skills_score": 0.84},
    ]
    ranked = hybrid_rank(items, signal_keys=("overall_score", "skills_score"))
    assert ranked[0]["job_id"] == "j2"
    assert all(0.0 <= it["fusion_score"] <= 1.0 for it in ranked)


def test_hybrid_rank_skips_absent_signal() -> None:
    # skills_score null everywhere (embeddings/scoring not populated) → ignored;
    # falls back to overall_score ordering without crashing.
    items = [
        {"job_id": "j1", "overall_score": 0.40, "skills_score": None},
        {"job_id": "j2", "overall_score": 0.80, "skills_score": None},
    ]
    ranked = hybrid_rank(items, signal_keys=("overall_score", "skills_score"))
    assert ranked[0]["job_id"] == "j2"


def test_hybrid_rank_single_item_passthrough() -> None:
    items = [{"job_id": "only", "overall_score": 0.5}]
    assert hybrid_rank(items, signal_keys=("overall_score",)) == items
