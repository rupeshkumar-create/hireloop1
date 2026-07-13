# Hireschema — Build Phases (User Journey Order)

Phases follow the **exact order a real user experiences the product**, not technical concerns.
Build → test → ship each phase before moving to the next.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Code complete — working |
| 🧪 | Code complete — needs manual test with real env keys |
| 🔑 | Blocked on an API key / external account you haven't set up yet |
| 🔲 | Not started |
| ⏸ | Deferred to v2 |

---

## Status Summary

```
DONE (code + scaffolding) ──────────────────────── S01–S21  (all code written)
NEEDS TESTING ──────────────────────────────────── S01–S21  (none end-to-end tested yet)
BLOCKED ON KEYS ────────────────────────────────── S07 (Apify) · S11 (Google OAuth) · S15 (MSG91)
NOT STARTED ────────────────────────────────────── S22 (infra deploy)
DEFERRED ───────────────────────────────────────── S23 (payments)
```

---

# CANDIDATE JOURNEY

---

## S01 — LinkedIn Signup  ✅ 🧪

> User opens app, clicks "Continue with LinkedIn", lands on `/dashboard`.

**What's built:**
- Supabase Auth LinkedIn OAuth provider
- `users` row created on first login (`role = 'candidate'`)
- Redirect → `/onboarding` if new user, `/dashboard` if returning

**How to test:**
```
1. cd app && pnpm dev
2. Open http://localhost:3001/signup
3. Click "Continue with LinkedIn"
4. Complete LinkedIn OAuth
5. Should land on /onboarding (new) or /dashboard (returning)
```

**DB check:**
```sql
SELECT id, email, role, created_at FROM public.users ORDER BY created_at DESC LIMIT 5;
```

**Env needed:** `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` ← already set

---

## S02 — Phone OTP Verification (optional)  ✅ 🧪

> Optional phone verification: India (+91/MSG91) when configured.
> Not required for signup — available in Settings when configured.

**What's built:**
- `POST /api/v1/auth/phone/send-otp`, `POST /api/v1/auth/phone/verify-otp`
- `phone_verified` flag on `users` table (+ `market`, `phone_country`)
- `get_phone_verified_user` FastAPI dependency (only when `require_phone_verification=true`)

**How to test:**
```
1. Sign up via LinkedIn → complete onboarding (no phone step)
2. Optional: verify phone from Settings when MSG91 keys are set (India +91 only)
3. OTP received via SMS (dev: logged in API when ENVIRONMENT=development)
```

**Env needed:**
```
ENABLED_MARKETS=IN
MSG91_AUTH_KEY=...          # IN OTP (+91 only)
```

**DB check:**
```sql
SELECT email, phone_verified, market, phone FROM public.users WHERE phone_verified = true;
```

---

## S03 — Onboarding Wizard (v2)  ✅ 🧪

> Two-step activation after signup: welcome → CV + DPDP consent (India-only).
> On completion → `/dashboard` with jobs panel open.

**Steps:**
1. **Welcome** — Aarya introduces herself
2. **Activate** — CV upload, legal consent → `complete-onboarding` (market fixed to IN)

**What's built:**
- `/onboarding/OnboardingFlow.tsx` — v2 two-step wizard
- `candidates` row created with `profile_complete = false`
- Resume, voice, and CTC are dashboard boosters — not wizard gates

**How to test:**
```
1. Complete S01
2. Should see welcome → activate flow
3. Upload CV, pick market, accept terms
4. Should land on /dashboard with jobs open
```

**DB check:**
```sql
SELECT c.id, u.full_name, c.profile_complete
FROM public.candidates c JOIN public.users u ON u.id = c.user_id
ORDER BY c.created_at DESC LIMIT 5;
```

---

## S04 — Aarya Text Chat (Dashboard)  ✅ 🧪

> User types (or speaks) to Aarya. She reads their profile, searches jobs,
> scores matches, and can request intros — all in one chat thread.

