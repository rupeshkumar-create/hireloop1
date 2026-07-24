"""P0-P2: title taxonomy, occupation families, hybrid retrieval helpers."""

from __future__ import annotations

import pytest

from hireloop_api.services.job_search_buckets import bucket_key, canonical_job_fingerprint
from hireloop_api.services.occupation_taxonomy import (
    apify_query_variants,
    resolve_role_id,
    taxonomy_metadata,
)
from hireloop_api.services.titles import (
    best_intent_title_affinity,
    intent_titles,
    occupation_families_compatible,
    parse_title,
    specialties_compatible,
    title_affinity,
)


def test_synonym_titles_still_match() -> None:
    assert title_affinity("Backend Developer", "Backend Engineer") >= 0.9
    assert title_affinity("Software Programmer", "Software Engineer") >= 0.9


def test_indian_shorthand_expands() -> None:
    assert title_affinity("SDE II", "Software Engineer") >= 0.65
    aff = title_affinity("Senior PM", "Product Manager")
    assert aff is not None and aff >= 0.65


@pytest.mark.parametrize(
    ("candidate", "job"),
    [
        ("Product Manager", "Project Manager"),
        ("Product Manager", "Marketing Manager"),
        ("Backend Engineer", "Data Engineer"),
        ("Head of Growth", "Director of Sales"),
        ("Front Office Manager", "Frontend Engineering Manager"),
    ],
)
def test_unrelated_titles_do_not_pass_gate(candidate: str, job: str) -> None:
    assert (title_affinity(candidate, job) or 0.0) < 0.35


@pytest.mark.parametrize(
    ("candidate", "job"),
    [
        ("SDE II", "Software Engineer II"),
        ("Backend Developer", "Backend Engineer"),
        ("HRBP", "Human Resources Business Partner"),
        ("Category Manager - Fashion & Apparel", "Fashion Category Manager"),
    ],
)
def test_alias_titles_match(candidate: str, job: str) -> None:
    assert (title_affinity(candidate, job) or 0.0) >= 0.55


def test_fullstack_backend_compatible() -> None:
    assert specialties_compatible(frozenset({"fullstack"}), frozenset({"backend"}))


def test_sre_devops_compatible() -> None:
    assert specialties_compatible(frozenset({"reliability"}), frozenset({"devops"}))


def test_intern_vs_principal_not_perfect() -> None:
    aff = title_affinity("Intern Software Engineer", "Principal Software Engineer")
    assert aff is not None and aff < 0.85


def test_intent_titles_excludes_current_by_default() -> None:
    cand = {
        "prioritized_title": "Product Manager",
        "target_titles": ["Program Manager"],
        "current_title": "Sales Manager",
        "looking_for": None,
    }
    titles = intent_titles(cand)
    assert "Product Manager" in titles
    assert "Sales Manager" not in titles


def test_best_intent_ignores_current_role_pollution() -> None:
    cand = {
        "prioritized_title": "Product Manager",
        "current_title": "Sales Manager",
    }
    aff = best_intent_title_affinity("Sales Manager", cand)
    assert aff < 0.35


def test_parse_title_pm_ambiguous() -> None:
    sig = parse_title("PM")
    assert sig.ambiguous is True
    assert len(sig.candidate_interpretations) >= 2


def test_apify_query_variants_title_oriented() -> None:
    variants = apify_query_variants(
        primary_title="Category Manager",
        specialty="Fashion",
        alternate_titles=["Merchandising Manager"],
        max_queries=4,
    )
    assert variants[0] == "Category Manager"
    assert all(len(v.split()) <= 5 for v in variants)


def test_bucket_key_format() -> None:
    key = bucket_key(role_id="product_management", market="IN", location="Bengaluru")
    assert key == "product_management|IN|bengaluru|en"


def test_canonical_fingerprint_stable() -> None:
    a = canonical_job_fingerprint(company_name="Acme", title="Engineer", location="London")
    b = canonical_job_fingerprint(company_name="Acme", title="Engineer", location="London")
    assert a == b


def test_resolve_role_id_sde() -> None:
    assert resolve_role_id("SDE II") == "software_engineering"


def test_taxonomy_metadata() -> None:
    meta = taxonomy_metadata("software_engineering")
    assert meta["role_id"] == "software_engineering"
    assert "onet_soc" in meta


def test_occupation_families_compatible_gate() -> None:
    assert occupation_families_compatible(["Backend Engineer"], "Backend Engineer") is True
    assert occupation_families_compatible(["Backend Engineer"], "Registered Nurse") is False
