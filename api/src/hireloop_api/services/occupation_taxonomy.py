"""
Occupation taxonomy — ESCO/O*NET-inspired role families and aliases.

Offline mapping layer; extend with observed production titles over time.
"""

from __future__ import annotations

from typing import Any

# role_id → display titles for Apify query planning
ROLE_QUERY_TITLES: dict[str, list[str]] = {
    "software_engineering": ["Software Engineer", "Backend Engineer", "Full Stack Developer"],
    "data_science": ["Data Scientist", "Machine Learning Engineer"],
    "data_analytics": ["Data Analyst", "Business Intelligence Analyst"],
    "product_management": ["Product Manager", "Senior Product Manager"],
    "project_management": ["Project Manager", "Technical Project Manager"],
    "program_management": ["Program Manager", "Technical Program Manager"],
    "category_management": ["Category Manager", "Merchandising Manager"],
    "merchandising": ["Merchandising Manager", "Buying Manager"],
    "human_resources": ["HR Manager", "Human Resources Business Partner"],
    "quality_engineering": ["QA Engineer", "SDET", "Quality Engineer"],
    "design": ["Product Designer", "UX Designer"],
    "marketing": ["Marketing Manager", "Growth Marketing Manager"],
    "sales": ["Sales Manager", "Account Executive"],
    "finance": ["Financial Analyst", "Finance Manager"],
    "operations": ["Operations Manager", "Business Operations Manager"],
    "customer_success": ["Customer Success Manager", "Implementation Manager"],
    "nursing": ["Registered Nurse", "Staff Nurse"],
}

# ESCO-style occupation URI stubs (extend with full URIs when licensing allows)
ESCO_ROLE_IDS: dict[str, str] = {
    "software_engineering": "http://data.europa.eu/esco/occupation/software-developer",
    "product_management": "http://data.europa.eu/esco/occupation/product-manager",
    "data_science": "http://data.europa.eu/esco/occupation/data-scientist",
    "category_management": "http://data.europa.eu/esco/occupation/category-manager",
}

# O*NET SOC code stubs
ONET_SOC_CODES: dict[str, str] = {
    "software_engineering": "15-1252.00",
    "product_management": "11-2021.00",
    "data_science": "15-2051.00",
    "data_analytics": "15-2051.01",
    "category_management": "11-2022.00",
    "nursing": "29-1141.00",
}

# Indian-market title aliases → role_id
TITLE_ALIASES: dict[str, str] = {
    "sde": "software_engineering",
    "sde ii": "software_engineering",
    "sde 2": "software_engineering",
    "sde iii": "software_engineering",
    "sde 3": "software_engineering",
    "sdet": "quality_engineering",
    "hrbp": "human_resources",
    "pm": "product_management",
    "apm": "product_management",
    "gtm": "sales",
    "csm": "customer_success",
    "bdr": "sales",
    "sdr": "sales",
    "ae": "sales",
    "fp&a": "finance",
    "m&a": "finance",
    "rn": "nursing",
}


def resolve_role_id(title: str | None) -> str | None:
    """Map a raw title to canonical role_id using aliases + patterns."""
    from hireloop_api.services.titles import parse_title

    if not title:
        return None
    low = title.strip().lower()
    if low in TITLE_ALIASES:
        return TITLE_ALIASES[low]
    sig = parse_title(title)
    return sig.role_id or sig.family_id


def apify_query_variants(
    *,
    primary_title: str,
    role_id: str | None = None,
    specialty: str | None = None,
    alternate_titles: list[str] | None = None,
    max_queries: int = 4,
) -> list[str]:
    """Deterministic title-oriented queries for johnvc/Google-Jobs-Scraper."""
    rid = role_id or resolve_role_id(primary_title)
    variants: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        key = q.strip().lower()
        if q.strip() and key not in seen:
            seen.add(key)
            variants.append(q.strip())

    add(primary_title)
    if specialty and primary_title:
        add(f"{specialty} {primary_title}")
    if rid and rid in ROLE_QUERY_TITLES:
        for alt in ROLE_QUERY_TITLES[rid][:2]:
            add(alt)
    for alt in alternate_titles or []:
        add(alt)
    return variants[:max_queries]


def taxonomy_metadata(role_id: str | None) -> dict[str, Any]:
    """Return ESCO/O*NET identifiers for explainability."""
    if not role_id:
        return {}
    return {
        "role_id": role_id,
        "esco_uri": ESCO_ROLE_IDS.get(role_id),
        "onet_soc": ONET_SOC_CODES.get(role_id),
    }