**What's built:**
- `/dashboard` — Jack & Jill layout (chat + right icon rail)
- `ChatInterface.tsx` — SSE streaming, option cards, mic button
- LangGraph Aarya agent with tools: `profile_read`, `job_search`, `get_match_score`, `request_intro`, `direct_apply`
- Session lazy-creation (chat works even before session is established)
- Right rail: Home · Inbox · Profile · Jobs · Coaching

**How to test:**
```
1. Complete S01–S03
2. Open /dashboard
3. Type: "Hi Aarya, what jobs match my profile?"
4. Aarya should read profile + call job_search tool + stream a response
5. Try the mic button (Chrome/Edge) — speak a message
```

**Model:** `anthropic/claude-opus-4.7` via OpenRouter (already configured)

**Env needed (already set):**
```
OPENROUTER_API_KEY=sk-or-v1-770a06...
OPENROUTER_PRIMARY_MODEL=anthropic/claude-opus-4.7
```

**DB check:**
```sql
SELECT c.id, c.title, c.message_count FROM public.conversations c
JOIN public.candidates ca ON ca.id = c.candidate_id ORDER BY c.created_at DESC LIMIT 5;
```

---

## S05 — Voice Chat (15-min Aarya Session)  ✅ 🧪

> User taps the phone icon → `/voice` page.
> Aarya speaks to them, they reply by voice.
> Same Aarya agent as text chat. STT runs via Deepgram for reliability.

**Architecture (Deepgram STT + browser TTS):**
```
Mic → MediaRecorder → /api/v1/voice/stt (Deepgram Nova-3, language=multi) → text
      → OpenRouter claude-opus-4.7 → streamed reply text → SpeechSynthesis → speaker
```

**What's built:**
- `/voice` page with animated waveform UI
- `useVoice.ts` — MediaRecorder → Deepgram STT (server-side) + SpeechSynthesis TTS
- Conversation loop (listen → stream → speak → repeat)
- On session end → `POST /api/v1/voice/sessions` → unlocks `/matches` gate

**How to test:**
```
1. Add `DEEPGRAM_API_KEY` to `api/.env` and restart API
2. Open /voice in Chrome or Edge
3. Tap the mic button
4. Say: "Hi Aarya, I'm a senior software engineer looking for roles in Bengaluru"
5. Aarya should respond via speaker
6. Have a short conversation, then tap End
7. Should redirect to /dashboard
```

**DB check (should unlock /matches):**
```sql
SELECT vs.status, vs.duration_secs FROM public.voice_sessions vs
JOIN public.candidates c ON c.id = vs.candidate_id ORDER BY vs.created_at DESC LIMIT 3;
```

---

## S06 — Resume Upload + Parsing  ✅ 🧪

> User uploads PDF/DOCX → Affinda parses it → profile auto-filled.
> Uploading a resume also unlocks `/matches` (alternative to voice session).

**What's built:**
- `ResumeUpload.tsx` component (drag-drop + file picker)
- `POST /api/v1/resumes/upload` → Affinda parse → updates `candidates` row
- `resumes` table row → triggers `/matches` gate unlock

**How to test:**
```
1. Dashboard → MatchesGate → "Upload your resume" card
2. Upload a real PDF resume
3. Check /matches page — should be unlocked now
4. Check profile is auto-filled
```

**Note:** Affinda key not in env yet — check if `AFFINDA_API_KEY` is set or if the route uses a stub.

**DB check:**
```sql
SELECT r.id, r.parsed_at, c.headline, c.skills
FROM public.resumes r JOIN public.candidates c ON c.id = r.candidate_id
ORDER BY r.created_at DESC LIMIT 3;
```

---

## S07 — Job Ingestion (Apify Scrapers)  🔑 Needs Apify token

> Automated job scraping from LinkedIn, Naukri, Instahyre.
> Without this, the jobs table is empty and matches return nothing.

