"""
Market intelligence for recruiter roles — comp bands, competitors, skill gaps.
Deterministic SQL from live jobs corpus (reuses career_intelligence patterns).
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from hireloop_api.markets import normalize_market
from hireloop_api.services.salary_benchmark import lookup_salary_benchmark


def _parse_json_list(val: object | None) -> list[Any]:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _parse_skills(role: dict[str, Any]) -> list[str]:
    skills: list[str] = []
    for item in _parse_json_list(role.get("must_haves")):
        if item:
            skills.append(str(item).strip().lower())
    jd = role.get("jd_structured")
    if isinstance(jd, str):
        try:
            jd = json.loads(jd)
        except (ValueError, TypeError):
            jd = {}
    if isinstance(jd, dict):
        for key in ("required_skills", "skills", "must_have_skills"):
            for item in jd.get(key) or []:
                if item:
                    skills.append(str(item).strip().lower())
    return list(dict.fromkeys(skills))[:30]


async def compute_role_market_intel(
    db: asyncpg.Connection,
    role: dict[str, Any],
    *,
    market: str = "IN",
) -> dict[str, Any]:
    """Compute comp band, competitors, and skill gap analysis for a role."""
    from hireloop_api.services.career_intelligence.market import _live_sql

    market = normalize_market(market)
    live = _live_sql(market)
    title = (role.get("title") or "").strip()
    skills = _parse_skills(role)
    city = role.get("location_city")

    # ── Comp suggestion ─────────────────────────────────────────────────────
    job_row = {
        "title": title,
        "location_city": city,
        "country_code": market,
        "seniority": (role.get("jd_structured") or {}).get("seniority", "mid")
        if isinstance(role.get("jd_structured"), dict)
        else "mid",
        "ctc_min": role.get("comp_min"),
        "ctc_max": role.get("comp_max"),
    }
    benchmark = lookup_salary_benchmark(job_row)

    # Live corpus percentiles when enough data
    comp_from_corpus: dict[str, Any] | None = None
    if title:
        title_like = title.replace("%", "").replace("_", "").strip()
        comp_rows = await db.fetch(
            f"""
            SELECT j.ctc_min, j.ctc_max
            FROM public.jobs j
            WHERE {live}
              AND j.title ILIKE '%' || $1 || '%'
              AND (j.ctc_min IS NOT NULL OR j.ctc_max IS NOT NULL)
            LIMIT 200
            """,
            title_like,
        )
        mins = [r["ctc_min"] for r in comp_rows if r["ctc_min"]]
        maxs = [r["ctc_max"] for r in comp_rows if r["ctc_max"]]
        if len(mins) + len(maxs) >= 5:
            all_vals = sorted(mins + maxs)
            mid = len(all_vals) // 2
            comp_from_corpus = {
                "sample_size": len(comp_rows),
                "p25": all_vals[max(0, mid // 2)],
                "p50": all_vals[mid],
                "p75": all_vals[min(len(all_vals) - 1, mid + mid // 2)],
                "source": "live_jobs",
            }

    role_comp = {
        "comp_min": role.get("comp_min"),
        "comp_max": role.get("comp_max"),
        "benchmark": benchmark,
        "corpus": comp_from_corpus,
        "competitive": _competitive_verdict(role, benchmark, comp_from_corpus),
    }

    # ── Competitors (companies hiring similar titles) ───────────────────────
    competitors: list[dict[str, Any]] = []
    if title:
        title_like = title.replace("%", "").replace("_", "").strip()
        comp_rows = await db.fetch(
            f"""
            SELECT c.name AS company_name, count(*) AS open_roles
            FROM public.jobs j
            JOIN public.companies c ON c.id = j.company_id
            WHERE {live}
              AND j.title ILIKE '%' || $1 || '%'
              AND c.name IS NOT NULL
            GROUP BY c.name
            ORDER BY open_roles DESC
            LIMIT 8
            """,
            title_like,
        )
        competitors = [
            {"company_name": r["company_name"], "open_roles": int(r["open_roles"])}
            for r in comp_rows
        ]

    total_similar = 0
    if title:
        total_similar = int(
            await db.fetchval(
                f"SELECT count(*) FROM public.jobs j WHERE {live} AND j.title ILIKE '%' || $1 || '%'",
                title.replace("%", "").replace("_", "").strip(),
            )
            or 0
        )

    # ── Skill gaps vs market ────────────────────────────────────────────────
    skill_gaps: list[dict[str, Any]] = []
    skills_in_demand: list[str] = []
    if skills:
        matched = await db.fetch(
            f"""
            SELECT lower(s) AS skill, count(*) AS n
            FROM public.jobs j
            CROSS JOIN LATERAL unnest(j.skills_required) AS s
            WHERE {live} AND lower(s) = ANY($1::text[])
            GROUP BY 1
            ORDER BY n DESC
            """,
            skills,
        )
        skills_in_demand = [r["skill"] for r in matched]

        missing = await db.fetch(
            f"""
            SELECT lower(s) AS skill, count(*) AS n
            FROM public.jobs j
            CROSS JOIN LATERAL unnest(j.skills_required) AS s
            WHERE {live}
              AND j.title ILIKE '%' || $2 || '%'
              AND NOT (lower(s) = ANY($1::text[]))
            GROUP BY 1
            ORDER BY n DESC
            LIMIT 10
            """,
            skills,
            title.replace("%", "").replace("_", "").strip() if title else "",
        )
        for r in missing:
            pct = round(100 * int(r["n"]) / max(total_similar, 1))
            skill_gaps.append(
                {
                    "skill": r["skill"],
                    "posting_count": int(r["n"]),
                    "pct_of_similar_roles": pct,
                    "message": f"{pct}% of similar roles list {r['skill']}; your brief does not",
                }
            )

    brief_gaps = [g for g in skill_gaps if g["pct_of_similar_roles"] >= 30][:5]

    return {
        "market": market,
        "role_title": title,
        "total_similar_roles": total_similar,
        "comp": role_comp,
        "competitors": competitors,
        "skills_in_demand": skills_in_demand,
        "skill_gaps": brief_gaps,
        "grounded": total_similar >= 8,
    }


def _competitive_verdict(
    role: dict[str, Any],
    benchmark: dict[str, Any] | None,
    corpus: dict[str, Any] | None,
) -> str:
    comp_min = role.get("comp_min")
    comp_max = role.get("comp_max")
    if comp_min is None and comp_max is None:
        if benchmark or corpus:
            return "missing_comp"
        return "unknown"
    ref_max = None
    if corpus and corpus.get("p50"):
        ref_max = corpus["p50"]
    elif benchmark and benchmark.get("market_max_inr"):
        ref_max = benchmark["market_max_inr"]
    if ref_max and comp_max and comp_max < ref_max * 0.85:
        return "below_market"
    if ref_max and comp_min and comp_min > ref_max * 1.15:
        return "above_market"
    return "competitive"
