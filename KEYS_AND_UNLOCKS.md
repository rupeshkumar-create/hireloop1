# Keys & Unlocks — what each `.env` value turns on

Most "pending" work across P09–P21 is **code-complete but gated on an external account/key**.
This maps every key to *what it unlocks*, *what happens without it*, and *where to get it*.
Set these in `api/.env` (never commit). After editing, **restart the API** — settings are
read once at boot (`@lru_cache`).

> Legend: 🟢 works without it (graceful fallback) · 🔴 feature is dead until set · ⚙️ flag

---

## TL;DR priority order

| # | Key(s) | Unlocks | Without it |
|---|--------|---------|------------|
| 0 | `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SECRET_KEY`, `SERVICE_SECRET` | App boots, auth, DB | 🔴 won't run / prod refuses to start |
| 1 | `OPENROUTER_API_KEY` | **Everything LLM**: Aarya/Nitya chat, career path, match rationale, tailored resume, mock interview, **embeddings** (semantic match) | 🔴 all AI features |
| 2 | `APIFY_TOKEN` + **actor rental** | P09 job ingestion, P12 HM enrichment | 🔴 no scraped jobs / no HM emails |
| 3 | `GOOGLE_CLIENT_ID/SECRET` + `SENDGRID_API_KEY` (+ `SG_TEMPLATE_*`, `NEVERBOUNCE_API_KEY`) | P13 email + candidate→HM intro send + **P07 voice-session booking (Google Calendar)** | 🔴 HM intros stop at "no Gmail connected"; 🟢 P07 falls back to in-app slots |
| 4 | `DEEPGRAM_API_KEY` | P15 server-side voice (STT + TTS) | 🟢 falls back to browser Web Speech |
| 5 | `MSG91_AUTH_KEY` (+ `MSG91_WHATSAPP_NUMBER`) | Phone OTP + P19 WhatsApp | 🟢 number captured, not verified/sent |
| – | `AFFINDA_API_KEY` | P06 resume parsing | 🟢 degraded parse |
| – | `LINKDAPI_KEY` | LinkedIn profile pre-fill at onboarding | 🟢 skipped |

---

## 0 · Core (required to run)

```
ENVIRONMENT=development            # development | staging | production
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:54322/postgres
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
SECRET_KEY=<strong-random>         # prod BOOT FAILS if left "change-me"
SERVICE_SECRET=<strong-random>     # gates service webhooks + admin cron; prod must set
SUPER_ADMIN_EMAILS=you@hireschema.com # bootstraps the first admin (P23)
```
The production guard (`_enforce_production_secrets`) refuses to start if `SECRET_KEY`/`SERVICE_SECRET`
are empty or `change-me`.

## 1 · OpenRouter — the biggest single unlock

```
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_PRIMARY_MODEL=anthropic/claude-sonnet-4.6    # reasoning / tools / career paths
OPENROUTER_FALLBACK_MODEL=google/gemini-2.5-flash       # resume parse / title expand
OPENROUTER_FAST_MODEL=google/gemini-2.5-flash           # high-volume utility turns
MATCH_RATIONALE_ENABLED=false   # ⚙️ on = per-card "why you fit" (extra LLM calls)
AUTO_INGEST_ON_EMPTY_SEARCH=false  # ⚙️ on = scrape when a search returns nothing (spends Apify)
```
Unlocks: **P08** Aarya chat, Nitya intro drafting, **career path**, **P10 embeddings** (semantic
layer — lexical matching works without it but is sharper with), **P20** resume tailoring,
**P21** mock interview, career intelligence. Get it at https://openrouter.ai/keys.

## 2 · Apify — ingestion & HM enrichment

