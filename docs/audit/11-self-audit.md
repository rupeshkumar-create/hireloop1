# 11 — Self-Audit (Skeptical Senior Review)

Cold review. Not diplomatic. Every item cites code/docs divergence.

---

## TODOs and commented-out / dead surfaces

| Issue | Evidence |
|---|---|
| Fantastic / LinkedIn Jobs actor env still documented | `api/.env.example` (~78–84), `config.py` flags — **ignored** by `JobIngester` Google-only path |
| Affinda key in config, zero callers | `config.affinda_api_key` |
| `job_ingest_log` table + cleanup cron, no API writer | migrations `008` vs `job_ingest_runs` usage |
| README still “P01” + sibling `../hireloop/` paths | `README.md` ~69–83 |
| Ingester header “first startup” ingest | `job_ingester.py` docstring vs cron/queue reality |
| DESIGN_MIGRATION gradient kill list | Still has TODO grep notes — design debt |

Few classic `TODO`/`FIXME` markers in TS/Python (grep nearly empty) — debt is **doc/config zombies**, not sticker TODOs.

---

## Error paths that swallow exceptions

| Area | Behavior |
|---|---|
| Matches feed enrichment | Broad `except Exception` continue paths in `matches.py` (~197–231 area) |
| Lexical / vector search | Soft-fail continues in `job_lexical_search.py` / vector helpers |
| Auto-ingest | Failures only `warn` — `aarya/tools.py` (~732–733) |
| Resume apply-to-profile (client) | Non-409 failures ignored after upload (`onboardingProfile.ts`) |
| Per-row upsert | Warn + skip (`job_ingester.py` ~1361–1363) — OK for poison rows; opaque to ops |
| Firecrawl optional paths | Fail → fall back / skip without user signal |

Net: product stays up; **silent empty feeds** become the user experience when Apify/credits die.

---

## Race conditions

| Race | Detail |
|---|---|
| Cron idempotency vs stuck job | `job_ingest:cron` unique active key can **block nights** until 20m reclaim / fail |
| Find-new double enqueue | `AARYA_AUTO_INGEST` + `CAREER_PATH_INGEST` — duplicate Apify spend (`matches.py` ~1982–2007) |
| LISTEN vs durable Nitya | Advisory lock + retry — **good**; contention raises for retry (`background_jobs` Nitya handler) |
| Intro send claim | Conditional UPDATE to `sending` — **good** (`claim_intro_for_send`) |
| Concurrent scoring | `match_scores` UNIQUE(candidate,job) upserts — generally OK; no explicit distributed rate limit on score storms from cron + onboarding + search |
| Multi-replica workers | Config is 1 replica; if scaled, multiple LISTEN + pollers without leader election |

---

## Hardcoded values that should be config

| Value | Location |
|---|---|
| All MatchingEngine weights / gates / lifts | `matching.py` `_W_*`, cosine bands |
| Persist/feed floors 0.35 / 0.18 / 0.38 | `match_quality.py` |
| RRF `k=60`, MMR `λ=0.72`, company cap 2 | `ranking.py` |
| Ingest dedupe 24h, Apify poll 600s | `job_ingester.py`, `jobs_scraper.py` |
| Tool round budgets 1/3 | `aarya/agent.py` |
| Slow request 1000ms | `main.py` |
| Stuck job reclaim 20m | `background_jobs.py` |

---

## Unused / underused tables & columns

| Object | Issue |
|---|---|
| `job_ingest_log` | Schema + cron; no Python insert |
| Fantastic/LinkedIn actor settings | Dead config surface |
| Affinda | Dead config |
| `voice_sessions` | RLS on, **no policies** — SPA dashboard counts via Supabase always 0 |
| Occupation `role_id text` intent | Blocked by existing UUID `role_id` (`20260710230000` IF NOT EXISTS skip) |
| `match_feedback` | Written by triggers; **not** used to learn scores |
| culture/career fit metadata | Computed but not in `overall` |

---

## Docs claim vs code reality

| Doc claim | Reality |
|---|---|
| SendGrid transactional only | **Resend primary** |
| LinkedIn Jobs Scraper | **Google Jobs** actor |
| LangGraph for Nitya | Procedural + plain chat |
| AWS ECS + Cloudflare India ASN | **Vercel + Railway**; WAF TF incomplete |
| Tailwind 4 / claude-3-5-sonnet | Tailwind **3.4**; **claude-sonnet-4.6** |
| Public `/r/{slug}` apply form | Page routes to **signup**; API apply exists separately |
| Nitya sends on activate | Stops at **`draft_ready`** |
| R16 only 3 public endpoints | Many more public routes |
| PHASE S22 infra not started | Railway/Vercel configs already exist |
| ClamAV on upload (R11 Phase 8+) | **Not implemented** |

---

## Top 10 production-readiness fixes (by severity)

1. **Ingest freshness alerting + unblock cron** — No stale-ingest alert; stuck `job_ingest:cron` can silently starve feed for days. Add SLO on `job_ingest_runs.last_run_at` / `jobs.scraped_at` and page on failure. (`09`, `jobs.py`, cron SQL)

2. **Prove backups / restore drill** — No verified dump/restore. One bad migration = business risk. Confirm Supabase PITR and rehearse. (`10`)

3. **Rotate any leaked key material** — OpenRouter prefix in tracked `PHASE_TRACKER.md`; scrub docs; rotate. (`08`)

4. **Prompt-injection hardening** — Resume text, scraped JD, public `/p` chat, and Nitya draft all feed LLMs unsanitized. Fence + schema-only tools + refuse instruction overrides. (`08`)

5. **Workers in API process + single replica** — LISTEN + heavy ingest share HTTP process. Crash/restart takes down chat and Nitya together; scale-out duplicates workers. Extract workers or add leader election. (`main.py`)

6. **Gmail/OAuth production gates** — S11 marked 🔑 in PHASE_TRACKER; cold intro path is the product differentiator and depends on verified Google consent + encrypted tokens. End-to-end test before calling “live.”

7. **Apify/credits failure UX** — Auto-ingest swallows; OpenRouter 402 skips embeddings. Users see empty/weak feeds with no explanation. Surface status + admin alarms. (`aarya/tools.py`, `embeddings.py`)

8. **Auth surface honesty / protect public routes** — Expand R16 or harden rate limits / abuse controls on public profile chat and role apply. (`public_profiles.py`, `.cursorrules`)

9. **Matching constants unvalidated** — Floors/weights are guessed; `match_feedback` unused. Before scaling acquisition, define offline eval or you will burn Apify on junk cards. (`05`)

10. **Doc/config drift & dead actors** — Kill Fantastic/LinkedIn/Affinda surface; fix README/stack; wire or delete `job_ingest_log`. Drift causes wrong production changes under pressure.

---

## Discrepancies

This entire document *is* a discrepancy list against internal optimism. Highest narrative gap: decks/README still describe an AWS LinkedIn-Jobs SendGrid product; the repo runs a Vercel/Railway Google-Jobs Resend product with substantial untested keys.

---

## Unverified — needs human confirmation

1. Actual production traffic error rates in Sentry/Railway (may be empty because unused).
2. Whether founder demos rely on `NEXT_PUBLIC_DEMO_MODE` mock paths (R15) masked as real.
3. Real Apify/OpenRouter spend vs empty-feed incidents in the last 30 days.