**What's built:**
- Apify actor config for LinkedIn India + Naukri scraping
- `POST /api/v1/admin/jobs/ingest` — trigger a run
- `jobs` + `companies` tables with dedup

**To enable:**
```
1. Go to apify.com → Create account → Settings → Integrations → API token
2. Add to api/.env:
   APIFY_TOKEN=apify_api_YOUR_REAL_TOKEN
3. Restart API
4. Trigger: POST http://localhost:8000/api/v1/admin/jobs/ingest
   with admin auth header
5. Wait ~5 mins, check jobs table
```

**DB check:**
```sql
SELECT COUNT(*) as total_jobs, COUNT(DISTINCT company_id) as companies
FROM public.jobs WHERE is_active = true AND deleted_at IS NULL;
```

**Why this matters:** S08, S09 (match feed) produce zero results until jobs are ingested.

---

## S08 — Embeddings + Matching Engine  ✅ 🧪 (needs S07 first)

> Every job and candidate profile gets a vector embedding.
> Cosine similarity via pgvector → `match_scores` table.

**What's built:**
- `services/embeddings.py` — text-embedding-3-small via OpenRouter
- `services/matching.py` — cosine similarity scoring pipeline
- `POST /api/v1/admin/matches/recompute` — trigger full recompute
- HNSW index on `job_embeddings` + `candidate_embeddings`

**How to test:**
```
1. Complete S07 (jobs in DB)
2. Complete S06 (resume uploaded + parsed)
3. Trigger: POST /api/v1/admin/matches/recompute
4. Check match_scores table has rows
```

**DB check:**
```sql
SELECT COUNT(*) FROM public.match_scores ms
JOIN public.candidates c ON c.id = ms.candidate_id
WHERE ms.score > 0.6;
```

---

## S09 — Job Match Feed UI  ✅ 🧪 (needs S07 + S08 first)

> Candidate sees their top job matches ranked by score.
> Three actions per card: Request Intro · Direct Apply · Save for Later.

**What's built:**
- `/matches` page with access gate (resume OR voice session required)
- `MatchesGate.tsx` — shows unlock paths if not yet unlocked
- `MatchesClient.tsx` — job feed with `JobCard` components
- 3-action cards with match % score

**How to test:**
```
1. Complete S06 or S05 (unlock gate)
2. Open /matches
3. Should see ranked job cards with % scores
4. Tap "Request Intro" on a card
```

**Gate check:**
```sql
-- User is unlocked if either of these returns a row:
SELECT id FROM public.resumes WHERE candidate_id = '<your_candidate_id>';
SELECT id FROM public.voice_sessions WHERE candidate_id = '<your_candidate_id>' AND status = 'completed';
```

---

## S10 — Hiring Manager Enrichment  ✅ 🧪 (needs S07 first)

> For each job, find the hiring manager's verified email.
> Required before Nitya can send intro emails.

**What's built:**
- Apify waterfall: LinkedIn → Apollo → Hunter → RocketReach
- NeverBounce email verification
- `hiring_managers` table + `hm_emails` enrichment

**To enable:**
```
NEVERBOUNCE_API_KEY=secret_YOUR_REAL_KEY  ← neverbounce.com (free tier: 1000/mo)
```

**Note:** Apify token (S07) also covers HM enrichment actors.

---

## S11 — Gmail OAuth + Intro Emails (Nitya)  🔑 Needs Google OAuth app

> Candidate connects their Gmail.
> When they "Request Intro" → Nitya drafts + sends a warm intro email
> **from the candidate's own Gmail** to the hiring manager.

**What's built:**
- `GET /api/v1/gmail/auth` → Google OAuth consent screen
- `GET /api/v1/gmail/callback` → stores refresh token in `user_gmail_tokens`
- Nitya agent: reads intro context → drafts email → sends via Gmail API
- Intro DB state machine: `pending` → `sent` → `responded`

