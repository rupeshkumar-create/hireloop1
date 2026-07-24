# 10 — Operations Runbook

Deploy, rollback, migrations, logs, secrets, backups, and local setup — verified against repo scripts/README where possible.

---

## Deploy each surface

### Product SPA (`app/`)

| Item | Detail |
|---|---|
| Platform | Vercel project `hireloop1-app` (`.vercel/project.json`), region `sin1` (`app/vercel.json`) |
| Root config | Root `vercel.json` → `pnpm --filter app build` |
| Deploy | Push / Vercel dashboard promote (no GitHub deploy workflow in `.github/workflows/ci.yml` — CI is lint/test only) |
| Env | `app/.env.example` → Vercel env (`NEXT_PUBLIC_SUPABASE_*`, `NEXT_PUBLIC_API_URL`, etc.) |
| Docs | `SUPABASE_CLOUD_SETUP.md` (~185–220) mentions `www.hireschema.com` |

### Marketing site (`web/`)

| Item | Detail |
|---|---|
| Dev | `pnpm dev:web` → :3000 |
| Prod | **No dedicated `web/vercel.json`**; root Vercel builds **app**. Marketing deploy project mapping is unclear from repo alone |

### API (`api/`)

| Item | Detail |
|---|---|
| Platform | Railway — `api/railway.toml` Dockerfile build, health `/api/v1/health`, restart on_failure ×5, region `asia-southeast1-eqsg3a`, **1 replica** |
| Image | `api/Dockerfile` → uvicorn `hireloop_api.main:app` |
| Smoke | `./api/scripts/smoke_railway.sh` (referenced in ops docs) |
| Env | `api/.env.example` → Railway variables |

### Database

| Item | Detail |
|---|---|
| Platform | Supabase Cloud project id in `supabase/config.toml` |
| Apply | `supabase link` + `supabase db push` (README / `LOCAL_TESTING.md` / `SUPABASE_CLOUD_SETUP.md`) |

### Planned but not active primary path

- AWS ECS Fargate Terraform: `infra/terraform/` — PHASE_TRACKER S22 not started.
- Cloudflare WAF Terraform: `infra/cloudflare/waf_rules.tf` (rate limits).

---

## Rollback

| Surface | How |
|---|---|
| Vercel | Redeploy previous deployment in Vercel UI / CLI `vercel rollback` (standard Vercel — not scripted in-repo) |
| Railway | Redeploy prior deployment / pin image (Railway UI — not scripted) |
| DB migrations | **No formal down-migration runbook in-repo.** Migrations are numbered SQL forward files. Rollback = manual reverse SQL or restore from backup |

Treat schema changes as **forward-only** unless a human authors a compensating migration.

---

## Migrations safely

1. Review SQL under `supabase/migrations/YYYYMMDDHHMMSS_*.sql`.
2. Run against staging/linked project: `supabase db push` (or CI equivalent if added later).
3. Prefer expansion→backfill→contract for destructive changes.
4. After pgvector/bulk embeds: docs say `ANALYZE` (R12) — operators should run manually after large loads.
5. Cron jobs that call API depend on GUCs for API URL + service secret — verify after migrate (`20240101000800` / `009` patterns).

---

## Logs by service

| Service | Where |
|---|---|
| API (+ workers) | Railway logs; structlog JSON in production (`main.py`); optional Sentry |
| SPA / web | Vercel function/runtime logs |
| Supabase | Dashboard logs; `pg_cron` / `pg_net` history in Postgres |
| Local | `.local-dev-*.log` files at repo root (dev helper artifacts) |

Slow request warning middleware logs &gt;1000ms (`main.py:_request_timing`).

---

## Secret rotation

| Secret | Rotate by |
|---|---|
| `SECRET_KEY` / `SERVICE_SECRET` | Generate new; update Railway; redeploy API; update Supabase cron GUCs that send `X-Service-Secret` |
| Supabase anon / service keys | Supabase dashboard → update Vercel + Railway |
| OpenRouter | Provider console → Railway |
| Apify | Apify console → Railway |
| Deepgram | Deepgram → Railway |
| Resend / SendGrid | Provider → Railway |
| Google OAuth client id/secret | Google Cloud Console → Railway; candidates may need to reconnect Gmail |
| MSG91 / NeverBounce / Firecrawl / LinkDAPI | Provider → Railway |
| Sentry DSN | Sentry → Railway |

Production refuses weak `SECRET_KEY` / `SERVICE_SECRET` (see `KEYS_AND_UNLOCKS.md`). No automated rotation in-repo.

---

## Database backup / restore

**Cannot verify from this repository that backups are enabled.**

