# 12 — Rebrand Checklist

Every place current product branding, agent names, domains, colors, and sender identity appear. Use as a change list for a full rename.

**Current public product name in UI/docs:** predominantly **Hireschema**
**Legacy code/infra names:** **Hireloop** / `hireloop_*` / `hireloop-api` / Vercel `hireloop1-*`

---

## Product name & package identity

| Location | What to change |
|---|---|
| Root `package.json` | Package name `hireschema` |
| `README.md`, `CLAUDE.md`, `AGENTS.md`, `.cursorrules`, `HIRELOOP_MVP.md`, `PHASE_TRACKER.md`, `DEMO_RUNBOOK.md`, `DESIGN.md`, `LOCAL_TESTING.md`, `SUPABASE_CLOUD_SETUP.md`, `KEYS_AND_UNLOCKS.md` | Product naming throughout |
| `api/src/hireloop_api/` | **Entire Python package path** `hireloop_api` → new module name (imports, Dockerfile CMD, Railway, tests) |
| `api/pyproject.toml` | Package metadata |
| FastAPI title | `main.py` — `title="Hireschema API"`, description with Aarya/Nitya |
| Health service name | `routes/health.py` (service identity strings) |
| Cron job names | `hireloop_job_ingest_nightly`, `hireloop_embed_*`, etc. in SQL migrations / live Supabase cron |
| API proxy path | `/hireloop-api` — `app/next.config.mjs`, `app/src/lib/api/base-url.ts`, `api/.env.example` `PUBLIC_API_URL` |
| Vercel project ids | `hireloop1-app` (dashboard + `.vercel/project.json`) |
| Railway service | `hireloop1` / hostname docs in `.env.example` |
| Repo folder / git remote | `hireloop-app` (optional org rename) |

---

## Agent names (Aarya / Nitya)

| Location | Notes |
|---|---|
| `api/src/hireloop_api/agents/aarya/agent.py` | `AARYA_SYSTEM_PROMPT`, `AARYA_VOICE_PROMPT` — “Aarya”, “Hireschema” |
| `api/src/hireloop_api/agents/nitya/agent.py` | `NITYA_SYSTEM_PROMPT` — “Nitya”, “Hireschema” |
| `api/src/hireloop_api/agents/nitya/recruiter_chat.py` | `NITYA_RECRUITER_PROMPT`, `NITYA_POST_BRIEF_PROMPT` |
| UI strings | Chat headers, empty states, intros — grep `Aarya`/`Nitya` under `app/src` |
| DB columns | `candidates.aarya_state`, `recruiters.nitya_state` — **schema rename costly**; prefer leave + map in UI |
| Job kinds / logs | `aarya_*`, `nitya_*` background job kind strings |
| OpenRouter headers | Nitya `X-Title: Hireschema - Nitya Recruiter AI`, `HTTP-Referer: https://hireschema.com` |

**Baked into stored data:** historical `agent_actions.action_type` / payloads, `conversations.agent` values (`aarya`/`nitya`), draft email HTML may contain agent/brand phrasing — **not fixed by config alone**.

---

## Domains & OAuth

| Location | Config / string |
|---|---|
| Production app | `https://www.hireschema.com`, `https://hireschema.com` |
| Middleware redirects | `app/src/middleware.ts` host handling |
| `ALLOWED_ORIGINS` | `api/.env.example`, Railway env |
| Gmail redirect | `https://www.hireschema.com/hireloop-api/api/v1/gmail/callback` |
| Supabase Auth redirect URLs | Dashboard + docs `SUPABASE_CLOUD_SETUP.md` — `/auth/callback` |
| LinkedIn OAuth app | LinkedIn developer console redirect URLs / app name |
| Google Cloud OAuth consent screen | App name, homepage, privacy policy URLs → hireschema.com |
| Vercel preview | `hireloop1-app.vercel.app` |

---

## Email sender identity

| Key / module | Default |
|---|---|
| `RESEND_FROM_EMAIL` | `noreply@hireschema.com` (`config.py`, `.env.example`) |
| `SENDGRID_FROM_EMAIL` | `noreply@hireschema.com` |
| Lifecycle / transactional templates | `services/email/transactional.py`, `lifecycle_emails.py`, `notifications.py` — subjects/bodies may say Hireschema |
| Privacy contact | `privacy@hireschema.com` — `SettingsPanel.tsx`, `me.py` (~2214), footer/consent copy |
| MSG91 template name | `MSG91_WHATSAPP_OTP_TEMPLATE=hireloop_otp` (`.env.example`) |
| Local gitignored env | Historical `noreply@hireloop.in` / `Hireloop` (do not commit; clean local + providers) |

**DNS:** SPF/DKIM/DMARC for sender domain must move with brand — **provider dashboard**, not only code.

---

## Logo assets & UI components

