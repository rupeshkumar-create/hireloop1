# Hireloop — Local testing by phase

Use this doc to test **one phase at a time**. Each section lists what to run, what keys you need, and how to know it passed.

**Ports (default):**

| Service | URL |
|---------|-----|
| API | http://localhost:8000 |
| App (candidate + recruiter + admin) | http://localhost:3001 |
| Marketing (SEO) | http://localhost:3000 |
| Supabase Studio | http://localhost:54323 |
| Postgres (Supabase local) | localhost:54322 |

---

## One-time local setup

**Cloud Supabase (recommended):** follow [`SUPABASE_CLOUD_SETUP.md`](./SUPABASE_CLOUD_SETUP.md) — `supabase link` + `supabase db push` on your project, then run API + app locally.

**Local Supabase CLI:**

```bash
# From repo root
supabase start
supabase db push

# Dev seed (companies, jobs, 3 test users) — only on dev DB
psql "postgresql://postgres:postgres@localhost:54322/postgres" -f scripts/seed_dev.sql

# API
cd api && cp .env.example .env
# fill keys (see matrix below)
uvicorn hireloop_api.main:app --reload --port 8000

# App
cd app && cp .env.example .env.local
pnpm dev

# Marketing (only for P24)
cd web && cp .env.example .env.local
pnpm dev
```

**Test logins** (after seed):

| Email | Password | Use for |
|-------|----------|---------|
| candidate@test.hireloop.in | hireloop-dev-2026 | P04–P15, P19–P21 |
| recruiter@test.hireloop.in | hireloop-dev-2026 | P16–P18 |
| admin@test.hireloop.in | hireloop-dev-2026 | P23 |

Sign in via Supabase **email/password** (not LinkedIn) if you used `seed_dev.sql`.

---

## API & keys matrix

### Always required (any authenticated flow)

