# Supabase Cloud setup (Option B)

Use a **hosted Supabase project** for auth, Postgres, storage, and Realtime. Local `supabase start` is optional for DB-only work; this guide is the path for **cloud + local app/API**.

---

## 1. Create the project

1. Go to [https://supabase.com/dashboard](https://supabase.com/dashboard) → **New project**.
2. Region: pick **South Asia (Mumbai)** if available (aligns with R4 ap-south-1 intent).
3. Save the **database password** (needed for `supabase link`).

From **Project Settings → API**, copy:

| Key | Used in |
|-----|---------|
| **Project URL** | `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_URL` |
| **anon public** | `NEXT_PUBLIC_SUPABASE_ANON_KEY` (app only) |
| **service_role** | `SUPABASE_SERVICE_KEY` (api only — never in the browser) |

---

## 2. Link CLI and push migrations

From repo root:

```bash
supabase login
supabase link --project-ref <your-project-ref>
supabase db push
```

Optional dev seed (cloud **dev** project only, not production):

```bash
# Use connection string from Dashboard → Database → Connection string (URI)
psql "<postgres-uri>" -f scripts/seed_dev.sql
```

---

## 3. Auth URLs (Supabase Dashboard)

**Authentication → URL configuration**

| Setting | Local dev | Production (custom domain) |
|---------|-----------|---------------------------|
| Site URL | `http://localhost:3001` | `https://www.hireschema.com` |
| Redirect URLs | `http://localhost:3001/auth/callback`, `…/auth/callback?*`, `…/auth/confirm`, `http://localhost:3001/**` | `https://www.hireschema.com/auth/callback`, `…/auth/callback?*`, `…/auth/confirm`, `…/**` |

LinkedIn OAuth always redirects to `/auth/callback?signup_role=candidate|recruiter` so Job Seeker vs Recruiter survive the LinkedIn round-trip. Keep a wildcard (`/**` or `/auth/callback?*`) in the Redirect URLs allow-list — an exact `/auth/callback` alone can reject the query string.

Also keep Vercel preview URLs if you still deploy previews:

- `https://hireloop1-app.vercel.app/auth/callback`
- `https://hireloop1-app.vercel.app/auth/confirm`

**Do not use port 3000** (`web/` marketing) as Site URL. Auth runs on **`app/`** (port **3001** locally).
If Site URL is `http://127.0.0.1:3000`, LinkedIn redirects to the marketing homepage with `/?code=…` and sign-in fails.

Add `http://127.0.0.1:3001/auth/callback` if you browse the app as `127.0.0.1` (not `localhost`).

**Email sign-in links (important):** Default Supabase templates send users to
`supabase.co/auth/v1/verify` with a PKCE token that **only works in the same
browser** where you requested the link — it hangs in incognito/temp-mail tabs.
This repo ships token_hash templates that open your app directly:

```bash
python3 scripts/patch_supabase_email_templates.py
```

Or paste `supabase/templates/confirmation.html` and `magic_link.html` into
**Authentication → Email Templates** in the dashboard (Confirm signup + Magic link).
After updating, request a **new** sign-in email; old links still use the broken URL.

---

## 4. LinkedIn OIDC provider

**Authentication → Providers → LinkedIn (OIDC)**

1. Create a LinkedIn app at [https://www.linkedin.com/developers/](https://www.linkedin.com/developers/).
2. **Authorized redirect URL** (LinkedIn side):

   `https://<project-ref>.supabase.co/auth/v1/callback`

3. Paste **Client ID** and **Client Secret** into Supabase LinkedIn provider → Enable.

Signup flow in the app:

1. User picks **Job Seeker** or **Recruiter** → cookie `hireloop_signup_role`.
2. LinkedIn OAuth → `/auth/callback` exchanges code.
3. Callback calls `POST /api/v1/auth/bootstrap` with Bearer token → creates `candidates` or `recruiters` row.
4. Redirect to `/onboarding` → welcome + activate (CV, market, consent).

---

## 5. Storage buckets

Migrations create private buckets (`resumes`, `avatars`, `tailored-resumes`). After `db push`, confirm under **Storage** in the dashboard. No public buckets (R11).

---

## 6. Environment files (automated)

Fastest path — paste keys once, script writes both env files:

```bash
cp scripts/supabase-credentials.env.example scripts/supabase-credentials.env
# Edit supabase-credentials.env with Dashboard values
python3 scripts/configure_supabase.py
python3 scripts/verify_supabase_connection.py
```

Or set manually:

### `app/.env.local`

```env
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### `api/.env`

```env
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<password>@aws-0-ap-south-1.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
ALLOWED_ORIGINS=http://localhost:3001,http://localhost:3000
ENVIRONMENT=development
MSG91_AUTH_KEY=                              # optional in dev (OTP logged)
```

Use the **Transaction pooler** URI from Supabase (port 6543) for asyncpg.

---

## 7. Run locally

```bash
# Terminal 1 — API
cd api && uvicorn hireloop_api.main:app --reload --port 8000

# Terminal 2 — App
cd app && pnpm dev   # http://localhost:3001
```

**Smoke test (P04 auth)**

1. Open `http://localhost:3001/signup` → Continue with LinkedIn.
2. After redirect, `/onboarding` → upload CV, pick market, accept terms → `/dashboard`.
3. Optional: verify phone from Settings when MSG91/Twilio keys are configured.

API calls from the browser must send **`Authorization: Bearer <supabase_access_token>`** (handled by `apiAuthFetch` in the app).

---

## 8. What you must provide (checklist)

- [ ] Supabase project URL + anon + service_role keys
- [ ] `supabase db push` completed on cloud
- [ ] Auth redirect URLs for localhost (and prod when ready)
- [ ] LinkedIn OIDC app + Supabase provider enabled
- [ ] `api/.env` with `DATABASE_URL`, `SUPABASE_*`, `ALLOWED_ORIGINS`
- [ ] `app/.env.local` with `NEXT_PUBLIC_SUPABASE_*` and `NEXT_PUBLIC_API_URL`
- [ ] MSG91 key (production SMS; dev can use logged OTP)

---

## 9. Security reminders

- Never commit `.env` / `.env.local`.
- Never put `service_role` in the Next.js app.
- Cold email stays on **Gmail OAuth**, not SendGrid (R9).
- Multi-region marketplace: market-scoped jobs + phone verify per region (R4).

See also: `LOCAL_TESTING.md` (phase-by-phase tests), `PHASE_TRACKER.md`.

---

## 10. Vercel deploy (hireschema.com)

**Project settings** (Vercel dashboard → hireloop1-app → Settings → General):

| Setting | Value |
|---------|--------|
| Root Directory | `app` |
| Framework | Next.js |
| Install Command | `cd .. && pnpm install --no-frozen-lockfile` |
| Build Command | `pnpm build` |
| Domains | `www.hireschema.com` (primary), `hireschema.com` (apex → www redirect in `next.config.mjs`) |

**Environment variables** — add for **Production**, **Preview**, and **Development**:

| Variable | Production value |
|----------|------------------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | anon key from Dashboard |
| `NEXT_PUBLIC_API_URL` | `https://hireloop1-production.up.railway.app` |
| `NEXT_PUBLIC_APP_URL` | `https://www.hireschema.com` |
| `NEXT_PUBLIC_WEB_URL` | `https://www.hireschema.com` |
| `API_SERVICE_SECRET` | same as Railway `SERVICE_SECRET` |
| `NEXT_PUBLIC_DEMO_MODE` | `false` |
| `NEXT_PUBLIC_DEV_EMAIL_LOGIN` | `false` |

Without Supabase vars, `next build` used to fail on `/signup` prerender. The app now tolerates missing vars at build time, but **auth still requires real values at runtime**.

Also add production redirect URLs in Supabase Auth (see §3): `https://www.hireschema.com/auth/callback` and `…/auth/confirm`.

**Railway** (API) — update these when the custom domain goes live:

| Variable | Production value |
|----------|------------------|
| `ALLOWED_ORIGINS` | include `https://www.hireschema.com,https://hireschema.com,https://hireloop1-app.vercel.app` |
| `PUBLIC_APP_URL` | `https://www.hireschema.com` |
| `PUBLIC_API_URL` | `https://www.hireschema.com/hireloop-api` |
| `ENVIRONMENT` | `production` |

Smoke test after deploy:

```bash
./api/scripts/smoke_railway.sh
```

---

## 11. Google OAuth (Connect Google / Gmail intros)

`Error 400: redirect_uri_mismatch` means the redirect URI your API sends does not **exactly** match one listed in Google Cloud Console.

### Redirect URI (production)

After deploy, the API uses:

```text
https://www.hireschema.com/hireloop-api/api/v1/gmail/callback
```

(Requires Railway `PUBLIC_APP_URL=https://www.hireschema.com` and `ENVIRONMENT=production`.)

### Google Cloud Console steps

1. [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **Credentials**
2. Open your **OAuth 2.0 Client ID** (Web application) — same `GOOGLE_CLIENT_ID` as Railway
3. Under **Authorized redirect URIs**, add **exactly**:
   - `https://www.hireschema.com/hireloop-api/api/v1/gmail/callback`
   - `http://localhost:8000/api/v1/gmail/callback` (local dev)
4. **Save** — Google can take a few minutes to propagate
5. **OAuth consent screen**: if the app is in **Testing**, add `rupesh.kumar@candidate.ly` (and any test users) under **Test users**

### Railway env (must match)

| Variable | Value |
|----------|--------|
| `GOOGLE_CLIENT_ID` | from Google Console |
| `GOOGLE_CLIENT_SECRET` | from Google Console |
| `PUBLIC_APP_URL` | `https://www.hireschema.com` |
| `ENVIRONMENT` | `production` |

Optional override (only if you need a custom URI):

```text
GMAIL_OAUTH_REDIRECT_URI=https://www.hireschema.com/hireloop-api/api/v1/gmail/callback
```

### Verify

While logged in, open (returns the URI the API sends to Google):

```text
GET /api/v1/gmail/auth-url
```

The `redirect_uri` in the JSON must match a row in Google Console **character-for-character** (https, no trailing slash).
