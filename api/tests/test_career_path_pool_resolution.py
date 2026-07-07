"""Pool definition resolution must match on FUNCTION, not seniority words.

Regression: "Manager - Customer Success" linked to the Engineering Manager
pool purely via the shared token "manager" — a CSM candidate's first job
feed was one Engineering Manager role.
"""

from __future__ import annotations

import asyncio
import uuid

from hireloop_api.services.career_path_pool import resolve_definition_for_title


class _FakeDb:
    """Returns a fixed set of pool definitions."""

    def __init__(self, definitions: list[dict]) -> None:
        self._definitions = definitions

    async def fetch(self, query: str, *args: object) -> list[dict]:
        return self._definitions


def _defs() -> list[dict]:
    return [
        {
            "id": uuid.uuid4(),
            "slug": "engineering-manager",
            "display_title": "Engineering Manager",
            "search_titles": ["Engineering Manager", "Software Engineering Manager"],
            "pool_min_jobs": 20,
            "is_senior": True,
            "market": "IN",
        },
        {
            "id": uuid.uuid4(),
            "slug": "customer-success",
            "display_title": "Customer Success Manager",
            "search_titles": ["Customer Success Manager", "Client Success Manager"],
            "pool_min_jobs": 20,
            "is_senior": False,
            "market": "IN",
        },
        {
            "id": uuid.uuid4(),
            "slug": "head-of-growth",
            "display_title": "Head of Growth",
            "search_titles": ["Head of Growth", "VP Growth", "Growth Manager"],
            "pool_min_jobs": 20,
            "is_senior": True,
            "market": "IN",
        },
    ]


def _resolve(title: str) -> str | None:
    db = _FakeDb(_defs())
    row = asyncio.run(resolve_definition_for_title(db, title))  # type: ignore[arg-type]
    return row["slug"] if row else None


def test_csm_resolves_to_customer_success_not_engineering() -> None:
    assert _resolve("Manager - Customer Success") == "customer-success"
    assert _resolve("Customer Success Manager") == "customer-success"


def test_generic_manager_title_matches_no_pool() -> None:
    # Pure level words share no function token with any pool.
    assert _resolve("Assistant Manager") is None
    assert _resolve("Senior Manager") is None


def test_decorated_growth_title_still_resolves() -> None:
    assert _resolve("VP Growth / CMO – AI SaaS") == "head-of-growth"


def test_engineering_manager_still_resolves() -> None:
    assert _resolve("Engineering Manager") == "engineering-manager"