| What | Where to get it | Env vars |
|------|-----------------|----------|
| **Supabase project** (local or cloud) | `supabase start` or [supabase.com](https://supabase.com) | See below |
| **Postgres** | Comes with local Supabase | `DATABASE_URL` in `api/.env` |
| **JWT validation** | Supabase → Settings → API | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (API) |
| **App auth session** | Same project → anon key | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (app) |
| **CORS** | Your local app URL | `ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3000` |
| **App → API** | You choose a shared secret | `SERVICE_SECRET` (api) = `API_SERVICE_SECRET` (app) optional for server routes |
| **Frontend API base** | Local API | `NEXT_PUBLIC_API_URL=http://localhost:8000` |

**Supabase (app `.env.local`):**

```env
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<from supabase status>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Supabase (api `.env`):**

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:54322/postgres
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SERVICE_KEY=<service_role key from supabase status>
ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3000
SERVICE_SECRET=local-dev-secret
```

Run `supabase status` for URL and keys after `supabase start`.

---

### Per-phase keys (only when testing that phase)

| Phase | Keys / services | Required? | Notes |
|-------|-----------------|-----------|--------|
| **P01** CI | None | — | `pnpm lint`, `pytest` |
| **P02** Cloudflare WAF | Cloudflare account | Optional locally | Production ops |
| **P03** DB | Supabase local | **Yes** | `supabase db push` |
| **P04** Auth OTP | MSG91 | **No in dev** | Dev logs OTP to API console |
| **P04** LinkedIn | Supabase Auth → LinkedIn provider | Optional | Or use seed email/password |
| **P05–P07** Onboarding / booking | **Google Calendar** (reuses P13 OAuth) | Optional | In-house booking; slots stored in `voice_sessions`. Cal.com dropped — no `CAL_API_KEY`. Calendar event + Meet link needs `calendar.events` scope on the P13 Google OAuth app |
| **P08** Aarya chat | **OpenRouter** | **Yes** | `OPENROUTER_API_KEY` |
| **P09** Jobs ingest | **Apify** | **Yes** for live scrape | Seed jobs enough for local |
| **P10–P11** Matches | OpenRouter (embeddings) | **Yes** for recompute | Seed `match_scores` enough for feed |
| **P12** HM enrich | Apify + **NeverBounce** | **Yes** for real enrich | |
| **P13** Gmail intro | **Google Cloud OAuth** | **Yes** for send | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| **P13** Transactional email | **SendGrid** | Optional | Template IDs in config |
| **P14** Intro worker | Google + Apify + NeverBounce + DB | **Yes** end-to-end | Nitya worker starts with API if `DATABASE_URL` set |
| **P15** Voice | **Deepgram** + **ElevenLabs** | **Yes** | `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_AARYA_VOICE_ID` |
| **P16–P18** Recruiter | **OpenRouter** | **Yes** | Recruiter JWT + seed recruiter row |
| **P19** WhatsApp | **MSG91** WhatsApp | **Yes** for real WA | Template `job_match_alert` approved; without keys → logged as mock/failed |
| **P20** Tailor resume | **OpenRouter** | **Yes** | |
| **P21** Mock interview | **OpenRouter** | **Yes** | |
| **P22** Payments | — | **Deferred** | Manual placements only |
| **P23** Admin / DPDP | None extra | **No** | Promote user to `admin` or use seed |
| **P24** SEO | None | **No** | Static pages in `web/` |

---

### Where to sign up (external APIs)

| Provider | Sign up | Used for |
|----------|---------|----------|
| [Supabase](https://supabase.com) | Free project or CLI local | Auth, DB, Realtime |
| [OpenRouter](https://openrouter.ai) | API key | Aarya, Nitya, tailor, mock interview, embeddings |
| [Deepgram](https://deepgram.com) | API key | Voice STT (P15) |
| [ElevenLabs](https://elevenlabs.io) | API key + voice IDs | Voice TTS (P15) |
| [Apify](https://apify.com) | API token | Job scrape (P09), HM enrich (P12) |
| [NeverBounce](https://neverbounce.com) | API key | HM email verify (P12–P14) |
| [Google Cloud Console](https://console.cloud.google.com) | OAuth client | Gmail send (P13–P14) |
| [SendGrid](https://sendgrid.com) | API key | Transactional email (P13) |
| [MSG91](https://msg91.com) | Auth key + SMS + WhatsApp sender | OTP (prod), WhatsApp (P19) |
| [Google Calendar API](https://console.cloud.google.com) | `calendar.events` scope (same OAuth as P13) | Voice session booking (P07) — in-house, Cal.com dropped |
| [Cloudflare](https://cloudflare.com) | WAF rules | P02 production only |

**P22 Razorpay** — not in MVP.

---

## Minimal `.env` to test “most of app” locally

```env
# api/.env — minimum viable
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:54322/postgres
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_SERVICE_KEY=<service_role>
ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3000
OPENROUTER_API_KEY=sk-or-v1-...
SERVICE_SECRET=local-dev-secret

# Add when testing that feature:
# DEEPGRAM_API_KEY=...
# ELEVENLABS_API_KEY=...
# ELEVENLABS_AARYA_VOICE_ID=...
# APIFY_TOKEN=...
# GOOGLE_CLIENT_ID=...
# GOOGLE_CLIENT_SECRET=...
# MSG91_AUTH_KEY=...
# MSG91_WHATSAPP_NUMBER=...
# SUPER_ADMIN_LINKEDIN_SLUGS=iamrupesh
# SUPER_ADMIN_EMAILS=you@domain.com
```

---

# Phase-by-phase test plan

Test in order **P03 → P04 → …** or jump to a single phase using seed data.

---

## P01 — Project skeleton

**Keys:** none  
**Test:**

```bash
pnpm lint && pnpm typecheck
cd api && pytest tests/ -v
```

**Pass:** CI commands green.

---

## P02 — Infra / Cloudflare geo-lock

**Keys:** Cloudflare (production)  
**Test:** N/A locally.  
**Pass:** WAF blocks non-IN ASN in staging/prod.

---

## P03 — Database

**Keys:** Supabase local  
**Test:**

```bash
supabase db push
psql ... -f scripts/seed_dev.sql
```

**Pass:** Tables exist; seed companies/jobs/users visible in Studio.

---

## P04 — Auth (+91 OTP + login)

**Keys:**

- Supabase (required)
- MSG91 — **only production**; in `ENVIRONMENT=development` OTP prints in **API logs**

**Test:**

1. `http://localhost:3001/signup` — LinkedIn **or** email `candidate@test.hireloop.in` / `hireloop-dev-2026`
2. OTP: `POST /api/v1/auth/send-otp` with `{"phone":"+919876543210"}` — read OTP from terminal log
3. `POST /api/v1/auth/verify-otp` with phone + OTP
4. `GET /api/v1/auth/me` with Bearer token

**Pass:** `india_verified=true` on user.

---

## P05 — Onboarding UI

**Keys:** none (UI only)  
**Test:** `http://localhost:3001/onboarding` — walk steps.  
**Pass:** Pages render; no crash.

---

## P06 — Resume upload

**Keys:** Supabase Storage buckets (migration `007`)  
**Test:** Upload PDF on onboarding; `POST /api/v1/resumes/upload`.  
**Pass:** Row in `resumes`; parsed fields populated (parser may need Affinda later).

---

## P07 — Voice booking (in-house, Google Calendar)

**Keys:** none required for the in-app path. Calendar event + Meet link uses the **P13 Google OAuth**
app with the `calendar.events` scope (`GOOGLE_CALENDAR_ID`). Cal.com dropped — no `CAL_API_KEY`.  
**Test:**

- `GET /api/v1/voice-sessions/slots`  → availability windows from Postgres
- `POST /api/v1/voice-sessions/book`  → creates the `voice_sessions` row (+ Calendar event if OAuth wired)

**Pass:** `voice_sessions` row created; `calendar_event_id` populated when the Google scope is connected
(otherwise the in-app slot alone is the booking).

---

## P08 — Aarya chat (SSE)

**Keys:** **OpenRouter**  
**Test:**

1. `http://localhost:3001/chat`
2. Send message; stream reply
3. `GET /api/v1/chat/sessions/{id}/actions` — action count increases

**Pass:** Assistant streams; `agent_actions` rows written.

---

## P09 — Job ingestion (Apify)

**Keys:** **Apify**  
**Test:**

- `POST /api/v1/jobs/ingest` (service secret header)
- Or rely on **seed jobs** for other phases

**Pass:** New rows in `jobs` with `country_code=IN`.

---

## P10 — Embeddings + match scores

**Keys:** **OpenRouter** (embeddings)  
**Test:**

```bash
# With service secret
curl -X POST http://localhost:8000/api/v1/matches/embed/candidate/<candidate_uuid> \
  -H "X-Service-Secret: local-dev-secret"
```

Or use **seed** `match_scores` for candidate `ca000000-...`.

**Pass:** `match_scores` + `job_embeddings` populated.

---

## P11 — Match feed + 3 actions

**Keys:** none if seed matches exist; OpenRouter for tailor/intro  
**Test:**

1. `http://localhost:3001/dashboard` as candidate
2. See job cards with scores
3. **Request Intro** → redirects to chat
4. **Direct Apply** → opens `apply_url`
5. **Tailor** → processing → download HTML (needs OpenRouter)

**Pass:** All three buttons behave; intro message in chat.

---

## P12 — HM enrichment (Apify)

**Keys:** **Apify**, **NeverBounce**  
**Test:** `POST /api/v1/hiring-managers/{id}/enrich`  
**Pass:** `hiring_managers.email_verified=true`.

---

## P13 — Gmail + SendGrid

**Keys:** **Google OAuth**, SendGrid optional  
**Test:**

- Gmail connect flow on settings
- SendGrid only for transactional templates

**Pass:** `gmail_tokens` row; test email via SendGrid dashboard.

---

## P14 — Intro handshake

**Keys:** Google + Apify + NeverBounce + OpenRouter; API must run **Nitya worker** (auto on startup)  
**Test:**

1. Candidate: Request Intro on a job
2. Check `intro_requests` → status progresses
3. Nitya LISTEN/NOTIFY → draft + Gmail send

**Pass:** `intro_requests.status=sent`; email in candidate Gmail (or error logged).

---

## P15 — Voice (chat mic — not LiveKit)

**Keys:** **Deepgram**, **ElevenLabs**  
**Test:**

1. `http://localhost:3001/chat` — tap mic, speak, stop
2. `POST /api/v1/voice/stt` + `/tts` via UI
3. Optional: `GET /api/v1/voice/voices`

**Pass:** Transcript sends as message; TTS plays reply.

**Not built yet:** 20-min LiveKit room (`/call/[id]`).

---

## P16 — Nitya role + hiring brief

**Keys:** **OpenRouter**  
**Test:**

1. Login `recruiter@test.hireloop.in`
2. `http://localhost:3001/recruiter/roles/new` → create role
3. `…/intake` — chat until Nitya outputs brief
4. Check `roles.hiring_brief`, `evaluation_criteria` in DB

**Pass:** Brief saved; “Nitya performed N actions” increases.

---

## P17 — Candidate search for role

**Keys:** OpenRouter optional; needs `match_scores` for proxy job  
**Test:** Pipeline page → **Rerun search**  
**Pass:** `role_pipeline` rows with scores.

---

## P18 — Pipeline + inbox

**Keys:** none  
**Test:**

- `http://localhost:3001/recruiter/inbox`
- `…/pipeline` — change stage to `hired`

**Pass:** Stage persists; `placements` row with `hired_unbilled`.

---

## P19 — WhatsApp (MSG91)

**Keys:** **MSG91** auth + WhatsApp Business number + Meta-approved template `job_match_alert`  
**Test:**

1. `http://localhost:3001/settings` — toggle WhatsApp prefs
2. Trigger match recompute (score ≥ 65%) → check `notifications`, `whatsapp_messages`
3. `POST /api/v1/webhooks/test-whatsapp` (authenticated)
4. Webhook: `POST /api/v1/webhooks/msg91-whatsapp` + header `X-Service-Secret`

**Pass:** Row in `whatsapp_messages`; real phone receives template (prod-like env).

**Without MSG91:** In-app notification still inserted; WhatsApp logged as failed/mock.

---

## P20 — Tailored resume

**Keys:** **OpenRouter**  
**Test:**

1. Dashboard → **Tailor** on a job
2. Or `POST /api/v1/tailored-resumes/tailor` `{"job_id":"aaaaaaaa-...","template":"modern"}`
3. Poll `GET /api/v1/tailored-resumes/tailored/{id}`
4. `http://localhost:3001/resumes`

**Pass:** `status=ready`; HTML download opens.

---

## P21 — Mock interview

**Keys:** **OpenRouter**  
**Test:**

1. `http://localhost:3001/mock-interview`
2. Start session → answer questions → end with “I’m done”
3. Check `mock_interviews.feedback`

**Pass:** JSON feedback stored.

---

## P22 — Payments

**Status:** **Deferred** (v2 Razorpay).  
**Test:** Mark hired in pipeline → view `http://localhost:3001/admin/placements`.

---

## P23 — Admin + DPDP

**Keys:** none  
**Test:**

1. Login `admin@test.hireloop.in`
2. `http://localhost:3001/admin`
3. `GET /api/v1/admin/dashboard`, `/bias-audit`, `/placements`
4. Settings → export: `GET /api/v1/me/dpdp/export`
5. Delete account: `DELETE /api/v1/me` (use a throwaway user)

**Pass:** JSON export downloads; soft-delete + `dpdp_export_jobs` row.

---

## P24 — SEO (marketing site)

**Keys:** none  
**Test:**

```bash
cd web && pnpm build && pnpm start
```

Visit e.g. `http://localhost:3000/jobs/software-engineer-jobs-in-bangalore`  
Check `http://localhost:3000/sitemap.xml`

**Pass:** Static job pages build; sitemap lists URLs.

---

## Quick reference — API docs

With API running: http://localhost:8000/api/docs

---

## Suggested test order (isolated milestones)

| Week / session | Phases | Minimum keys |
|----------------|--------|----------------|
| 1 | P03, P04, P08, P11 | Supabase + OpenRouter |
| 2 | P10, P14 | + Apify, Google, NeverBounce |
| 3 | P15, P20, P21 | + Deepgram, ElevenLabs |
| 4 | P16–P18 | OpenRouter + seed recruiter |
| 5 | P19, P23 | + MSG91 |
| 6 | P24 | none |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 401 on API | Pass Supabase access token; user must exist in `public.users` |
| 403 “Phone verification” | Run verify-otp or set `india_verified=true` in seed |
| CORS error | Add `http://localhost:3001` to `ALLOWED_ORIGINS` |
| No matches on dashboard | Run seed or `matches/embed/candidate/{id}` |
| Recruiter 403 | `users.role=recruiter` + `recruiters` row |
| Voice 503 | Set ElevenLabs voice IDs |
| WhatsApp no send | Expected without MSG91; check `whatsapp_messages.error_message` |
