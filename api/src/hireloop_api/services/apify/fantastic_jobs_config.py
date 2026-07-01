"""
Fantastic.jobs Career Site Job Listing API — actor input builder.

Maps Hireloop settings + per-run overrides to the Apify actor JSON schema:
https://apify.com/fantastic-jobs/career-site-job-listing-api/input-schema
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from hireloop_api.config import Settings


class FantasticJobsRunParams(BaseModel):
    """Per-run parameters for fantastic-jobs/career-site-job-listing-api."""

    time_range: str = "24h"
    limit: int = Field(default=1000, ge=10, le=5000)

    title_search: list[str] | None = None
    title_exclusion_search: list[str] | None = None
    location_search: list[str] | None = None
    location_exclusion_search: list[str] | None = None
    description_search: list[str] | None = None
    description_exclusion_search: list[str] | None = None

    organization_slug_filter: list[str] | None = None
    organization_slug_exclusion_filter: list[str] | None = None
    organization_search: list[str] | None = None
    organization_exclusion_search: list[str] | None = None

    remove_agency: bool = True
    recruiter_only: bool = False
    description_type: str = "text"
    date_posted_after: str | None = None

    seniority_filter: list[str] | None = None
    no_direct_apply: bool = False
    direct_apply: bool = False

    industry_filter: list[str] | None = None
    industry_exclusion_filter: list[str] | None = None
    organization_employees_lte: int | None = None
    organization_employees_gte: int | None = None
    organization_size_filter: list[str] | None = None

    exclude_ats_duplicate: bool = True
    populate_ai_remote_location: bool = True
    populate_ai_remote_location_derived: bool = True

    has_salary: bool | None = None
    ai_work_arrangement_filter: list[str] | None = None
    ai_employment_type_filter: list[str] | None = None
    ai_experience_level_filter: list[str] | None = None
    ai_visa_sponsorship_filter: bool | None = None
    ai_taxonomies_filter: list[str] | None = None
    ai_taxonomies_primary_filter: list[str] | None = None
    ai_taxonomies_exclusion_filter: list[str] | None = None
    ai_language_filter: list[str] | None = None

    has_no_location: bool = False


def _non_empty(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    cleaned = [v.strip() for v in values if v and v.strip()]
    return cleaned or None


def build_actor_input(params: FantasticJobsRunParams) -> dict[str, Any]:
    """
    Build the JSON body for POST /acts/{actor}/runs.

    Omits unset optional filters so the actor uses its own defaults.
    """
    payload: dict[str, Any] = {
        "timeRange": params.time_range,
        "limit": max(10, min(int(params.limit), 5000)),
        "removeAgency": params.remove_agency,
        "recruiterOnly": params.recruiter_only,
        "descriptionType": params.description_type,
        "excludeATSDuplicate": params.exclude_ats_duplicate,
        "populateAiRemoteLocation": params.populate_ai_remote_location,
        "populateAiRemoteLocationDerived": params.populate_ai_remote_location_derived,
        "hasNoLocation": params.has_no_location,
    }

    if params.no_direct_apply:
        payload["noDirectApply"] = True
    if params.direct_apply:
        payload["directApply"] = True

    if params.date_posted_after:
        payload["datePostedAfter"] = params.date_posted_after

    if params.has_salary is not None:
        payload["hasSalary"] = params.has_salary

    if params.ai_visa_sponsorship_filter is not None:
        payload["aiVisaSponsorshipFilter"] = params.ai_visa_sponsorship_filter

    if params.organization_employees_lte is not None:
        payload["organizationEmployeesLte"] = params.organization_employees_lte
    if params.organization_employees_gte is not None:
        payload["organizationEmployeesGte"] = params.organization_employees_gte

    _array_fields: list[tuple[str, list[str] | None]] = [
        ("titleSearch", params.title_search),
        ("titleExclusionSearch", params.title_exclusion_search),
        ("locationSearch", params.location_search),
        ("locationExclusionSearch", params.location_exclusion_search),
        ("descriptionSearch", params.description_search),
        ("descriptionExclusionSearch", params.description_exclusion_search),
        ("organizationSlugFilter", params.organization_slug_filter),
        ("organizationSlugExclusionFilter", params.organization_slug_exclusion_filter),
        ("organizationSearch", params.organization_search),
        ("organizationExclusionSearch", params.organization_exclusion_search),
        ("seniorityFilter", params.seniority_filter),
        ("industryFilter", params.industry_filter),
        ("industryExclusionFilter", params.industry_exclusion_filter),
        ("organizationSizeFilter", params.organization_size_filter),
        ("aiWorkArrangementFilter", params.ai_work_arrangement_filter),
        ("aiEmploymentTypeFilter", params.ai_employment_type_filter),
        ("aiExperienceLevelFilter", params.ai_experience_level_filter),
        ("aiTaxonomiesFilter", params.ai_taxonomies_filter),
        ("aiTaxonomiesPrimaryFilter", params.ai_taxonomies_primary_filter),
        ("aiTaxonomiesExclusionFilter", params.ai_taxonomies_exclusion_filter),
        ("aiLanguageFilter", params.ai_language_filter),
    ]

    for actor_key, values in _array_fields:
        cleaned = _non_empty(values)
        if cleaned:
            payload[actor_key] = cleaned

    if not payload.get("locationSearch"):
        payload["locationSearch"] = ["India"]

    return payload


def fantastic_defaults_from_settings(settings: Settings | None) -> FantasticJobsRunParams:
    """Static filters from api/.env — merged into every ingest run."""
    if settings is None:
        return FantasticJobsRunParams()

    has_salary: bool | None = None
    if settings.fantastic_jobs_require_salary:
        has_salary = True

    visa: bool | None = None
    if settings.fantastic_jobs_visa_sponsorship_only:
        visa = True

    return FantasticJobsRunParams(
        remove_agency=settings.fantastic_jobs_remove_agency,
        recruiter_only=settings.fantastic_jobs_recruiter_only,
        exclude_ats_duplicate=settings.fantastic_jobs_exclude_ats_duplicate,
        populate_ai_remote_location=settings.fantastic_jobs_populate_ai_remote,
        populate_ai_remote_location_derived=settings.fantastic_jobs_populate_ai_remote,
        title_exclusion_search=_non_empty(settings.fantastic_jobs_title_exclusions),
        location_exclusion_search=_non_empty(settings.fantastic_jobs_location_exclusions),
        description_exclusion_search=_non_empty(settings.fantastic_jobs_description_exclusions),
        organization_exclusion_search=_non_empty(settings.fantastic_jobs_organization_exclusions),
        organization_slug_exclusion_filter=_non_empty(
            settings.fantastic_jobs_organization_slug_exclusions
        ),
        industry_exclusion_filter=_non_empty(settings.fantastic_jobs_industry_exclusions),
        ai_work_arrangement_filter=_non_empty(settings.fantastic_jobs_ai_work_arrangement),
        ai_employment_type_filter=_non_empty(settings.fantastic_jobs_ai_employment_types),
        ai_experience_level_filter=_non_empty(settings.fantastic_jobs_ai_experience_levels),
        ai_language_filter=_non_empty(settings.fantastic_jobs_ai_languages),
        seniority_filter=_non_empty(settings.fantastic_jobs_seniority_filter),
        industry_filter=_non_empty(settings.fantastic_jobs_industry_filter),
        organization_search=_non_empty(settings.fantastic_jobs_organization_search),
        organization_slug_filter=_non_empty(settings.fantastic_jobs_organization_slug_filter),
        organization_size_filter=_non_empty(settings.fantastic_jobs_organization_size_filter),
        ai_taxonomies_filter=_non_empty(settings.fantastic_jobs_ai_taxonomies),
        ai_taxonomies_primary_filter=_non_empty(settings.fantastic_jobs_ai_taxonomies_primary),
        ai_taxonomies_exclusion_filter=_non_empty(settings.fantastic_jobs_ai_taxonomies_exclusions),
        has_salary=has_salary,
        ai_visa_sponsorship_filter=visa,
        no_direct_apply=settings.fantastic_jobs_no_direct_apply,
        direct_apply=settings.fantastic_jobs_direct_apply_only,
        organization_employees_gte=settings.fantastic_jobs_org_employees_min or None,
        organization_employees_lte=settings.fantastic_jobs_org_employees_max or None,
    )


def merge_ingest_run_params(
    settings: Settings | None,
    *,
    title_search: list[str] | None,
    location_search: list[str] | None,
    limit: int,
    time_range: str,
    description_search: list[str] | None = None,
) -> FantasticJobsRunParams:
    """Combine env defaults with per-run title/location/limit overrides."""
    base = fantastic_defaults_from_settings(settings)
    data = base.model_dump()
    data.update(
        {
            "time_range": time_range,
            "limit": max(10, min(limit, 5000)),
            "title_search": _non_empty(title_search),
            "location_search": _non_empty(location_search),
            "description_search": _non_empty(description_search),
        }
    )
    return FantasticJobsRunParams(**data)


def description_search_for_candidate(
    skills: list[str] | None,
    settings: Settings | None,
) -> list[str] | None:
    """
    Optional descriptionSearch for candidate-scoped ingests.

    Fantastic.jobs warns: keep very specific, max a handful of terms, not with 6m.
    """
    if settings is None or not settings.fantastic_jobs_use_description_search_for_candidates:
        return None
    if not skills:
        return None
    cap = max(1, min(settings.fantastic_jobs_max_description_search_terms, 5))
    terms: list[str] = []
    for skill in skills:
        s = (skill or "").strip()
        if not s:
            continue
        # Prefix match per schema: Python:* matches Pythonic, etc.
        if not s.endswith(":*"):
            s = f"{s}:*"
        terms.append(s)
        if len(terms) >= cap:
            break
    return terms or None
