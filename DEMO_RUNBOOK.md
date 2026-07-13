# Demo Runbook — showing the working loop

How to bring Hireschema up and walk the **candidate → match → intro → recruiter** loop.
Two tracks: a **zero-key demo** (works today) and the **full-key demo** (live jobs,
embeddings, voice, email). Companion: `KEYS_AND_UNLOCKS.md`.

---

## 0. Prerequisites (one-time)
```bash
# from repo root
supabase start            # local Postgres + auth (or point DATABASE_URL at your cloud)
supabase db push          # apply all migrations (incl. relocation, location_scope)

# api/.env — minimum to boot (see KEYS_AND_UNLOCKS.md §0)
#   DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY, SECRET_KEY, SERVICE_SECRET
#   SUPER_ADMIN_EMAILS=<your-login-email>   ← makes you admin
```
Run the three apps (separate terminals):
```bash
cd api  && uv run uvicorn hireloop_api.main:app --reload      # API  :8000
cd app  && corepack pnpm dev                                  # SPA  :3001
cd web  && corepack pnpm dev                                  # site :3000
```

---

## TRACK A — Zero-key demo (no Apify/OpenRouter/Gmail needed)

This proves the **core value loop** end-to-end using seeded jobs + lexical matching.

### A1. Seed jobs + score them
```bash
cd api
uv run python scripts/seed_sample_jobs.py        # India jobs into the feed
uv run python scripts/backfill_current_title.py   # fill current_title from résumés (if any)
uv run python scripts/recompute_matches.py        # build match_scores (lexical — no key)
```

### A2. Candidate journey (in the SPA, :3001)
1. **Sign up / log in** → upload a résumé (or use a seeded candidate).
2. **Chat with Aarya** — "find my best matches." Jobs render as cards.
3. **Jobs feed** — note the **tier-grouped first screen** (Strong / Good / Worth-a-look),
   confidence %, CTC in LPA. This is the curated, de-duplicated, hybrid-ranked screen.
4. **Profile chip** ("Profile X% complete") → opens the in-chat completion flow:
   - "Fill it in" → gamified form, **only asks the gaps** (skips what we already know).
   - Set **location scope** (city / state / country / global) and watch matches re-rank
     after `recompute_matches.py`.
5. **Tailor** on a job card → opens a **print-ready résumé** → browser "Save as PDF".
6. **Mock interview** → run a session → get the **scorecard** (score /10, strengths, gaps).

### A3. The intro loop (the MVP-critical bit) — needs a recruiter
1. Open a second session as a **recruiter** (role=recruiter). Create a role → Nitya
   intake chat → **publish role** (it's scored against candidates instantly).
2. As the **candidate**, that role now appears in the feed → **Request intro**.
3. As the **recruiter**, see it in the **Inbox** → **Accept** → a chat thread opens.
4. Back as the candidate: the intro shows **accepted** in the Inbox; message back and forth.
   → **This is the whole product in one loop, with zero external keys.**

### A4. Admin / observability (you, as admin)
- `/admin` → dashboard (users, jobs, intros), **bias-audit** samples (DPDP provenance),
  and `GET /api/v1/admin/observability` (agent action volume, latency, error-rate, funnel).
- Ops probes: `GET /api/v1/health` (liveness) and `/api/v1/health/ready` (deep, DB-checked).

---

## TRACK B — Full-key demo (live jobs, semantic match, voice, email)

Add keys to `api/.env` (see `KEYS_AND_UNLOCKS.md`), **restart the API**, then:

| Unlock | Keys | Command |
|---|---|---|
| **Live jobs** (P09) | `APIFY_TOKEN` + actor rented | `uv run python scripts/run_ingest.py --candidate <id>` |
| **Semantic matching** (P10) | `OPENROUTER_API_KEY` | `uv run python scripts/embed_all.py && uv run python scripts/recompute_matches.py` |
| **Candidate→HM intros** (P12/P13) | Apify + `GOOGLE_CLIENT_ID/SECRET` + `SENDGRID_API_KEY` | request an intro on a scraped job; Nitya enriches the HM and drafts from the candidate's Gmail |
| **Voice** (P15) | `DEEPGRAM_API_KEY` | use the mic in chat / the `/voice` call (falls back to browser speech without it) |
| **WhatsApp / OTP** (P19/P04) | `MSG91_AUTH_KEY` (paid) | phone verification + WhatsApp nudges |

---

## Talking points for the demo
- **Relevance is real, not theatre:** weighted composite (skills 0.40 / profile 0.30 /
  experience 0.15 / location 0.10 / CTC 0.05), lexical + title-affinity so it works before
  embeddings, **hybrid RRF fusion**, MMR diversity, cross-ATS de-dup, saved-job boost.
- **India-only & DPDP-compliant:** INR salaries (LPA), **no protected attributes in
  scoring** (every match carries a bias-audit), raw voice not stored.
- **Two agents, DB-only comms:** Aarya (candidate) + Nitya (recruiter) — no agent-to-agent RPC.
- **Quality bar:** 205 backend tests, typed APIs, RLS on every table, prod-secret boot guard.

## If something looks empty
- Feed empty → run `recompute_matches.py` (scores are batch-built).
- "Profile 0%" → generate Career Intelligence (auto-runs after résumé/LinkedIn) or fill the form.
- No jobs at all → `seed_sample_jobs.py` (Track A) or rent the Apify actor (Track B).