- No tested `pg_dump` / restore script shipped as a production runbook.
- `BACKEND_IMPROVEMENT_PLAN.md` still lists “Nightly pg_dump + restore runbook” as needed.
- Practically relies on **Supabase platform backups / PITR** — confirm in Supabase dashboard (plan feature).

**Restore (generic):** identify PITR or dump → restore to new project or reset → `supabase db push` if schema behind → re-point Railway `DATABASE_URL` / Supabase URL carefully.

---

## Local development (fresh clone)

Verified against `README.md` + `LOCAL_TESTING.md` + root `package.json` scripts:

### Prerequisites

- Node 20.17+ (`nvm use` / `.nvmrc`)
- pnpm 9.12+
- Python 3.12 + `uv`
- Docker Desktop
- Supabase CLI

### Install

```bash
pnpm install
cd api && uv sync
```

### Env

```bash
cp web/.env.example web/.env.local
cp app/.env.example app/.env.local
cp api/.env.example api/.env
```

Fill credentials (Supabase, OpenRouter, etc.).

### Run

```bash
supabase start          # API 54321, DB 54322, Studio 54323
pnpm dev:web            # :3000
pnpm dev:app            # :3001
pnpm dev:api            # :8000
```

Seed logins referenced in `LOCAL_TESTING.md` use `*@test.hireschema.com` / password `hireloop-dev-2026`.

### Note

README phase pointer to sibling `../hireloop/` and “P01” status is **stale** — use monorepo `PHASE_TRACKER.md`.

---

## Security console checklist (S1 — SEC-2 / SEC-3 / SEC-4)

See full acceptance criteria in `docs/audit/14-security-remediation-plan.md`. Execute in production dashboards:

### SEC-2 — Google OAuth (`gmail.send`)

1. Open Google Cloud Console → OAuth consent screen for the Hireschema / Hireloop project.
2. Record: status (`Testing` / `In production` / verification pending), app display name, test-user list size.
3. If Testing: start verification (privacy policy URL = `https://www.hireschema.com/privacy`, scope justification for `gmail.send` + `calendar.events`, demo video of connect → approve-send).
4. Refresh-token test: use an account connected >7 days ago; call Gmail send/status; note whether refresh succeeds without re-consent.
5. Paste results under “Google OAuth status” in this file when done.

**Google OAuth status (fill in):** `_pending human_`

### SEC-3 — Sentry

1. Create/confirm Sentry project; copy DSN.
2. Set `SENTRY_DSN` (and optional sample rate) on Railway **production** service; redeploy.
3. Confirm API logs do **not** print `sentry_dsn_missing_in_production`.
4. Trigger a test exception (temporary admin endpoint or Sentry “Send test event”); confirm Slack/email alert within minutes.
5. Add alert: error-rate spike on transactions matching `/api/v1/public/*`.

**Sentry status (fill in):** `_pending human_`

### SEC-4 — Security migrations on prod Supabase

```bash
supabase link   # prod project
supabase migration list
```

Confirm these (and tip) are applied:

- `20260713100000_deactivate_stale_scraped_jobs`
- `20260713120000_intro_outbound_drafts`
- `20260713160000_candidate_privacy_opt_in`
- `20260713161000_distributed_public_rate_limits`
- `20260715180000_robustness_india_intro_dpdp`

SQL spot-checks:

```sql
SELECT COUNT(*) FROM public.api_rate_limits;
SELECT COUNT(*) FROM public.candidates
WHERE share_with_recruiters = TRUE AND deleted_at IS NULL;
-- Cross-check consent_log for those who share.
```

Abuse trip test: hammer `POST /api/v1/public/profiles/{slug}/chat` (or apply) until **429**.

**Migration status (fill in):** `_pending human_`

### SEC-1 leftover — secret hygiene

1. Rotate OpenRouter key in provider console → update Railway `OPENROUTER_API_KEY` → revoke old (expect 401).
2. Delete or vault local `.railway/migration-env.json` and `.railway/migration-backup.json`.
3. Run full-history gitleaks (CI job or local CLI); explain any remaining findings.

---

## Discrepancies

1. README tech stack (LinkedIn Jobs Scraper, SendGrid-primary, AWS ECS, Tailwind 4) ≠ live code/deploy.
2. Marketing `web/` production hosting not fully specified by root Vercel config.
3. No CI/CD deploy workflow — only CI checks.

---

## Unverified — needs human confirmation

1. Supabase backup retention / PITR enabled.
2. Exact Vercel project for `web/` / DNS cutover details.
3. Who owns Railway/Vercel org access and on-call.
4. Live cron GUC values for API base URL + service secret.
5. SEC-2 / SEC-3 / SEC-4 console results (fill-in sections above).
