# Hireschema

**Hireschema** — AI recruiting platform for India. Aarya (candidate AI) + Nitya (recruiter AI) powered by a shared Postgres candidate graph.

> Replicating the Jack & Jill model (Tinker Tailor Talent, London) for the Indian market — INR, +91-only, ap-south-1, DPDP-compliant.

---

## Monorepo layout

```
hireloop-app/
├── web/          # Marketing site (Next.js 15) → hireschema.com
├── app/          # Candidate + Recruiter app (Next.js 15) → hireschema.com
├── api/          # Backend API + Agent loops (FastAPI, Python 3.12)
├── infra/        # Terraform (AWS ap-south-1 + Cloudflare)
├── docs/         # ADRs, runbooks, data-flow diagrams
├── scripts/      # DB seed, migration helpers, one-off scripts
└── .github/      # CI/CD workflows
```

## Quick start

### Prerequisites

- Node 20.17+ (`nvm use`)
- pnpm 9.12+ (`npm i -g pnpm`)
- Python 3.12+ with `uv` (`pip install uv`)
- Docker Desktop (for local Supabase)
- Supabase CLI (`brew install supabase/tap/supabase`)

### Install

```bash
# Node packages (web + app)
pnpm install

# Python packages (api)
cd api && uv sync
```

### Environment

```bash
# Copy env templates
cp web/.env.example web/.env.local
cp app/.env.example app/.env.local
cp api/.env.example api/.env
```

Fill in credentials from Supabase dashboard, OpenRouter, Deepgram, MSG91, SendGrid, Apify, NeverBounce.

### Run locally

```bash
# Terminal 1 — Supabase local stack
supabase start

# Terminal 2 — Marketing site
pnpm dev:web          # http://localhost:3000

# Terminal 3 — App
pnpm dev:app          # http://localhost:3001

# Terminal 4 — API
pnpm dev:api          # http://localhost:8000
```

## Phase tracker

See [PHASE_TRACKER.md](../hireloop/PHASE_TRACKER.md) for current build status.

Current phase: **P01 — Repo & CI scaffold** `in_progress`

## Spec documents

| Document | Purpose |
|---|---|
| [HIRELOOP_MVP.md](../hireloop/HIRELOOP_MVP.md) | Master spec — single source of truth |
| [MVP_RULES.md](../hireloop/MVP_RULES.md) | Hard constraints (also at `.cursorrules`) |
| [MVP_SPEC.md](../hireloop/MVP_SPEC.md) | Feature spec with acceptance criteria |
| [PHASE_TRACKER.md](../hireloop/PHASE_TRACKER.md) | Build journal, 24 phases |
| [TOOLS_PRICING.md](../hireloop/TOOLS_PRICING.md) | Vendor list + pricing worksheet |

## Tech stack

| Layer | Tool |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind CSS 4, shadcn/ui |
| Backend | FastAPI (Python 3.12), asyncpg, LangGraph |
| Database | Supabase (Postgres 15 + pgvector) |
| AI / LLM | OpenRouter → claude-3-5-sonnet |
| Voice TTS | Deepgram Aura |
| Voice STT | Deepgram Nova-3 |
| Auth | Supabase Auth (LinkedIn OAuth + MSG91 OTP) |
| Job scraping | Apify (LinkedIn Jobs Scraper) |
| HM enrichment | Apify waterfall + NeverBounce |
| Email | SendGrid (transactional) + Gmail OAuth (cold outreach) |
| WhatsApp | MSG91 |
| Infra | AWS ap-south-1, ECS Fargate, Cloudflare WAF |

## India-only marketplace (MVP)

Candidates, recruiters, and jobs are scoped to India (`market = IN`):
- Phone OTP: +91 via MSG91 only
- Salaries in INR (LPA)
- Job visibility: onsite = India; remote = `allowed_regions` includes IN or WORLD
- `ENABLED_MARKETS=IN` — job ingest is India-only

## License

Proprietary — All rights reserved. Hireschema