**To enable:**
```
1. console.cloud.google.com → New project → APIs & Services → OAuth 2.0 Client
2. Scopes: gmail.send + gmail.readonly
3. Redirect URI (add **both** in Google Cloud Console → Credentials → OAuth client):
   - `http://localhost:8000/api/v1/gmail/callback` (local)
   - `https://hireloop1-app.vercel.app/hireloop-api/api/v1/gmail/callback` (production)
4. Railway env:
   - `PUBLIC_APP_URL=https://hireloop1-app.vercel.app`
   - Optional: `PUBLIC_API_URL=https://hireloop1-app.vercel.app/hireloop-api`
   - `GOOGLE_CLIENT_ID=...` and `GOOGLE_CLIENT_SECRET=...`
5. Restart API
```

**How to test:**
```
1. GET /api/v1/gmail/auth (logged in as candidate)
2. Complete Google OAuth
3. Request intro from a job card
4. Check intro_requests table + sent email in Gmail Sent
```

**⚠️ Critical rule (R9):** Intro emails MUST go via candidate's Gmail OAuth.
Never use SendGrid for cold/unsolicited intro emails.

---

## S12 — Intros Inbox  ✅ 🧪

> Candidate sees all their intro requests and their status.
> Notification dot on the right rail "Inbox" when there are pending items.

**What's built:**
- `/intros` page listing all intro requests
- `GET /api/v1/intros` — paginated list with status
- Dashboard right rail inbox dot (polls every 30s)

**How to test:**
```
1. Complete S11 (request at least one intro)
2. Open /intros
3. Should see intro with status "pending" → "sent" after Nitya fires
```

---

## S13 — Mock Interview  ✅ 🧪

> Candidate can practice interviews in text or voice.
> Aarya acts as interviewer, gives STAR-method feedback.

**What's built:**
- `/mock-interview` — session creation, chat interface, feedback card
- `POST /api/v1/mock-interview/sessions` → multi-turn LLM interviewer
- Feedback JSON saved on session end
- Works with voice (browser STT/TTS) or text

**How to test:**
```
1. Dashboard → right rail "Coaching" → /mock-interview
2. Select role: "Senior Software Engineer"
3. Type or speak answers
4. Say "I want to stop" → get feedback summary
```

---

## S14 — Tailored Resume per JD  ✅ 🧪

> One click from a job card → Aarya rewrites the resume to match that JD.
> Output is an HTML page, downloadable for print-to-PDF.

**What's built:**
- "Tailor Resume" action on job cards
- `POST /api/v1/tailored-resumes/tailor` → background LLM task (~30s)
- `GET /api/v1/tailored-resumes/tailored/{id}/download` → HTML

**How to test:**
```
1. Open /matches → pick a job card → "Tailor Resume"
2. Wait ~30s
3. Download the HTML → open in browser → print to PDF
```

---

## S15 — WhatsApp Notifications  🔑 Needs MSG91 + Meta approval

> Aarya pings the candidate on WhatsApp when a new top match appears,
> or when an intro gets a response.
> Candidate controls what they receive in /settings.

**What's built:**
- `POST /api/v1/webhooks/msg91-whatsapp` — inbound webhook
- Outbound notification on new `match_scores` row > 0.75
- `whatsapp_messages` table + `consent_log` writes
- `/settings` notification preference toggles

**To enable:**
```
1. msg91.com → Create account → WhatsApp → Register number
2. Submit templates to Meta for approval (~2 weeks)
3. Add to api/.env:
   MSG91_AUTH_KEY=your-key
   MSG91_WHATSAPP_NUMBER=+91XXXXXXXXXX
