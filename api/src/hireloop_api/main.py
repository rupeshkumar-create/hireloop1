"""
Hireloop API — FastAPI application entry point.

Architecture:
  - FastAPI with async handlers throughout (asyncpg, httpx)
  - Pydantic v2 for all data models
  - LangGraph for agent state management (Aarya + Nitya)
  - Structured logging via structlog
  - CORS restricted to allowed origins (India app only)

Run locally:
  uvicorn hireloop_api.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hireloop_api.agents.nitya.agent import NityaWorker
from hireloop_api.config import get_settings
from hireloop_api.rate_limit import rate_limit_middleware
from hireloop_api.routes.admin import router as admin_router
from hireloop_api.routes.application_kits import router as application_kits_router
from hireloop_api.routes.auth import router as auth_router
from hireloop_api.routes.career import router as career_router
from hireloop_api.routes.chat import router as chat_router
from hireloop_api.routes.gmail import router as gmail_router
from hireloop_api.routes.health import router as health_router
from hireloop_api.routes.hiring_managers import router as hiring_managers_router
from hireloop_api.routes.intros import router as intros_router
from hireloop_api.routes.jobs import router as jobs_router
from hireloop_api.routes.learning_roadmaps import router as learning_roadmaps_router
from hireloop_api.routes.matches import router as matches_router
from hireloop_api.routes.me import router as me_router
from hireloop_api.routes.mock_interview import router as mock_interview_router
from hireloop_api.routes.recruiter import router as recruiter_router
from hireloop_api.routes.resumes import router as resumes_router
from hireloop_api.routes.skills import router as skills_router
from hireloop_api.routes.super_admin import router as super_admin_router
from hireloop_api.routes.tailored_resumes import router as tailored_resumes_router
from hireloop_api.routes.voice import router as voice_router
from hireloop_api.routes.voice_sessions import router as voice_sessions_router
from hireloop_api.routes.whatsapp_routes import router as whatsapp_router

# ── Structured logging setup ──────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger()

# ── Settings ──────────────────────────────────────────────────────────────────
settings = get_settings()

# ── Error tracking (Sentry) ───────────────────────────────────────────────────
# No-op unless SENTRY_DSN is configured. PII is never sent (DPDP Act 2023).
if settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    logger.info("sentry_initialised", environment=settings.environment)

# ── Nitya worker (background LISTEN/NOTIFY) ───────────────────────────────────
_nitya_worker: NityaWorker | None = None
_nitya_task: asyncio.Task | None = None  # type: ignore[type-arg]
_bg_worker_stop: asyncio.Event | None = None
_bg_worker_task: asyncio.Task | None = None  # type: ignore[type-arg]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: launch Nitya + background job workers. Shutdown: stop cleanly."""
    global _nitya_worker, _nitya_task, _bg_worker_stop, _bg_worker_task
    cfg = get_settings()

    if cfg.database_url:
        # Convert SQLAlchemy-style DSN to asyncpg-style for LISTEN
        dsn = cfg.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _nitya_worker = NityaWorker(settings=cfg, db_dsn=dsn)
        _nitya_task = asyncio.create_task(_nitya_worker.start())
        logger.info("nitya_worker_started")

    if cfg.database_url and cfg.background_worker_enabled:
        from hireloop_api.services.background_jobs import run_background_worker

        _bg_worker_stop = asyncio.Event()
        _bg_worker_task = asyncio.create_task(
            run_background_worker(
                cfg,
                _bg_worker_stop,
                poll_seconds=cfg.background_worker_poll_seconds,
            )
        )
        logger.info("background_worker_scheduled")

    yield  # application runs here

    if _bg_worker_stop is not None:
        _bg_worker_stop.set()
    if _bg_worker_task and not _bg_worker_task.done():
        _bg_worker_task.cancel()
        try:
            await _bg_worker_task
        except asyncio.CancelledError:
            pass

    if _nitya_worker:
        _nitya_worker.stop()
    if _nitya_task and not _nitya_task.done():
        _nitya_task.cancel()
        try:
            await _nitya_task
        except asyncio.CancelledError:
            pass
    logger.info("background_workers_stopped")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Hireloop API",
    description="AI recruiting platform for India — Aarya (candidate) + Nitya (recruiter)",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # Wildcard headers is safe here because allow_origins is explicit (not "*").
    # This prevents preflight failures when browsers include extra headers like
    # Accept, Accept-Encoding, or any future custom headers.
    allow_headers=["*"],
)


