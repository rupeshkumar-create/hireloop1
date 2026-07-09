"""
Coarse India salary band lookup for match cards (city × role × seniority).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "india_salary_bands.json"


@lru_cache(maxsize=1)
def _load_bands() -> dict[str, Any]:
    try:
        return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except OSError:
        return {"bands": [], "currency": "INR", "unit": "LPA"}


def _norm_city(city: str | None) -> str:
    c = (city or "").strip().lower()
    if not c:
        return "default"
    if "bangalore" in c or "bengaluru" in c:
        return "bengaluru"
    if "mumbai" in c or "bombay" in c:
        return "mumbai"
    if "delhi" in c or "ncr" in c or "gurgaon" in c or "gurugram" in c or "noida" in c:
        return "delhi"
    if "hyderabad" in c:
        return "hyderabad"
    if "pune" in c:
        return "pune"
    return c.split(",")[0].strip() or "default"


def _role_keywords(title: str | None) -> list[str]:
    t = (title or "").lower()
    if any(k in t for k in ("customer success", "csm", "client success")):
        return ["customer success", "csm"]
    if any(k in t for k in ("software", "engineer", "developer", "sde")):
        return ["software", "engineer", "developer"]
    if "operations" in t:
        return ["operations", "manager"]
    if any(k in t for k in ("manager", "lead", "head")):
        return ["manager", "lead"]
    return ["default"]


def lookup_salary_benchmark(
    job_row: Mapping[str, Any],
    cand_row: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return market band + comparison to job CTC when possible."""
    data = _load_bands()
    bands = data.get("bands") or []
    if not bands:
        return None

    city = _norm_city(job_row.get("location_city"))
    seniority = str(job_row.get("seniority") or "mid").lower()
    keywords = _role_keywords(str(job_row.get("title") or ""))

    match_band = None
    for band in bands:
        if band.get("seniority") != seniority:
            continue
        band_city = band.get("city") or "default"
        if band_city not in (city, "default"):
            continue
        band_kw = band.get("role_keywords") or []
        if any(k in keywords for k in band_kw) or "default" in band_kw:
            match_band = band
            if band_city == city:
                break

    if not match_band:
        return None

    job_min = job_row.get("ctc_min")
    job_max = job_row.get("ctc_max")
    median = match_band.get("median")
    result: dict[str, Any] = {
        "currency": data.get("currency", "INR"),
        "unit": data.get("unit", "LPA"),
        "market_min": match_band.get("min"),
        "market_max": match_band.get("max"),
        "market_median": median,
        "city": city,
        "seniority": seniority,
    }

    if job_min is not None and median:
        try:
            jm = float(job_min)
            med = float(median)
            if med > 0:
                pct = round((jm / med - 1.0) * 100)
                if pct >= 10:
                    result["vs_market"] = "above_market"
                    result["vs_market_label"] = f"~{pct}% above typical band"
                elif pct <= -10:
                    result["vs_market"] = "below_market"
                    result["vs_market_label"] = f"~{abs(pct)}% below typical band"
                else:
                    result["vs_market"] = "in_band"
                    result["vs_market_label"] = "Within typical market band"
        except (TypeError, ValueError):
            pass

    if job_max is not None:
        result["job_ctc_max"] = job_max
    if job_min is not None:
        result["job_ctc_min"] = job_min

    cand_min = (cand_row or {}).get("expected_ctc_min")
    if cand_min is not None and median:
        try:
            if float(cand_min) > float(median) * 1.15:
                result["candidate_expectation"] = "above_market"
        except (TypeError, ValueError):
            pass

    return result
