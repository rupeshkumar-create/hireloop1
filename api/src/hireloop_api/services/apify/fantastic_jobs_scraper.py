"""
Fantastic.jobs Career Site Job Listing API scraper (via Apify).

Actor: fantastic-jobs/career-site-job-listing-api

We use this as a second ingestion source alongside LinkedIn jobs. Input is
scoped to India (locationSearch includes "India") and we hard-filter derived
countries to ensure we never write non-IN jobs (R4 geo-lock).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import httpx
import structlog

from hireloop_api.services.apify.jobs_scraper import JobRecord

logger = structlog.get_logger()

APIFY_API_BASE = "https://api.apify.com/v2"


def _pick(raw: dict[str, Any], *keys: str) -> Any:  # noqa: ANN401 — raw API values are genuinely dynamic
    """Return the first present key (supports 2026 field renames + legacy fallbacks)."""
    for key in keys:
        val = raw.get(key)
        if val is not None and val != "":
            return val
    return None


def _actor_path(actor: str) -> str:
    """Apify API expects `username~actor-name` in URLs (store uses `username/actor-name`)."""
    return actor.replace("/", "~") if "/" in actor else actor


class ApifyFantasticJobsScraper:
    def __init__(self, api_token: str, *, actor: str) -> None:
        self._token = api_token
        self._actor = actor

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def trigger_run(
        self,
        *,
        title_search: list[str] | None,
        locations: list[str] | None,
        limit: int,
        time_range: str = "24h",
    ) -> str:
        """
        Trigger Fantastic.jobs job listing run and return Apify run_id.
        """
        # Input schema reference:
        # https://apify.com/fantastic-jobs/career-site-job-listing-api/input-schema
        input_data: dict[str, Any] = {
            "timeRange": time_range,
            "limit": max(10, min(limit, 5000)),
            "includeLinkedIn": True,
            "includeCompanyDetails": True,
            "descriptionType": "text",
            "descriptionFormat": "text",
            "removeAgency": True,
            "locationSearch": locations or ["India"],
        }
        if title_search:
            input_data["titleSearch"] = title_search

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{APIFY_API_BASE}/acts/{_actor_path(self._actor)}/runs",
                headers=self._headers(),
                json=input_data,
            )

        if resp.status_code not in (200, 201):
            logger.error(
                "apify_fantastic_trigger_failed",
                status=resp.status_code,
                body=resp.text[:200],
            )
            raise RuntimeError(f"Apify run trigger failed: {resp.status_code}")

        run_id = resp.json()["data"]["id"]
        logger.info("apify_fantastic_run_triggered", run_id=run_id)
        return run_id

    async def wait_for_run(self, run_id: str, poll_interval: int = 10, max_wait: int = 600) -> str:
        """Poll until run completes. Returns dataset_id."""
        import asyncio

        elapsed = 0
        while elapsed < max_wait:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{APIFY_API_BASE}/actor-runs/{run_id}",
                    headers=self._headers(),
                )
            data = resp.json()["data"]
            status = data["status"]

            if status == "SUCCEEDED":
                dataset_id = data["defaultDatasetId"]
                logger.info("apify_fantastic_run_succeeded", run_id=run_id, dataset_id=dataset_id)
                return dataset_id
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Apify run {run_id} ended with status: {status}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Apify run {run_id} did not complete within {max_wait}s")

    async def fetch_dataset(self, dataset_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{APIFY_API_BASE}/datasets/{dataset_id}/items",
                headers=self._headers(),
                params={"limit": limit, "format": "json", "clean": True},
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Dataset fetch failed: {resp.status_code}")
        items = resp.json()
        logger.info("apify_fantastic_dataset_fetched", dataset_id=dataset_id, count=len(items))
        return items

    def normalise_batch(self, items: list[dict[str, Any]]) -> list[JobRecord]:
        results: list[JobRecord] = []
        skipped = 0
        for item in items:
            rec = self.normalise(item)
            if rec is None:
                skipped += 1
                continue
            results.append(rec)
        logger.info(
            "fantastic_normalise_done",
            total=len(items),
            kept=len(results),
            skipped=skipped,
        )
        return results

    def normalise(self, raw: dict[str, Any]) -> JobRecord | None:
        title = (raw.get("title") or "").strip()
        if not title:
            return None

        # India geo-lock (R4): filter derived countries first, then location objects.
        countries = [str(c).lower() for c in (raw.get("countries_derived") or [])]
        if countries:
            if not any(c in ("india", "in") for c in countries):
                return None

        locations = raw.get("locations_derived") or []
        city = state = None
        if isinstance(locations, list) and locations:
            first = locations[0] or {}
            if isinstance(first, dict):
                country = first.get("country")
                if country:
                    if str(country).lower() not in ("india", "in"):
                        return None
                city = first.get("city")
                state = first.get("admin") or first.get("region")

        # Hard enforce India-only: if neither derived countries nor a location country
        # is present, skip to avoid accidentally storing non-IN jobs.
        if not countries:
            first_loc = locations[0] if isinstance(locations, list) and locations else None
            if not (isinstance(first_loc, dict) and first_loc.get("country")):
                return None

        # Remote detection (remote_derived removed 2026-06 — use ai_work_arrangement)
        work_arrangement = str(_pick(raw, "ai_work_arrangement") or "").lower()
        is_remote = (
            work_arrangement in ("remote solely", "remote ok", "remote")
            or raw.get("location_type") == "TELECOMMUTE"
        ) and "hybrid" not in work_arrangement

        # Employment type: prefer AI-derived enum, fall back to source array
        employment_type = "full_time"
        ai_emp = str(_pick(raw, "ai_employment_type") or "").upper()
        emp_map = {
            "FULL_TIME": "full_time",
            "PART_TIME": "part_time",
            "CONTRACTOR": "contract",
            "TEMPORARY": "contract",
            "INTERN": "internship",
        }
        if ai_emp in emp_map:
            employment_type = emp_map[ai_emp]
        else:
            et = raw.get("employment_type") or []
            if isinstance(et, list) and et:
                et0 = str(et[0]).lower()
                if "intern" in et0:
                    employment_type = "internship"
                elif "part" in et0:
                    employment_type = "part_time"
                elif "contract" in et0:
                    employment_type = "contract"

        # Salary: new snake_case AI fields with legacy aliases
        ctc_min = _pick(raw, "ai_salary_min_value", "ai_salary_minvalue")
        ctc_max = _pick(raw, "ai_salary_max_value", "ai_salary_maxvalue")
        ctc_val = raw.get("ai_salary_value")
        currency = str(_pick(raw, "ai_salary_currency") or "").lower()
        unit = str(_pick(raw, "ai_salary_unit_text", "ai_salary_unittext") or "").lower()

        def _as_int(v: str | int | float | None) -> int | None:
            try:
                if v is None:
                    return None
                return int(float(v))
            except Exception:
                return None

        ctc_min_i = _as_int(ctc_min)
        ctc_max_i = _as_int(ctc_max)
        if ctc_min_i is None and ctc_max_i is None:
            v = _as_int(ctc_val)
            if v is not None:
                ctc_min_i = v
                ctc_max_i = v

        # Only keep salary when it looks like INR per year (avoid incorrect mappings)
        if currency and currency not in ("inr", "₹"):
            ctc_min_i = None
            ctc_max_i = None
        if unit and unit not in ("year", "yr", "annual", "annum"):
            ctc_min_i = None
            ctc_max_i = None

        # Skills: use ai_key_skills when available; otherwise extract heuristically.
        skills: list[str] = []
        ai_skills = raw.get("ai_key_skills")
        if isinstance(ai_skills, list):
            skills = [str(s).lower().strip() for s in ai_skills if str(s).strip()]
        if not skills:
            skills = self._extract_skills(
                " ".join(filter(None, [raw.get("description_text"), title]))
            )

        job_url = raw.get("url") or None
        internal_id = raw.get("id")
        if internal_id:
            apify_job_id = f"fj_{internal_id}"
        elif job_url:
            apify_job_id = f"fj_{self._stable_id(job_url)}"
        else:
            return None

        company_name = raw.get("organization") or None
        company_linkedin_url = _pick(
            raw,
            "org_linkedin_url",
            "linkedin_org_url",
            "organization_url",
        )

        expires_at = None
        raw_exp = _pick(raw, "date_valid_through", "date_validthrough")
        if raw_exp:
            try:
                expires_at = datetime.fromisoformat(str(raw_exp).replace("Z", "+00:00")).astimezone(
                    UTC
                )
            except Exception:
                expires_at = None
        if expires_at is None:
            expires_at = datetime.now(UTC) + timedelta(days=30)

        return JobRecord(
            apify_job_id=apify_job_id,
            title=title,
            description=raw.get("description_text") or raw.get("ai_core_responsibilities") or None,
            requirements=raw.get("ai_requirements_summary") or None,
            company_name=company_name,
            company_linkedin_url=company_linkedin_url,
            location_city=city,
            location_state=state,
            country_code="IN",
            is_remote=is_remote,
            employment_type=employment_type,
            seniority=None,
            ctc_min=ctc_min_i,
            ctc_max=ctc_max_i,
            skills_required=sorted(set(skills)),
            apply_url=job_url,
            source="apify",
            expires_at=expires_at,
            raw_data=raw,
        )

    @staticmethod
    def _stable_id(url: str | None) -> str:
        if not url:
            return ""
        safe = re.sub(r"[^a-zA-Z0-9]+", "_", url.strip().lower())
        return safe[:120]

    # Very small keyword set (fallback only; AI skills are preferred)
    _SKILLS: ClassVar[set[str]] = {
        "python",
        "java",
        "javascript",
        "typescript",
        "golang",
        "go",
        "react",
        "next.js",
        "nextjs",
        "node.js",
        "nodejs",
        "django",
        "fastapi",
        "postgres",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "aws",
        "gcp",
        "azure",
        "kubernetes",
        "docker",
        "terraform",
        "sql",
        "spark",
        "kafka",
        "airflow",
        "product management",
        "data science",
        "machine learning",
        "devops",
        "sre",
    }

    def _extract_skills(self, text: str) -> list[str]:
        if not text:
            return []
        text_lower = text.lower()
        found: list[str] = []
        for skill in self._SKILLS:
            if re.search(r"\b" + re.escape(skill) + r"\b", text_lower):
                found.append(skill)
        return sorted(set(found))