# ── Security headers ────────────────────────────────────────────────────────────
# Conservative, universally-safe headers on every response. Deliberately omits a
# Content-Security-Policy (needs per-surface tuning) and any Permissions-Policy
# that would disable the mic/camera the voice features rely on.
@app.middleware("http")
async def _security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ── Request timing / slow-request logging ───────────────────────────────────────
# Measures every request and logs the slow ones (p95-hunting). Adds a Server-Timing
# header so latency is visible in the browser network panel too. Cheap: one clock
# read per request.
_SLOW_REQUEST_MS = 1000.0


@app.middleware("http")
async def _request_timing(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.0f}"
    if elapsed_ms >= _SLOW_REQUEST_MS and request.url.path != "/api/v1/health":
        logger.warning(
            "slow_request",
            method=request.method,
            path=request.url.path,
            duration_ms=round(elapsed_ms),
            status_code=response.status_code,
        )
    return response


# ── Rate limiting ───────────────────────────────────────────────────────────────
# In-process per-IP flood protection (health-exempt, auth tightened). See
# rate_limit.py for semantics/limits.
app.middleware("http")(rate_limit_middleware)


# ── Routers ───────────────────────────────────────────────────────────────────
# P01: health
app.include_router(health_router, prefix="/api/v1")

# P04: auth (LinkedIn OAuth callback + MSG91 SMS OTP)
app.include_router(auth_router, prefix="/api/v1")

# P06: resume upload + parsing
app.include_router(resumes_router, prefix="/api/v1")

# P07: voice session booking (in-house, Google Calendar)
app.include_router(voice_sessions_router, prefix="/api/v1")

# P08: Aarya chat (SSE streaming)
app.include_router(chat_router, prefix="/api/v1")

# P09: Job ingestion (Apify) + public job listing
app.include_router(jobs_router, prefix="/api/v1")

# P10: Embeddings + match feed
app.include_router(matches_router, prefix="/api/v1")

app.include_router(skills_router, prefix="/api/v1")

# Career path → job discovery (profile → AI path → Apify-backed jobs)
app.include_router(career_router, prefix="/api/v1")

# P12: HM enrichment (Apify waterfall)
app.include_router(hiring_managers_router, prefix="/api/v1")

# P13: Gmail OAuth + SendGrid transactional
app.include_router(gmail_router, prefix="/api/v1")

# P14: Intro handshake (candidate view + cancel)
app.include_router(intros_router, prefix="/api/v1")

# P15: Voice STT/TTS (Deepgram)
app.include_router(voice_router, prefix="/api/v1")

# P16-P18: Recruiter / Nitya
app.include_router(recruiter_router, prefix="/api/v1")

# P19: WhatsApp webhooks (MSG91)
app.include_router(whatsapp_router, prefix="/api/v1")

# P19 + P23: User prefs, DPDP export/delete
app.include_router(me_router, prefix="/api/v1")
app.include_router(application_kits_router, prefix="/api/v1")

# P20: Tailored resumes
app.include_router(tailored_resumes_router, prefix="/api/v1")
# Learning roadmaps (per-job AI upskilling plan)
app.include_router(learning_roadmaps_router, prefix="/api/v1")

# P21: Mock interviews
app.include_router(mock_interview_router, prefix="/api/v1")

# P23: Admin panel API
app.include_router(admin_router, prefix="/api/v1")

# P23: Super admin (internal user management)
app.include_router(super_admin_router, prefix="/api/v1")


# ── Global exception handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    In development: expose the real exception type + message + a hint at the
    failing module so the engineer can debug from the browser without tailing
    uvicorn stderr. In production: opaque "Internal server error" + the log
    line carries the full traceback for ops.
    """
    import traceback as _tb

    exc_type = type(exc).__name__
    exc_msg = str(exc) or repr(exc)

    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error_type=exc_type,
        error=exc_msg,
        exc_info=True,
    )

    if settings.is_development:
        # Last frame from app code, useful when the user reports "server error"
        tb = _tb.extract_tb(exc.__traceback__)
        last_app_frame = next(
            (f for f in reversed(tb) if "hireloop_api" in (f.filename or "")),
            tb[-1] if tb else None,
        )
        location = (
            f"{last_app_frame.filename.split('hireloop_api/')[-1]}:"
            f"{last_app_frame.lineno} ({last_app_frame.name})"
            if last_app_frame
            else "unknown"
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"[{exc_type}] {exc_msg}",
                "where": location,
                "path": request.url.path,
            },
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Startup/shutdown are handled by the lifespan context manager above.
