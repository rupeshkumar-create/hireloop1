"""
Health-check endpoints.

GET /api/v1/health        — liveness: 200 while the process is alive (ECS/uptime probes).
GET /api/v1/health/ready  — readiness: 200 only when dependencies (DB) are reachable; 503 otherwise.
No auth required (explicitly whitelisted in middleware).
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hireloop_api.config import Settings, get_settings
from hireloop_api.deps import get_db_pool

logger = structlog.get_logger()
router = APIRouter(tags=["ops"])

_START_TIME = time.time()


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    uptime_seconds: float
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness: 200 as long as the API process is alive."""
    return HealthResponse(
        status="ok",
        service="hireloop-api",
        environment=settings.environment,
        uptime_seconds=round(time.time() - _START_TIME, 2),
        timestamp=datetime.now(UTC).isoformat(),
    )


def build_readiness(checks: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """Pure: map dependency checks → (HTTP status, body). Ready only if all 'ok'."""
    ready = all(v == "ok" for v in checks.values())
    return (
        200 if ready else 503,
        {
            "status": "ready" if ready else "degraded",
            "service": "hireloop-api",
            "checks": checks,
            "uptime_seconds": round(time.time() - _START_TIME, 2),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )


@router.get("/health/ready")
async def readiness_check(settings: Settings = Depends(get_settings)) -> JSONResponse:
    """Readiness: verifies DB connectivity. Returns 503 (not 200) when a dependency is
    down, so load balancers stop routing to an unhealthy instance."""
    checks: dict[str, str] = {"database": "ok"}
    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as exc:
        checks["database"] = "error"
        logger.warning("readiness_db_check_failed", error=str(exc)[:200])

    status_code, body = build_readiness(checks)
    return JSONResponse(status_code=status_code, content=body)


async def _check_db(settings: Settings) -> str:
    try:
        pool = await get_db_pool(settings)
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return "ok"
    except Exception as exc:
        logger.warning("deep_health_db_failed", error=str(exc)[:200])
        return "error"


async def _check_url(name: str, url: str, token: str | None) -> str:
    """Cheap GET auth-probe of an external dependency. 'not_configured' when no
    token; 'ok' on 2xx; 'unavailable' otherwise. Never raises."""
    if not token:
        return "not_configured"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        return "ok" if resp.status_code == 200 else "unavailable"
    except Exception as exc:
        logger.warning("deep_health_dep_failed", dep=name, error=str(exc)[:200])
        return "unavailable"


@router.get("/health/deep")
async def deep_health(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Ops-only deep check: reports DB + Apify + OpenRouter reachability.

    Requires X-Service-Secret (same as other privileged ops endpoints). Unlike
    /health/ready this does NOT 503 on an external-dependency outage — it returns
    200 with per-dependency status so a dashboard can alert.
    """
    import hmac

    secret = request.headers.get("X-Service-Secret", "")
    expected = settings.service_secret or ""
    if not expected or not hmac.compare_digest(secret, expected):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    db, apify, openrouter = await asyncio.gather(
        _check_db(settings),
        _check_url("apify", "https://api.apify.com/v2/users/me", settings.apify_token),
        _check_url("openrouter", "https://openrouter.ai/api/v1/key", settings.openrouter_api_key),
    )
    checks = {"database": db, "apify": apify, "openrouter": openrouter}
    # Only a DB failure is "unhealthy" for serving; external deps are informational.
    status_code = 200 if db == "ok" else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "degraded",
            "service": "hireloop-api",
            "checks": checks,
            "uptime_seconds": round(time.time() - _START_TIME, 2),
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
