# Hireloop API — FastAPI (uvicorn). Container host: Railway / any PaaS.
# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=0

# Deps first (cached on the lockfile), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Run as non-root.
RUN groupadd --gid 1001 hireloop && \
    useradd --uid 1001 --gid hireloop --shell /bin/sh --create-home hireloop

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1

USER hireloop
EXPOSE 8000

# Railway injects $PORT. ONE worker only — the app runs the Nitya LISTEN +
# background-job workers in-process, so multiple uvicorn workers would duplicate
# them. Scale via instances (each its own single worker), not --workers.
# --no-access-log: dashboard polling emits an INFO line every ~2s per client,
# which hit Railway's 500 logs/sec cap and DROPPED thousands of messages —
# including real errors. structlog's slow_request + error logs cover ops needs.
CMD ["sh", "-c", "uvicorn hireloop_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log"]