```

---

# RECRUITER JOURNEY

---

## S16 — Recruiter Signup + Role Creation  ✅ 🧪

> Hiring manager signs up (LinkedIn), creates a role.
> Nitya asks questions to build a structured hiring brief.

**What's built:**
- `role = 'recruiter'` → redirected to `/recruiter` after login
- `/recruiter/roles/new` — role creation form
- `/recruiter/roles/{id}/intake` — Nitya intake chat

**How to test:**
```
1. Sign up with a different LinkedIn account
2. In DB: UPDATE public.users SET role = 'recruiter' WHERE email = 'your@email'
3. Re-login → should land on /recruiter
4. Create a new role → chat with Nitya → brief should be saved
```

---

## S17 — Candidate Pipeline (Kanban)  ✅ 🧪

> Recruiter sees matched candidates in a drag-drop kanban.
> Stages: Matched → Screened → Interview → Offer → Hired.

**What's built:**
- `/recruiter/roles/{id}/pipeline` — kanban board
- Drag stage → `role_pipeline.stage` updated in DB
- `Hired` column → creates `placements` row (for fee tracking)

---

## S18 — Recruiter Inbox + Nitya Chat  ✅ 🧪

> Recruiter can chat with Nitya about candidates and pipeline.
> `/recruiter/inbox` shows intro request threads.

---

# PLATFORM

---

## S19 — Admin Panel + DPDP Compliance  ✅ 🧪

> Internal dashboard for Hireschema team.
> DPDP Act: candidates can export or delete their data.

**What's built:**
- `/admin` — stats, bias audit, placements
- `GET /api/v1/me/dpdp/export` → JSON data dump
- `DELETE /api/v1/me` → soft-delete + 30-day purge schedule
- Bias audit report (gender/location distribution of match scores)

**How to test:**
```
1. In DB: UPDATE public.users SET role = 'admin' WHERE email = 'your@email'
2. Re-login → /admin
3. Test export: GET /api/v1/me/dpdp/export (should download JSON)
4. Test delete: DELETE /api/v1/me (careful — soft delete only)
```

---

## S20 — Transactional Email (SendGrid)  🔑 Needs SendGrid key

> System emails: signup confirmation, match alerts, interview reminders.
> NOT for cold outreach (that goes via Gmail OAuth — see S11).

**To enable:**
```
1. sendgrid.com → Create account → Settings → API Keys → Full Access key
2. Verify sender domain: noreply@hireschema.com
3. Add to api/.env:
   SENDGRID_API_KEY=SG.your-real-key
4. Create templates and add IDs to api/.env:
   SG_TEMPLATE_SIGNUP_CONFIRMATION=d-xxx
   SG_TEMPLATE_JOB_MATCH_ALERT=d-xxx
   SG_TEMPLATE_INTERVIEW_REMINDER=d-xxx
   SG_TEMPLATE_INTRO_STATUS=d-xxx
