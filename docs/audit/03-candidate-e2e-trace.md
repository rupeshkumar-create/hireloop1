# 03 — Candidate End-to-End Trace

Numbered path through code for a candidate from LinkedIn signup through Gmail intro send. “Implemented” means callable code paths exist; PHASE_TRACKER still marks many steps as untested with real keys.

```mermaid
sequenceDiagram
  participant U as Candidate Browser
  participant SB as Supabase Auth
  participant App as Next.js app
  participant API as FastAPI
  participant PG as Postgres
  participant OR as OpenRouter
  participant Apify as Apify
  participant Nitya as NityaWorker
  participant Gmail as Gmail API

  U->>App: Continue with LinkedIn
  App->>SB: signInWithOAuth linkedin_oidc
  SB-->>U: OAuth redirect
  U->>App: /auth/callback?code=
  App->>SB: exchangeOAuthCodeOnce
  App->>API: POST /auth/bootstrap
  API->>PG: users + candidates INSERT/UPDATE
  App->>U: /onboarding
  U->>API: POST /resumes/upload
  API->>PG: resumes INSERT; enqueue RESUME_PARSE
  U->>API: POST /me/complete-onboarding
  API->>PG: enqueue MATCH_EMBED_CANDIDATE, AARYA_AUTO_INGEST
  API->>OR: embeddings
  API->>Apify: Google Jobs scrape
  API->>PG: jobs + match_scores upsert
  U->>API: GET /matches
  U->>API: POST /intros
  API->>PG: intro_requests INSERT + NOTIFY
  PG-->>Nitya: LISTEN payload
  Nitya->>OR: draft_intro_email
  Nitya->>PG: status draft_ready
  U->>API: POST /intros/{id}/approve-send
  API->>Gmail: send_intro_email
  API->>PG: status sent
```

---

## 1. LinkedIn OAuth signup

| | |
|---|---|
| **UI** | `/signup` → `app/src/components/auth/SignupForm.tsx:handleLinkedInSignIn` (~142–167) |
| **Auth** | `supabase.auth.signInWithOAuth({ provider: "linkedin_oidc", scopes: "openid profile email" })` |
| **Callback** | `app/src/app/auth/callback/AuthCallbackClient.tsx` (~33–125): `exchangeOAuthCodeOnce` then `finishAuthSession` |
| **API** | `POST /api/v1/auth/bootstrap` → `routes/auth.py:bootstrap_user` (~236–474) |

**DB writes:** `_provision_user_row`; `UPDATE users.role`; `_ensure_candidate_row`; `UPDATE candidates.linkedin_data` / `linkedin_url`; optional `consent_log` (`profile_creation`).

**DB reads:** Existing candidate/recruiter; LinkedIn metadata helpers in `services/linkedin_oauth.py`.

**External:** Supabase Auth (LinkedIn OIDC); `ensure_oauth_email_confirmed` (Admin API); welcome email via transactional path (Resend/SendGrid).

**Failure:** Provider error → signup query error; code exchange fail → error card; bootstrap timeout/5xx → `bootstrap_failed`. LinkedIn Apify enrichment is deferred until post-consent (`auth.py` ~420–421).

**Progress UX:** “Finishing LinkedIn sign-in…” — single round-trip; **no Realtime**. Destination: `resolvePostAuthDestination` → new user `/onboarding`, returning `/dashboard` (`post-auth-destination.ts`).

---

## 2. Onboarding — CV upload, parsing, preferences

| | |
|---|---|
| **UI** | `/onboarding` → `OnboardingFlow.tsx` Activation step (~183–257) |
| **Client helper** | `app/src/lib/api/onboardingProfile.ts:uploadResumeAndApply` (~115–154) |

**Sequence:**

1. `POST /api/v1/resumes/upload` — `routes/resumes.py` (~523–661): validate MIME/size; `_quick_parse_resume`; upload Supabase Storage `resumes`; `INSERT resumes`; enqueue `RESUME_PARSE`.
2. If `parse_status === "pending"`: poll `GET /resumes/{id}` every **2s**, timeout **120s**.
3. `POST /resumes/{id}/apply-to-profile?mode=replace` (~697–858): `UPDATE candidates`; `consent_log`; enqueue `RESUME_EMBED_SCORE`, `MATCH_EMBED_CANDIDATE`, `CAREER_INTELLIGENCE_UPDATE`, `CAREER_PATH_UPDATE`, `AARYA_AUTO_INGEST`.
4. `POST /me/onboarding-consent` — `me.py` (~1678–1810): consent rows; optional LinkDAPI `asyncio.create_task`.
5. Preferential `PATCH /me/profile` with `looking_for` if parse has title.
6. `POST /me/complete-onboarding` (~1813–1979): requires ToS consent; forces `market='IN'`; sets `onboarding_complete`; enqueue embed/ingest; returns `starter_jobs` from `fetch_instant_shelf`.

**External:** Supabase Storage; OpenRouter for full LLM/vision parse (`resume_parser.py` via background job); optional LinkDAPI.

**Failure:** Upload rate-limit/validation → HTTP error; apply-to-profile non-409 failures ignored client-side (best-effort); complete-onboarding blocked without consent.

**Progress UX:** Spinner/errors in ActivationStep; resume = **HTTP polling** if pending; redirect `/dashboard?kickoff=career`.

---

## 3. Profile embedding

| | |
|---|---|
| **Jobs** | `MATCH_EMBED_CANDIDATE`, `RESUME_EMBED_SCORE` |
| **Handler** | `background_jobs._handle_match_embed_candidate` / `_handle_resume_embed_score` (~507–531) |
| **Core** | `services/embeddings.py:EmbeddingService.embed_candidate` (~140–254) |

