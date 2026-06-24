# AGENTS.md — Hireloop AI Coding Agent Instructions

This file is read by Codex (and other AI agents) at the start of every session.
Follow these instructions in addition to `.cursorrules`.

## Project identity

**Hireloop** — India-first AI recruiting platform.
- **Aarya** = candidate-facing AI agent
- **Nitya** = recruiter/HM-facing AI agent
- Shared Postgres candidate graph via Supabase

## Monorepo packages

| Path | Stack | Purpose |
|---|---|---|
| `web/` | Next.js 15 + TS + Tailwind | Marketing site → hireloop.in |
| `app/` | Next.js 15 + TS + Tailwind | Candidate + Recruiter SPA → app.hireloop.in |
| `api/` | FastAPI + Python 3.12 | REST API + LangGraph agent loops |

## Before writing any code

1. Read `MVP_RULES.md` (at `.cursorrules`) — hard constraints
2. Check `PHASE_TRACKER.md` — what phase are we in? what's done?
3. Read the relevant section of `HIRELOOP_MVP.md` for the feature
4. If a rule conflicts with a feature request, **the rule wins** — raise it with the user

## Coding conventions

### TypeScript (web + app)
- Strict mode always on
- Prefer `type` over `interface` for data shapes
- Use `zod` for all runtime validation (forms, API responses)
- Server Components by default; mark Client Components explicitly with `"use client"`
- Tailwind utility classes only — no CSS modules, no styled-components
- shadcn/ui components from `@/components/ui/`
- All API calls via `src/lib/api.ts` — never call Supabase direct from pages
- Env vars: `NEXT_PUBLIC_` prefix for client-side only

### Python (api)
- Python 3.12, type hints everywhere
- Pydantic v2 for all data models (no plain dicts crossing module boundaries)
- `asyncpg` for DB — never use the synchronous psycopg2
- `httpx.AsyncClient` for all HTTP — never `requests`
- FastAPI dependency injection for auth, DB pool, settings
- Never `import *`
- Ruff for linting + formatting (`ruff check . && ruff format .`)
- All secrets via `pydantic_settings` / `.env` — never hardcode

### Database
- All migrations in `supabase/migrations/` — numbered `YYYYMMDDHHMMSS_description.sql`
- Always use soft-delete (`deleted_at IS NULL` filter) on PII tables
- pgvector: cosine similarity only (`<=>`), HNSW index on every `*_embedding` column
- Row-Level Security (RLS) enabled on every table
- Sequences/UUIDs: use `gen_random_uuid()` as default for PKs

## Running commands

```bash
# Lint TypeScript
pnpm lint

# Type-check TypeScript
pnpm typecheck

# Lint Python (from api/)
ruff check . && ruff format --check .

# Run Python tests (from api/)
pytest tests/ -v

# Run DB migrations (from repo root)
supabase db push
```

## Agent patterns

### Aarya (candidate agent) — `api/src/hireloop_api/agents/aarya/`
- Single-threaded master loop (see R6 in .cursorrules)
- Tools: profile_read, job_search, match_score, request_intro, voice_response
- State persisted in LangGraph checkpoint (Postgres backend)
- Every tool call → `agent_actions` table → Supabase Realtime → frontend counter

### Nitya (recruiter agent) — `api/src/hireloop_api/agents/nitya/`
- Wakes via Postgres LISTEN/NOTIFY on `intro_requests` channel
- Tools: candidate_lookup, draft_email, send_via_gmail, update_intro_status
- NEVER sends cold email via SendGrid — always Gmail OAuth

## Secrets management

All secrets in `.env` files (never committed).
Use `.env.example` as the template (committed, no real values).
In CI: GitHub Actions secrets → environment variables.
In production: AWS Secrets Manager → ECS task definition env vars.

## What NOT to do

See `.cursorrules` R16 for the full list of hard NOs.
Summary: no pirated software, no cold email via SendGrid, no LinkedIn scraping
without Apify no-cookie actors, no agent-to-agent RPC, no payment plumbing,
no hardcoded secrets, no SELECT * on large tables.
