# 08 — Auth & Security

Auth flows, OAuth scopes, secrets hygiene, public endpoints, prompt-injection surfaces, and resume storage ACL — as implemented.

---

## LinkedIn OAuth (users)

1. SPA `SignupForm.handleLinkedInSignIn` — `supabase.auth.signInWithOAuth({ provider: "linkedin_oidc", scopes: "openid profile email" })` (`app/src/components/auth/SignupForm.tsx`).
2. Redirect → `/auth/callback` — `AuthCallbackClient` exchanges PKCE code (`exchangeOAuthCodeOnce`).
3. `finishAuthSession` → `POST /api/v1/auth/bootstrap` persists role + `linkedin_data` (`routes/auth.py:bootstrap_user`).
4. Session: `@supabase/ssr` browser client (`app/src/lib/supabase/client.ts`, `detectSessionInUrl: false`); server `createClient` + middleware session refresh.

Phone OTP (+91 MSG91) is optional/settings — not required for signup (`routes/auth.py` OTP endpoints; `get_phone_verified_user` when `require_phone_verification=true`).

---

## Gmail OAuth (cold intros) + Google scopes

**Scopes requested** (`routes/gmail.py:48-51`):

```
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/gmail.send
https://www.googleapis.com/auth/calendar.events
```

Combined as `_GOOGLE_SCOPE`. Tests assert no `gmail.readonly` (`api/tests/test_google_oauth_scope.py`).

| Concern | Implementation |
|---|---|
| Connect URL | HMAC-signed `state` (user_id + ts), TTL 10 min (`sign_oauth_state`) |
| Callback | Unauthenticated by design; bound via signed state (`gmail.py` ~180–187) |
| Token storage | `public.gmail_tokens`, **encrypted** via `token_crypto` (`gmail_oauth.py:save_oauth_tokens`) |
| Refresh | Refresh when &lt;60s remaining (`gmail_oauth.py` ~76–116) |
| Send | `GmailOAuthService.send_intro_email` → Gmail API |
| Calendar | Same token store + `calendar.events` (`google_calendar.py`) |

### All Google OAuth scopes in app

Exactly the four above (openid + email + gmail.send + calendar.events). No broader Gmail or Drive scopes found.

LinkedIn scopes (via Supabase): `openid profile email` only at SPA call site.

---

## Supabase session handling in SPA

- Browser: anon key + cookie session (`createBrowserClient`).
- Middleware refreshes session (`app/src/middleware.ts`).
- API auth: `Authorization: Bearer <access_token>` validated in `deps.get_current_user` (Supabase Auth `/auth/v1/user` with service apikey).
- API base: browser uses `/hireloop-api` rewrite; `auth-fetch.ts` attaches Bearer.

---

## Hardcoded secrets / API keys

| Finding | Location | Status |
|---|---|---|
| Truncated OpenRouter key prefix | `PHASE_TRACKER.md` (~line 154, `sk-or-v1-770a06...`) | **Tracked in git** — treat as potential leak; rotate if real |
| Placeholder-only | `api/.env.example`, `app/.env.example`, `KEYS_AND_UNLOCKS.md` | OK |
| `api/.env`, `app/.env.local`, `.env.vercel.prod` | Local / gitignored (`.gitignore` `.env`, `.env.*`) | Not in `git ls-files` |
| `.railway/migration-*.json` | Gitignored per `.gitignore` | Dangerous if present on disk with real keys |

No wholesale committed production secrets found in application source. **PHASE_TRACKER key fragment is the clear tracked risk.**

---

## Endpoints with no / weak user auth

| Route | Auth model |
|---|---|
| `/api/v1/health`, `/health/ready` | Public |
| `/api/v1/health/deep` | `X-Service-Secret` |
| `/api/v1/markets` | Public |
| `/api/v1/jobs/ingest`, `/ingest/cron` | Service secret only |
| `/api/v1/matches/embed`, `/recompute` | Service secret |
| `/api/v1/gmail/callback` | Signed OAuth state (no Bearer) |
| `/api/v1/webhooks/msg91-whatsapp` | Service secret |
| `/api/v1/public/profiles/{slug}`, chat, `/roles/{slug}`, apply | Public / optional auth |

`.cursorrules` R16 claims only `/health`, `/markets`, `/auth/callback` are unauthenticated — **codebase is broader** (public profiles, deep health, cron ingest, gmail callback, webhooks).

---

## Prompt-injection surfaces

Untrusted text reaches LLMs with JSON/schema instructions but **no strong delimiter fencing / sanitizer**:

| Surface | Module |
|---|---|
| Resume parse (text/vision) | `services/resume_parser.py` |
| JD enrichment | `services/jd_enrichment.py` (~HumanMessage with description) |
| Aarya chat (user messages + profile) | `agents/aarya/agent.py` |
| Pasted JD tool | `analyze_pasted_jd` |
| Nitya draft (candidate/HM/company) | `agents/nitya/tools.py:draft_intro_email` |
| Public profile visitor chat | `services/public_profile_chat.py` (unauthenticated visitors) |
| Recruiter JD import extraction | `role_jd_fetch` / OpenRouter extract |
| Match rationale, mock interview, tailored resume, kits | respective services/routes |

Risk: resume contents, scraped JD HTML markdown, and public chat can instruct the model. Mitigations in code are weak (prompt wording only).

---

## Resume Storage access control

- Buckets private (`20240101000700_storage_buckets.sql`): `resumes`, `avatars`, `tailored-resumes`.
- Upload/read policies: object path folder must match `auth.uid()`.
- Service role SELECT on `resumes` for API parse workers.
- API upload uses service client (`routes/resumes.py`); worker download uses service key (`background_jobs.py`).
- Migration header mentions signed URLs (1h); product path predominantly service-role proxy rather than handing long-lived public URLs to clients.

---

## Discrepancies

1. R16 unauthenticated endpoint allow-list vs actual public surface.
2. Docs list SendGrid OTP email heavily; Resend is primary.
3. Nitya prompt says send without SendGrid; approve-send path is the actual gate.

---

## Unverified — needs human confirmation

1. Whether the `PHASE_TRACKER.md` OpenRouter prefix corresponds to a live key that needs rotation.
2. Google Cloud OAuth app verification status for `gmail.send` in production.
3. Supabase LinkedIn provider client secret rotation SOP.
4. Whether ClamAV virus scan (Phase 8+ in rules) is enabled anywhere — **not found in code**.
