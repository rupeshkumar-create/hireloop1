"""
Apify Google Jobs Scraper service.

Active actor:
  - johnvc/Google-Jobs-Scraper

India geo-lock replaced by per-market scoping (IN / US / GB).

Typical cost: ~$0.50 per 1,000 job listings = ~₹0.04/job.

Usage flow:
  1. Trigger actor run with search queries
  2. Poll for completion (async, up to 5 min)
  3. Fetch dataset items
  4. Normalise → JobRecord
  5. Upsert into public.jobs (dedup on apify_job_id)
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, ClassVar

import httpx
import structlog
from pydantic import BaseModel, field_validator

from hireloop_api.markets import (
    MARKET_SCRAPE_LOCATIONS,
    SUPPORTED_MARKETS,
    currency_for_market,
    resolve_country_from_location,
)

logger = structlog.get_logger()


# ── Data models ───────────────────────────────────────────────────────────────


class JobRecord(BaseModel):
    """Normalised job record ready to INSERT into public.jobs."""

    apify_job_id: str
    title: str
    description: str | None = None
    requirements: str | None = None
    company_name: str | None = None
    company_linkedin_url: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    country_code: str = "IN"
    salary_currency: str = "INR"
    allowed_regions: list[str] | None = None
    is_remote: bool = False
    employment_type: str = "full_time"
    seniority: str | None = None
    ctc_min: int | None = None
    ctc_max: int | None = None
    skills_required: list[str] = []
    apply_url: str | None = None
    source: str = "google_jobs"
    expires_at: datetime | None = None
    raw_data: dict = {}

    @field_validator("country_code")
    @classmethod
    def must_be_supported_market(cls, v: str) -> str:
        code = (v or "IN").upper().strip()
        if code not in SUPPORTED_MARKETS:
            raise ValueError(f"Unsupported market: {code}")
        return code

    @field_validator("employment_type")
    @classmethod
    def normalise_employment_type(cls, v: str) -> str:
        mapping = {
            "full-time": "full_time",
            "full_time": "full_time",
            "contract": "contract",
            "internship": "internship",
            "part-time": "part_time",
            "part_time": "part_time",
        }
        return mapping.get(v.lower().replace(" ", "_"), "full_time")

    @field_validator("seniority")
    @classmethod
    def normalise_seniority(cls, v: str | None) -> str | None:
        if not v:
            return None
        mapping = {
            "intern": "intern",
            "internship": "intern",
            "junior": "junior",
            "entry level": "junior",
            "associate": "junior",
            "mid": "mid",
            "mid-senior level": "mid",
            "mid-senior": "mid",
            "mid level": "mid",
            "senior": "senior",
            "lead": "lead",
            "director": "director",
            "vp": "vp",
            "vice president": "vp",
            "c_level": "c_level",
            "c-level": "c_level",
            "executive": "c_level",
        }
        return mapping.get(v.lower(), None)


# ── Apify client ──────────────────────────────────────────────────────────────

DEFAULT_GOOGLE_JOBS_ACTOR = "johnvc/Google-Jobs-Scraper"
DEFAULT_LINKEDIN_JOBS_ACTOR = DEFAULT_GOOGLE_JOBS_ACTOR
APIFY_API_BASE = "https://api.apify.com/v2"

# Back-compat alias — prefer MARKET_SCRAPE_LOCATIONS from markets.py
INDIA_LOCATIONS = MARKET_SCRAPE_LOCATIONS["IN"]

# Role categories to scrape — expand in P24 for programmatic SEO
SEARCH_QUERIES = [
    "Software Engineer",
    "Senior Software Engineer",
    "Product Manager",
    "Data Scientist",
    "Machine Learning Engineer",
    "DevOps Engineer",
    "Full Stack Developer",
    "Backend Engineer",
    "Frontend Engineer",
    "Engineering Manager",
    "Tech Lead",
    "SRE",
    "Android Developer",
    "iOS Developer",
    "Mobile Engineer",
]


class ApifyJobsScraper:
    def __init__(self, api_token: str, *, actor: str = DEFAULT_GOOGLE_JOBS_ACTOR) -> None:
        self._token = api_token
        self._actor = actor

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    @staticmethod
    def _actor_path(actor: str) -> str:
        """Apify API expects `username~actor-name` in URLs (store uses `username/actor-name`)."""
        return actor.replace("/", "~") if "/" in actor else actor

    @staticmethod
    def _coerce_market_location(loc: str, market: str) -> str:
        loc = (loc or "").strip()
        if not loc:
            return MARKET_SCRAPE_LOCATIONS.get(market, ["India"])[0]
        low = loc.lower()
        hints = {
            "IN": "india",
            "US": "united states",
            "GB": "united kingdom",
        }
        hint = hints.get(market, "")
        if hint and hint in low:
            return loc
        if market == "IN":
            return f"{loc}, India" if "india" not in low else loc
        if market == "US":
            return f"{loc}, United States" if "united states" not in low else loc
        if market == "GB":
            return f"{loc}, United Kingdom" if "united kingdom" not in low else loc
        return loc

    async def scrape(
        self,
        *,
        queries: list[str] | None = None,
        locations: list[str] | None = None,
        max_results_per_query: int = 25,
        time_range: str = "24h",
    ) -> tuple[list[dict[str, Any]], list[JobRecord], dict[str, Any]]:
        """
        Run the configured Google Jobs actor and return (raw_items, records, stats).

        johnvc/Google-Jobs-Scraper accepts one query/location per run, so we run
        bounded query x location pairs and concatenate the datasets.
        """
        q_list = (queries or SEARCH_QUERIES)[:10]
        loc_list = (locations or ["India"])[:5]
        rows = max(10, min(1000, max_results_per_query))

        run_ids: list[str] = []
        dataset_ids: list[str] = []
        all_items: list[dict[str, Any]] = []

        for q in q_list:
            for loc in loc_list:
                market = resolve_country_from_location(loc) or "IN"
                run_id = await self._trigger_run_google_jobs(
                    query=q,
                    location=self._coerce_market_location(loc, market),
                    max_results=rows,
                    country=self._google_country_code(market),
                )
                dataset_id = await self.wait_for_run(run_id)
                items = await self.fetch_dataset(dataset_id, limit=rows)
                run_ids.append(run_id)
                dataset_ids.append(dataset_id)
                all_items.extend(items)

        records = self.normalise_batch(all_items)
        stats = {
            "actor": self._actor,
            "run_id": run_ids[0] if run_ids else None,
            "dataset_id": dataset_ids[0] if dataset_ids else None,
            "run_ids": run_ids,
            "dataset_ids": dataset_ids,
            "raw_items": len(all_items),
            "normalised": len(records),
        }
        return all_items, records, stats

    @staticmethod
    def _build_google_jobs_input(
        *,
        query: str,
        location: str | None,
        max_results: int,
        country: str = "in",
    ) -> dict[str, Any]:
        return {
            "query": query,
            "location": location or "",
            "country": country or "None",
            "language": "None",
            "google_domain": "google.com",
            "num_results": max(10, min(int(max_results), 1000)),
            "max_pagination": 0,
            "include_lrad": False,
            "lrad_value": "",
            "max_delay": 1,
            "output_file": "",
            "cleanup_results": True,
        }

    @staticmethod
    def _google_country_code(market: str) -> str:
        """Map internal ISO-ish market codes to johnvc/Google-Jobs-Scraper country values."""
        return {"IN": "in", "US": "us", "GB": "uk"}.get(market.upper(), "None")

    async def _trigger_run_google_jobs(
        self, *, query: str, location: str | None, max_results: int, country: str
    ) -> str:
        """Trigger johnvc/Google-Jobs-Scraper for one query/location pair."""
        input_data = self._build_google_jobs_input(
            query=query,
            location=location,
            max_results=max_results,
            country=country,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{APIFY_API_BASE}/acts/{self._actor_path(self._actor)}/runs",
                headers=self._headers(),
                json=input_data,
            )

        if resp.status_code not in (200, 201):
            logger.error("apify_run_trigger_failed", status=resp.status_code, body=resp.text[:200])
            raise RuntimeError(f"Apify run trigger failed: {resp.status_code}")

        run_id = resp.json()["data"]["id"]
        logger.info(
            "apify_google_jobs_run_triggered",
            run_id=run_id,
            query=query,
            location=location,
            max_results=max_results,
        )
        return run_id

    async def wait_for_run(self, run_id: str, poll_interval: int = 10, max_wait: int = 600) -> str:
        """
        Poll until run completes. Returns dataset_id.
        Raises on timeout or failure.
        """
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
                logger.info("apify_run_succeeded", run_id=run_id, dataset_id=dataset_id)
                return dataset_id
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Apify run {run_id} ended with status: {status}")

            logger.debug("apify_run_waiting", run_id=run_id, status=status, elapsed=elapsed)
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Apify run {run_id} did not complete within {max_wait}s")

    async def fetch_dataset(self, dataset_id: str, limit: int = 5000) -> list[dict[str, Any]]:
        """Fetch raw items from an Apify dataset."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{APIFY_API_BASE}/datasets/{dataset_id}/items",
                headers=self._headers(),
                params={"limit": limit, "format": "json", "clean": True},
            )

        if resp.status_code != 200:
            raise RuntimeError(f"Dataset fetch failed: {resp.status_code}")

        items = resp.json()
        logger.info("apify_dataset_fetched", dataset_id=dataset_id, count=len(items))
        return items

    # ── Normalisation ──────────────────────────────────────────────────────────

    def normalise(self, raw: dict[str, Any]) -> JobRecord | None:
        """
        Map one johnvc/Google-Jobs-Scraper item → JobRecord.
        Returns None if market cannot be resolved or required fields are missing.
        """
        title = (
            raw.get("title") or raw.get("jobTitle") or raw.get("position") or raw.get("role") or ""
        )
        title = str(title).strip()
        if not title:
            return None

        location_raw = (
            raw.get("location")
            or raw.get("jobLocation")
            or raw.get("locationText")
            or raw.get("job_location")
            or ""
        )
        location_raw = str(location_raw).strip()
        country_raw = str(raw.get("country") or raw.get("country_code") or "").strip()
        market = self._resolve_market(location_raw, title, country_raw)
        if not market:
            return None

        city, state = self._parse_location(location_raw, market)

        # Build a stable dedup key from Google job id, apply URL, or share link.
        apply_options = raw.get("apply_options") or raw.get("applyOptions") or []
        apply_url_from_options = None
        if isinstance(apply_options, list):
            for opt in apply_options:
                if isinstance(opt, dict) and opt.get("link"):
                    apply_url_from_options = str(opt["link"])
                    break
        job_url = (
            apply_url_from_options
            or raw.get("jobUrl")
            or raw.get("applyUrl")
            or raw.get("apply_url")
            or raw.get("job_url")
            or raw.get("url")
            or raw.get("share_link")
            or raw.get("link")
            or ""
        )
        job_url = str(job_url)
        stable_id = (
            raw.get("job_id")
            or raw.get("jobId")
            or raw.get("id")
            or self._extract_job_id(job_url)
        )
        apify_job_id = f"gj_{stable_id}" if stable_id else f"gj_{uuid.uuid4()}"

        # Parse salary from description if available
        ctc_min, ctc_max = self._parse_salary(
            raw.get("salary") or raw.get("descriptionText") or raw.get("description") or ""
        )

        # Skills extraction from description
        skills = self._extract_skills(
            " ".join(
                filter(
                    None,
                    [
                        raw.get("descriptionText") or raw.get("description"),
                        raw.get("requirements"),
                        title,
                    ],
                )
            )
        )

        # Employment type
        emp_type = (
            raw.get("employmentType")
            or raw.get("contractType")
            or raw.get("jobType")
            or raw.get("employment_type")
            or (raw.get("detected_extensions") or {}).get("schedule_type")
            or "full_time"
        )

        # Seniority
        seniority_raw = (
            raw.get("seniorityLevel")
            or raw.get("experienceLevel")
            or raw.get("seniority")
            or raw.get("experience_level")
            or ""
        )

        is_remote = "remote" in location_raw.lower() or "remote" in title.lower()
        allowed_regions = ["WORLD"] if is_remote else None

        try:
            return JobRecord(
                apify_job_id=apify_job_id,
                title=title,
                description=raw.get("descriptionText") or raw.get("description"),
                requirements=raw.get("requirements"),
                company_name=(
                    raw.get("companyName") or raw.get("company_name") or raw.get("company")
                ),
                company_linkedin_url=(
                    raw.get("companyUrl") or raw.get("companyLinkedinUrl") or raw.get("company_url")
                ),
                location_city=city,
                location_state=state,
                country_code=market,
                salary_currency=currency_for_market(market),
                allowed_regions=allowed_regions,
                is_remote=is_remote,
                employment_type=emp_type,
                seniority=seniority_raw or None,
                ctc_min=ctc_min,
                ctc_max=ctc_max,
                skills_required=skills,
                apply_url=(job_url or None),
                source="google_jobs",
                raw_data={k: v for k, v in raw.items() if k not in ("description",)},
            )
        except Exception as exc:
            logger.warning("job_normalise_failed", error=str(exc), title=title)
            return None

    def normalise_batch(self, items: list[dict[str, Any]]) -> list[JobRecord]:
        """Normalise a batch of raw Apify items, skipping unsupported markets."""
        results = []
        skipped = 0
        for item in items:
            record = self.normalise(item)
            if record:
                results.append(record)
            else:
                skipped += 1
        logger.info("normalise_batch_done", total=len(items), kept=len(results), skipped=skipped)
        return results

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_market(location_raw: str, title: str, country_raw: str = "") -> str | None:
        country_map = {
            "in": "IN",
            "india": "IN",
            "us": "US",
            "usa": "US",
            "united states": "US",
            "uk": "GB",
            "gb": "GB",
            "united kingdom": "GB",
        }
        country_market = country_map.get(country_raw.lower())
        market = (
            country_market
            or resolve_country_from_location(location_raw)
            or resolve_country_from_location(title)
        )
        if market and market in SUPPORTED_MARKETS:
            return market
        return None

    @staticmethod
    def _parse_location(loc: str, market: str) -> tuple[str | None, str | None]:
        if market == "IN":
            return ApifyJobsScraper._parse_india_location(loc)
        parts = [p.strip() for p in loc.split(",")]
        city = parts[0] if parts else None
        state = parts[1] if len(parts) > 1 else None
        return city, state

    @staticmethod
    def _parse_india_location(loc: str) -> tuple[str | None, str | None]:
        """Extract city and state from a location string."""
        city_to_state = {
            "bengaluru": "Karnataka",
            "bangalore": "Karnataka",
            "mumbai": "Maharashtra",
            "pune": "Maharashtra",
            "hyderabad": "Telangana",
            "secunderabad": "Telangana",
            "delhi": "Delhi",
            "new delhi": "Delhi",
            "gurugram": "Haryana",
            "gurgaon": "Haryana",
            "noida": "Uttar Pradesh",
            "chennai": "Tamil Nadu",
            "kolkata": "West Bengal",
            "ahmedabad": "Gujarat",
            "surat": "Gujarat",
            "jaipur": "Rajasthan",
            "kochi": "Kerala",
            "thiruvananthapuram": "Kerala",
            "chandigarh": "Punjab",
            "indore": "Madhya Pradesh",
        }
        parts = [p.strip() for p in loc.split(",")]
        city = parts[0] if parts else None
        if city:
            state = city_to_state.get(city.lower())
            return city, state
        return None, None

    @staticmethod
    def _extract_job_id(url: str) -> str | None:
        """Extract a stable job id from known job URL formats for deduplication."""
        match = re.search(r"/jobs/view/(\d+)", url)
        if match:
            return f"li_{match.group(1)}"
        match = re.search(r"currentJobId=(\d+)", url)
        if match:
            return f"li_{match.group(1)}"
        match = re.search(r"/job/([^/?#]+)", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _parse_salary(text: str) -> tuple[int | None, int | None]:
        """
        Extract salary range from text. Returns (min_inr_pa, max_inr_pa).
        Handles: "₹20-30 LPA", "20L-30L", "20,00,000 - 30,00,000"
        """
        if not text:
            return None, None

        # LPA pattern: "20-30 LPA" or "20L to 30L"
        lpa_match = re.search(
            r"(?:₹\s*)?(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*(?:LPA|L\b|lakh|lac)",
            text,
            re.IGNORECASE,
        )
        if lpa_match:
            min_l = float(lpa_match.group(1))
            max_l = float(lpa_match.group(2))
            return int(min_l * 100_000), int(max_l * 100_000)

        return None, None

    # Comprehensive skill keywords for Indian tech market
    SKILL_KEYWORDS: ClassVar[set[str]] = {
        "python",
        "java",
        "javascript",
        "typescript",
        "golang",
        "go",
        "rust",
        "c++",
        "c#",
        "ruby",
        "scala",
        "kotlin",
        "swift",
        "r",
        "react",
        "nextjs",
        "next.js",
        "angular",
        "vue",
        "nodejs",
        "node.js",
        "django",
        "fastapi",
        "flask",
        "spring",
        "spring boot",
        "rails",
        "postgres",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "elasticsearch",
        "aws",
        "gcp",
        "azure",
        "kubernetes",
        "docker",
        "terraform",
        "machine learning",
        "deep learning",
        "nlp",
        "llm",
        "pytorch",
        "tensorflow",
        "sql",
        "spark",
        "hadoop",
        "kafka",
        "airflow",
        "product management",
        "agile",
        "scrum",
        "jira",
        "figma",
        "sketch",
        "ios",
        "android",
        "react native",
        "flutter",
        "ci/cd",
        "devops",
        "sre",
        "linux",
        "data science",
        "data engineering",
        "analytics",
        "tableau",
        "power bi",
        "customer success",
        "customer support",
        "client success",
        "relationship management",
        "communication",
        "renewals",
        "operations",
        "merchandising",
        "fashion buying",
        "retail planning",
        "category management",
        "recruitment",
        "talent acquisition",
        "payroll",
        "employee relations",
        "finance",
        "accounting",
        "digital marketing",
        "seo",
        "social media",
        "sales",
        "business development",
    }

    def _extract_skills(self, text: str) -> list[str]:
        text_lower = text.lower()
        found = []
        for skill in self.SKILL_KEYWORDS:
            # Word-boundary match
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, text_lower):
                found.append(skill)
        return sorted(set(found))