**DB read:** candidate + primary resume text.
**External:** OpenRouter `POST .../embeddings` (`openai/text-embedding-3-small`).
**DB write:** upsert `candidate_embeddings` (profile/skills/resume vectors).

**Failure:** OpenRouter **402** → log + skip vectors; scoring continues lexically.

**Progress UX:** Silent background — no user indicator.

---

## 4. Job ingest trigger

| Trigger | Path |
|---|---|
| Onboarding / apply-to-profile | enqueue `AARYA_AUTO_INGEST` |
| Thin feed | `routes/matches.py` (~504–526) if &lt;20 active `google_jobs` |
| Find new | `POST /matches/find-new` (~1946–2007) |
| Handlers | `background_jobs._handle_aarya_auto_ingest` → `aarya/tools.py:_auto_ingest_for_candidate` (~657–733) |

**External:** Apify `JobIngester.ingest_for_candidate` → `johnvc/Google-Jobs-Scraper`.
**DB:** upsert `jobs` / `job_sources` / `job_ingest_runs`; then embed+score.

**Failure:** Logged `aarya_auto_ingest_failed` — not user-facing. Empty-search auto-ingest default **false** (`config.auto_ingest_on_empty_search`).

**Progress UX:** Chat may stream tool labels via **SSE** when session attached; bare background ingest silent.

---

## 5. Scoring

| | |
|---|---|
| **Core** | `MatchingEngine.score_candidate` — `services/matching.py` (~1029+) |
| **Assemble** | `_assemble_score` (~571–689) |

**DB:** Read candidate + active jobs with pgvector cosines; upsert `match_scores` (+ `bias_audit`); delete weak pairs via `should_persist_match` (`match_quality.py`).

**External:** None in score path (uses stored embeddings).

**Failure:** Empty pool → scored=0; missing embeddings → lexical blend only. Batch path uses `notify=False`.

---

## 6. Matches feed render

| | |
|---|---|
| **API** | `GET /api/v1/matches` — `routes/matches.py` (~435+) |
| **UI** | `app/src/components/jobs/MatchFeed.tsx` (~213–278); `lib/api/matches.ts` |

**Behavior:** Load from `match_scores` JOIN `jobs`; quality gates; may enqueue ingest/embed; first screen uses RRF+MMR (`ranking.assemble_first_screen`).

**Progress UX:** Client cache + background refresh; skeletons; **not** Realtime on `match_scores`. Empty + high `min_score` retries with floor `0.25`.

---

## 7. “Request Intro” → `intro_requests` row

| | |
|---|---|
| **UI** | `DashboardClient.handleRequestIntro` (~371–396); chat cards |
| **Client** | `createCandidateIntro` — `lib/api/intros.ts` |
| **API** | `POST /api/v1/intros` → `intro_service.create_candidate_intro` (~248–433) |
| **Alt** | Aarya tool `request_intro` → same service |

**Resolution branches:**

1. Job has `recruiter_id` → `direction='candidate_to_recruiter'`, `status='pending'` (inbox; **no** Nitya Gmail).
2. Known HM email → `candidate_to_hm` + `_enqueue_nitya_intro` (`NITYA_INTRO_DRAFT`).
3. Else → stub HM + enrich path.

Also: `ensure_saved_job`; candidate confirmation notification.

**DB trigger:** `AFTER INSERT` → `pg_notify('intro_requests', …)` (`20240101000300_intros_and_hm.sql`, updated in two-sided intros migration).

**Progress UX:** Chat message + `introWatch`; **Supabase Realtime** on `intro_requests` (`IntrosList.tsx` ~80–89, `IntrosInboxPanel.tsx` ~92–106).

---

## 8. Nitya pickup → draft → approve-send → Gmail

### Pickup (dual path)

1. **LISTEN:** `NityaWorker` (`agents/nitya/agent.py` ~233–318) on channel `intro_requests`.
2. **Durable:** `_handle_nitya_intro_draft` (`background_jobs.py` ~670+) — recovers missed NOTIFY.

### Draft pipeline — `NityaIntroHandler.handle` (~91–227)

- Skips non-`candidate_to_hm` (in-app flows).
- `lookup_intro_request` → `enrich_hiring_manager` (Apify + NeverBounce) → `draft_intro_email` (OpenRouter).
- Sets `status='draft_ready'`, stores `draft_email` JSON (`nitya/tools.py` ~255–259).
- **Does not send** — waits for candidate approve.

### Approve + send

- `POST /intros/{id}/approve-send` — `intros.py:approve_and_send_intro` (~230–311).
- `claim_intro_for_send` → `status='sending'`.
- `send_intro_email` → `GmailOAuthService.send_intro_email` (candidate Gmail OAuth).
- Success → `status='sent'` + Gmail message/thread IDs; failure → release claim / 502.

**External:** Apify, NeverBounce, OpenRouter, Gmail API.

**Progress UX:** Realtime status (`pending` → enriching/drafting → `draft_ready` → `sending` → `sent`); Gmail-connect messaging if token missing.

---

## Discrepancies

1. Nitya system prompt still says “Send via the candidate's Gmail” as step 4 of activation (`NITYA_SYSTEM_PROMPT`); actual handler **stops at `draft_ready`** — send is approve-send HTTP.
2. Onboarding often returns quick-parse `ready` so client **skips** full-parse poll even while `RESUME_PARSE` continues in background.
3. PHASE_TRACKER: LinkedIn signup / Gmail / Apify steps marked 🧪 or 🔑 — not certified E2E in prod.

---

## Unverified — needs human confirmation

1. Live LinkedIn OIDC provider settings in Supabase dashboard.
2. Whether Gmail OAuth consent screen is verified / in testing mode (affects send).
3. Whether NeverBounce + Apify HM actors are funded in the production Railway env.