```
APIFY_TOKEN=apify_api_...
APIFY_ENABLE_CAREER_SITE_INGEST=true
APIFY_LINKEDIN_JOBS_ACTOR=bebity/linkedin-jobs-scraper
APIFY_CAREER_SITE_ACTOR=fantastic-jobs/career-site-job-listing-api
```
**The blocker is actor rental, not the token.** The token is validated, but the rental actors
must be rented on your Apify plan (FREE plan can't). Unlocks **P09** (real jobs in the feed) and
**P12** (hiring-manager contact enrichment → candidate→HM intros). Recruiter-posted roles work
without this; scraped roles and HM intros do not.

## 3 · Email pipeline + candidate→HM intro (P13/P14 HM path)

```
GOOGLE_CLIENT_ID=...              # Gmail OAuth — intros sent FROM the candidate's Gmail (R9)
GOOGLE_CLIENT_SECRET=...
SENDGRID_API_KEY=SG....           # transactional only (signup, alerts, invites)
SENDGRID_FROM_EMAIL=noreply@hireschema.com
SENDGRID_FROM_NAME=Hireschema
SG_TEMPLATE_SIGNUP_CONFIRMATION=d-...
SG_TEMPLATE_JOB_MATCH_ALERT=d-...
SG_TEMPLATE_INTERVIEW_REMINDER=d-...
SG_TEMPLATE_INTRO_STATUS=d-...
NEVERBOUNCE_API_KEY=...           # verify HM email before sending
```
Rule (R9/R16): **cold intro emails go via the candidate's Gmail, never SendGrid.** Without Gmail
OAuth, the candidate→HM pipeline marks intros "declined — no Gmail connected." The candidate→
**registered-recruiter** loop needs none of this (fully in-app/DB-driven).

## 3b · Voice-session booking — P07 (in-house, Google Calendar)

```
GOOGLE_CALENDAR_ID=primary          # the calendar Aarya/Nitya books AI career calls into
# Reuses GOOGLE_CLIENT_ID/SECRET above — request the calendar.events scope at OAuth consent.
```
**Cal.com has been dropped.** P07 is now built in-house: availability windows live in Postgres,
and on confirm we create a Google Calendar event (with a Meet link) via the Calendar API using the
**same Google OAuth app as P13** — one vendor relationship, no extra `CAL_API_KEY`. 🟢 Without the
calendar scope wired, booking still works via in-app slots stored in `voice_sessions`; the calendar
event + Meet link is the enrichment layer. This removes the prior `CAL_API_KEY` / `CAL_USERNAME` /
event-type-ID requirement entirely.

**Scopes are bundled into one consent.** `GET /api/v1/gmail/connect` requests `gmail.send` **and**
`calendar.events` together, so a candidate connects Google once and unlocks both P13 outreach and
P07 booking. Enable **both** the Gmail API and the Google Calendar API in the Cloud project, and add
both scopes to the OAuth consent screen. `GET /api/v1/gmail/status` returns `send_enabled` +
`calendar_enabled` so the UI knows what was granted. ⚠️ Candidates who connected *before* this change
hold a send-only token (`calendar_enabled: false`) and must hit Connect again to grant calendar.

## 4 · Voice (P15)

```
DEEPGRAM_API_KEY=...
DEEPGRAM_TTS_MODEL=aura-asteria-en
```
🟢 Server-side STT + Aarya's TTS. Without it the browser's Web Speech API is used (less consistent
across devices/accents). The recruiter-style mock-interview call reuses this.

## 5 · Phone / WhatsApp (P04 OTP, P19)

```
MSG91_AUTH_KEY=...
MSG91_SENDER_ID=HLLOOP
MSG91_WHATSAPP_NUMBER=...
REQUIRE_PHONE_VERIFICATION=false   # ⚙️ prod should be true once MSG91 is live for +91
```
🟢 Phone OTP is **India (+91) via MSG91 only**. Other markets use the app without SMS verification.
WhatsApp notifications (P19) wait on MSG91 WABA approval.

## Supporting enrichment

```
AFFINDA_API_KEY=...        # P06 resume → structured profile (degraded parse without it)
LINKDAPI_KEY=...           # resolve a candidate's LinkedIn URL → pre-filled profile at onboarding
LINKDAPI_BASE_URL=https://linkdapi.com
```

---

## After setting keys — make changes take effect

1. **Restart the API** (settings are `@lru_cache`d at boot).
2. If you set `OPENROUTER_API_KEY` or changed matching: `uv run python scripts/recompute_matches.py`
   so the feed re-ranks with fresh (and now semantic) scores.
3. If you rented the Apify actor: `uv run python scripts/run_ingest.py` to pull live jobs.