```

---

## S21 — Programmatic SEO (Marketing Site)  ✅ 🧪

> `/jobs/[role]-jobs-in-[city]` static pages — 5000+ target.
> Drives organic traffic from Google India job searches.

**What's built:**
- `web/src/app/jobs/[slug]/page.tsx` — dynamic route
- `generateStaticParams()` → ROLES × CITIES matrix
- Sitemap generation

**How to test:**
```
1. cd web && pnpm build
2. Check .next/static — should see /jobs/* pages
3. pnpm start → open http://localhost:3000/jobs/software-engineer-jobs-in-bangalore
```

---

## S22 — Infrastructure Deployment  🔲 Not started

> Production hosting on AWS ap-south-1 (Mumbai) for India latency.

**Steps:**
```
1. Cloudflare → add hireschema.com domain → rate limits + security headers
2. AWS ap-south-1:
   - ECS Fargate: hireloop-api (FastAPI, 2 vCPU / 4 GB)
   - ECS Fargate: hireloop-app (Next.js, 1 vCPU / 2 GB)
   - RDS or keep Supabase (already cloud)
3. GitHub Actions CI/CD:
   - Push to main → build Docker image → push ECR → ECS rolling deploy
4. DNS:
   - hireschema.com → ECS app service
   - api.hireschema.com → ECS API service
5. Update .env:
   NEXT_PUBLIC_API_URL=https://api.hireschema.com
   ALLOWED_ORIGINS=https://hireschema.com
```

---

## S23 — Payments  ⏸ Deferred to v2

> Razorpay subscription for candidates (premium match features).
> For MVP: track placements manually in `/admin/placements`.

---

# COMPLETE CHECKLIST (copy this for sprint planning)

```
CANDIDATE FLOW
[ ] S01  LinkedIn signup — test with real LinkedIn account
[ ] S02  Phone OTP — test with real +91 number (Twilio already set)
[ ] S03  Onboarding wizard — complete all 5 steps
[ ] S04  Aarya text chat — send messages, check tools fire (profile_read, job_search)
[ ] S05  Voice chat — Chrome, speak 3+ turns, check voice_sessions row
[ ] S06  Resume upload — upload PDF, check candidates.skills populated
[ ] S07  Job ingestion — ADD APIFY_TOKEN, trigger ingest, check jobs count
[ ] S08  Embeddings + matching — trigger recompute, check match_scores
[ ] S09  Match feed — open /matches, see job cards with % scores
[ ] S10  HM enrichment — ADD NEVERBOUNCE_API_KEY, check hiring_managers rows
[ ] S11  Gmail OAuth — CREATE GOOGLE OAUTH APP, connect Gmail, send test intro
[ ] S12  Intros inbox — check /intros shows sent intros
[ ] S13  Mock interview — complete a session, verify feedback JSON saved
[ ] S14  Tailored resume — tailor one resume, download HTML
[ ] S15  WhatsApp — ADD MSG91 KEY, wait for Meta approval, test notification

RECRUITER FLOW
[ ] S16  Recruiter signup — set role=recruiter in DB, complete Nitya intake
[ ] S17  Pipeline kanban — drag candidate through stages
[ ] S18  Recruiter inbox — view intro threads

PLATFORM
[ ] S19  Admin panel — set role=admin, check /admin loads
[ ] S20  SendGrid — ADD SENDGRID KEY, test signup confirmation email
[ ] S21  SEO build — pnpm build in web/, check /jobs/* pages exist
[ ] S22  Deploy to AWS ap-south-1 — (do last, after all tests pass)
```

---

## Keys Still Needed

| Key | Service | Priority | Get it from |
|-----|---------|----------|-------------|
| `APIFY_TOKEN` | Job ingestion + HM enrichment | 🔴 Critical | apify.com → Settings → API |
| `GOOGLE_CLIENT_ID/SECRET` | Gmail OAuth for intros | 🔴 Critical | console.cloud.google.com |
| `SENDGRID_API_KEY` | Transactional email | 🟡 High | sendgrid.com |
| `NEVERBOUNCE_API_KEY` | Email verification | 🟡 High | neverbounce.com (free: 1000/mo) |
| `MSG91_AUTH_KEY` | WhatsApp notifications | 🟢 Nice | msg91.com (+ Meta template approval ~2 weeks) |
| `SECRET_KEY` | API session security | 🔴 Before prod | `openssl rand -hex 32` |
| `SERVICE_SECRET` | Internal API auth | 🔴 Before prod | `openssl rand -hex 32` |

---

## Run Commands

```bash
# Apply DB schema (run once)
supabase db push

# API (FastAPI)
cd api && uvicorn hireloop_api.main:app --reload --port 8000

# Candidate + Recruiter + Admin app
cd app && pnpm dev   # → http://localhost:3001

# Marketing SEO site
cd web && pnpm dev   # → http://localhost:3000
```

## Dev Test Accounts

| Email | Password | Role |
|-------|----------|------|
| candidate@test.hireschema.com | hireloop-dev-2026 | candidate |
| recruiter@test.hireschema.com | hireloop-dev-2026 | recruiter |
| admin@test.hireschema.com | hireloop-dev-2026 | admin |