| Path |
|---|
| `app/public/brand/hireschema-mark.svg` |
| `app/public/brand/email-logo.svg` |
| `app/public/brand/hireschema-assets.js` |
| `app/public/brand/svg/logo/*` (mark-lime, mark-charcoal, mark-white, lockups, app-icon) |
| `app/public/brand/svg/README.md` |
| `app/src/components/brand/HireschemaLogo.tsx` |
| `app/src/components/brand/HireLogo.tsx`, `HireIcon.tsx`, `icons.tsx`, `hireschema-icons.ts` |
| `web/` marketing assets / copy under `web/src/app/**` (page metadata, hero) |

---

## Brand colors

| Token | Value | Where |
|---|---|---|
| Charcoal ink | `#141414`, `#1C1C1C` | `app/src/app/globals.css` (~17–24), Tailwind theme |
| Lime accent | `#9FE870` | Same + brand SVGs (`mark-lime.svg`) |
| Tailwind brand tokens | `app/tailwind.config.ts`, `web/tailwind.config.ts` | Theme extension |
| DESIGN.md | Design language prose | Update with new palette |

---

## Metadata & public pages

| Surface | Files |
|---|---|
| App layout metadata | `app/src/app/layout.tsx` (title/description/OG) |
| Marketing pages | `web/src/app/**` — landing, about, pricing, candidates, recruiters, privacy, terms, contact |
| Public recruiter role | `app/src/app/r/[slug]/page.tsx` — any “Powered by” / brand |
| Public profile | `app/src/app/p/[slug]/**` |
| Sitemap/robots | `web/src/app/sitemap*`, `robots*` |
| Legal | Privacy/terms mentioning Hireschema + DPO email |

---

## Checklist — change matrix

### Config keys (env)

- [ ] `PUBLIC_APP_URL`, `PUBLIC_API_URL`, `ALLOWED_ORIGINS`
- [ ] `RESEND_FROM_EMAIL`, `SENDGRID_FROM_EMAIL` (+ provider domain verify)
- [ ] `GMAIL_OAUTH_REDIRECT_URI` + Google Cloud authorized redirects
- [ ] Supabase Site URL + redirect allow-list
- [ ] LinkedIn OAuth app branding + redirects
- [ ] `MSG91_*` template names / WhatsApp business display name
- [ ] OpenRouter `HTTP-Referer` / `X-Title` headers in agent constructors
- [ ] Sentry project name (optional)
- [ ] Vercel / Railway project display names

### Code / assets (must edit)

- [ ] Replace UI strings “Hireschema”, “Aarya”, “Nitya” (decide: rename agents or keep)
- [ ] System prompts in `aarya/agent.py`, `nitya/agent.py`, `recruiter_chat.py`
- [ ] Brand SVG/logo components under `app/public/brand` + `components/brand`
- [ ] CSS color tokens + Tailwind theme
- [ ] `/hireloop-api` path (coordinate Vercel rewrite + OAuth + docs)
- [ ] `hireloop_api` Python package rename (large blast radius)
- [ ] Cron job rename in Supabase (or leave internal names)

### External consoles

- [ ] Resend / SendGrid domain
- [ ] Google OAuth consent screen
- [ ] LinkedIn developer app
- [ ] MSG91 brand/templates
- [ ] DNS for new domain
- [ ] Apple/Google if PWA icons later

---

## Branding baked into stored data (not config)

| Data | Issue |
|---|---|
| `intro_requests.draft_email` HTML/text | May contain “sent via Hireschema/Aarya/Nitya” phrasing already generated |
| `messages` / chat history | Agent self-introductions by old name |
| `agent_actions` payloads | Historical tool labels |
| `conversations.agent` enum-like strings | `aarya` / `nitya` |
| Emails already sent via Gmail/Resend | Immutable in recipient inboxes |
| Seed/demo users | `*@test.hireschema.com`, password `hireloop-dev-2026` in `LOCAL_TESTING.md` |
| Consent / notification copy already accepted | Legal text snapshots in `consent_log` purpose strings may reference brand |

**Migration note:** Renaming agents/product in prompts does not rewrite history. Add a one-off data migration only if you need old drafts scrubbed; otherwise document as legacy.

---

## Discrepancies

1. Dual brand in repo: user-facing **Hireschema** vs engineering **Hireloop** paths (`hireloop_api`, `/hireloop-api`, cron `hireloop_*`, Vercel `hireloop1`).
2. Local gitignored env may still say Hireloop — not authoritative for prod but confuses operators.
3. Filename `HIRELOOP_MVP.md` vs product Hireschema.

---

## Unverified — needs human confirmation

1. Trademark / legal entity name on invoices and LinkedIn company page.
2. Whether Google/LinkedIn OAuth apps already show “Hireschema” or “Hireloop” on the consent screen.
3. Whether Resend domain `hireschema.com` is fully verified (SPF/DKIM) in production.
