# ── Build stage ────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (layer cache)
COPY pyproject.toml .
COPY ruff.toml .

# Install dependencies into a virtual environment
RUN uv sync --no-dev --frozen

# Copy source code
COPY src/ ./src/

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1001 hireloop && \
    useradd --uid 1001 --gid hireloop --shell /bin/sh --create-home hireloop

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

# Make sure the venv binaries are on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

# Health check (ECS will use this)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/api/v1/health'); r.raise_for_status()"

USER hireloop

EXPOSE 8000

CMD ["uvicorn", "hireloop_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
