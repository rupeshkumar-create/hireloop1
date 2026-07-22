# Hireschema Technical Audit — Index

Leadership-facing code audit produced from the repository at `hireloop-app` (read-only except these `docs/audit/` files). Claims are grounded in source and migrations; planned or stubbed behavior is called out in each document.

| # | Document | One-paragraph summary |
|---|---|---|
| 01 | [01-system-map.md](./01-system-map.md) | Maps deployables (Vercel SPA, unclear marketing hosting, Railway FastAPI with in-process Nitya LISTEN + `background_jobs`, Supabase DB/Auth/Storage/Realtime/pg_cron) and every cross-service path (HTTP rewrite `/hireloop-api`, SSE chat, Realtime, NOTIFY, table queue). Inventories external callers for Apify, OpenRouter, Resend/SendGrid, Deepgram, Firecrawl, Gmail/Calendar, MSG91, NeverBounce, LinkDAPI, ATS scripts, Sentry — with file references and Mermaid topology. |
| 02 | [02-data-model.md](./02-data-model.md) | Documents ~55 public tables from 70 migrations: purpose, key columns, FKs, readers/writers, RLS policies (verbatim excerpts + plain language). Confirms zero tables without RLS; ~19 deny-all-without-policies; service-role and asyncpg bypass paths; no frontend mutating writes; pgvector 1536-dim HNSW cosine on candidate/job embedding tables and how filters apply. |
| 03 | [03-candidate-e2e-trace.md](./03-candidate-e2e-trace.md) | Numbered candidate journey: LinkedIn OIDC → bootstrap → onboarding upload/parse/consent → embed → Apify Google Jobs auto-ingest → MatchingEngine → match feed → Request Intro → NOTIFY/durable Nitya draft → approve-send Gmail, with DB I/O, externals, failures, and Realtime/SSE/poll progress, plus sequence diagram. |
| 04 | [04-recruiter-e2e-trace.md](./04-recruiter-e2e-trace.md) | Recruiter journey: signup/role switch → JD form or Firecrawl URL import → publish (mirror `jobs`) → public `/r/{slug}` (account-first CTA vs inbound API) → MatchingEngine search → `role_pipeline` → recruiter→candidate intro → accept, with file refs and sequence diagram. |
| 05 | [05-matching-engine.md](./05-matching-engine.md) | Exact `MatchingEngine` math: weights 0.40/0.30/0.15/0.10/0.05, renormalization, skills 0.85/0.15 blend, embedding lifts, role/domain/title/seniority gates, persist/feed floors, RRF k=60, MMR λ=0.72, company cap 2. States no outcome-validated constants; proposes feedback plug-in via `match_feedback` / second-stage ranker. |
| 06 | [06-agent-architecture.md](./06-agent-architecture.md) | Aarya LangGraph (nodes, tools, prompts, no checkpoint, Realtime `agent_actions`, Deepgram voice). Nitya intro LISTEN pipeline + separate plain recruiter chat. Missed NOTIFY recovered via `NITYA_INTRO_DRAFT` jobs, not re-LISTEN sweep. Confirms no agent↔agent HTTP/RPC. |
| 07 | [07-ingest-pipeline.md](./07-ingest-pipeline.md) | Triggers (cron, find-new, career, auto-ingest), `johnvc/Google-Jobs-Scraper` params, 3-level dedup including fingerprint algorithm, 24h `job_ingest_runs` cache, embed worker concurrency/retry. Failure modes, ATS/Firecrawl as secondary, cost ballpark ~$0.52–$0.55/1k jobs with assumptions. |
| 08 | [08-auth-security.md](./08-auth-security.md) | LinkedIn via Supabase, Gmail/Calendar scopes (`openid`, `userinfo.email`, `gmail.send`, `calendar.events`), encrypted tokens, SPA sessions. Secrets scan (PHASE_TRACKER key fragment), broader public endpoints than R16, prompt-injection surfaces, private resume Storage ACL. |
| 09 | [09-background-jobs-reliability.md](./09-background-jobs-reliability.md) | Full `background_jobs` poller, kinds, retries, 20m reclaim, cron inventory, LISTEN durability. Monitoring is structlog/Sentry/admin — no ingest-staleness alert; explains how a 3-day silent stop would only be found manually. |
| 10 | [10-operations-runbook.md](./10-operations-runbook.md) | Deploy Vercel/Railway/Supabase, rollback limitations, forward-only migrations, log locations, secret rotation, unverified backups, fresh-clone local setup from README/`LOCAL_TESTING.md`. |
| 11 | [11-self-audit.md](./11-self-audit.md) | Skeptical review: dead actors/config, swallowed errors, races (cron idempotency, double ingest), unused tables, doc/code lies, ranked top-10 production fixes. |
| 12 | [12-rebrand-checklist.md](./12-rebrand-checklist.md) | Hireschema vs Hireloop dual brand map: package paths, agents, logos, colors, domains, OAuth redirects, email from addresses, and data already baked into drafts/chat history. |
| 13 | [13-quality-improvements.md](./13-quality-improvements.md) | App quality / robustness package from `fix/robustness-quality-p0-p2`: fail-closed India/DPDP/privacy/atomic intros/rate limits/file security (P0); stale-job hiding, feed fallback/history/find-new, approve-first follow-ups (P1); chat analysis cards, India UX lock, phone OTP deferred (P2). Maps how this extends docs 01–12. |
| 14 | [14-security-remediation-plan.md](./14-security-remediation-plan.md) | Security remediation backlog from 02/08/11/13: S1 (rotate leaked key, Google OAuth consent, Sentry, prod migrations) · S2 (prompt-injection fencing, public-surface R16 truth, phone_verified trust, SERVICE_SECRET rotation drill) · S3 (ClamAV, dep scans, abuse signals, voice_sessions RLS). Acceptance criteria per item; status tracker for weekly reporting. |

---

## Combined Discrepancies

1. **Email stack:** Docs/R9 say SendGrid-primary; code uses **Resend first** with SendGrid fallback (`01`, `08`, `11`).
2. **Job scrape:** Docs say LinkedIn Jobs Scraper; live actor is **`johnvc/Google-Jobs-Scraper`** (`01`, `07`, `11`).
3. **LLM / CSS:** Docs claim Tailwind 4 + `claude-3-5-sonnet`; packages Tailwind **3.4**, primary model **`anthropic/claude-sonnet-4.6`** (`01`, `11`).
4. **Infra:** Docs/Terraform assume AWS ECS ap-south-1 + Cloudflare India ASN; live configs are **Vercel sin1 + Railway SG**; Cloudflare TF incomplete (`01`, `10`, `11`).
5. **Workers:** Docs imply separate agent processes; Nitya + queue run **in-process** with API (`01`, `06`, `09`).
6. **Nitya architecture:** `main.py` claims LangGraph for Nitya; intro path is procedural; recruiter chat is plain LLM (`06`, `11`).
7. **Nitya prompt vs code:** Prompt says send on activate; handler stops at **`draft_ready`** — send is approve-send (`03`, `06`).
8. **README stale:** Sibling `../hireloop/` links, phase P01, wrong stack table (`01`, `10`, `11`).
9. **`job_ingest_log`:** Table + cleanup cron exist; **API writes `job_ingest_runs` instead** (`02`, `07`, `09`).
10. **`time_range` unused** by Google Jobs actor input despite settings (`07`).
11. **Public `/r/{slug}` UX:** Page redirects to signup; inbound apply API is separate (`04`, `11`).
12. **R16 public endpoints:** Allow-list understates actual public surface (`08`, `11`).
13. **Frontend SELECT vs R16:** Mutations via API only; dashboard still SELECTs some tables directly; `voice_sessions` RLS makes counts empty (`02`).
14. **India market:** Temporarily multi-market then forced back to IN in late migration — older multi-market docs stale (`02`).
15. **`jobs.role_id` taxonomy migration** skipped by existing UUID column (`02`, `11`).
16. **Dual brand:** User-facing Hireschema vs Hireloop module/proxy/cron/Vercel names (`12`).
17. **Root Vercel builds app only** — marketing `web/` prod wiring unclear (`01`, `10`).
18. **PHASE S22 “infra not started”** while Railway/Vercel configs already present (`01`, `11`).
19. **Affinda / Fantastic / LinkedIn job actors:** Config zombies (`07`, `11`).
20. **ClamAV** mentioned in R11 — not implemented (`08`, `11`).
21. **Matching culture/career scores** look ranking-related but are metadata only (`05`).
22. **Find-new** can enqueue duplicate Apify work (`07`, `11`).
23. **No formal P0/P1/P2 design doc** — quality severity buckets in `13` are inferred from commits (`13`).
24. **Marketing still mentions +91 phone verification** while OTP onboarding is skipped and `REQUIRE_PHONE_VERIFICATION=false`; `save_phone` auto-verifies (`13`).
25. **Retention digests** may count jobs older than the 45-day live freshness window until cron deactivates them (`13`).
26. **Chat analysis cards** are heuristic, not LLM-deep analysis (`13`).

---

## Combined Unverified — needs human confirmation

1. Marketing `web/` Vercel project / DNS wiring.
2. Live Supabase cron GUCs (`app.api_base_url`, `app.service_secret`) so nightly ingest fires.
3. Whether Cloudflare fronts any production hostname.
4. Railway/Vercel env completeness vs `.env.example` (Apify, Resend, Gmail, etc.).
5. Affinda account — key unused in code.
6. Migration tip drift: live Supabase vs repo.
7. Realtime publication parity with SPA subscriptions.
8. Supabase backup / PITR enabled and restore rehearsed.
9. LinkedIn OIDC provider settings in Supabase.
10. Google OAuth consent verification status (`gmail.send`).
11. NeverBounce + Apify HM actors funded in production.
12. Apify live pricing vs `$0.50/1k` comment; OpenRouter embedding $/M.
13. Whether `PHASE_TRACKER.md` OpenRouter key prefix is/was a real key (rotate if yes).
14. ClamAV or other malware scanning anywhere outside repo.
15. Live `cron.job` last-run status; Sentry DSN in Railway.
16. Who owns on-call / watches Railway logs.
17. Recruiter usage of import-url vs form; effectiveness of public rate limits.
18. Offline validation (if any) of matching floors outside repo; `match_feedback` volume.
19. Railway `database_url` always set so LISTEN starts; future multi-replica plans.
20. Trademark/legal name, OAuth consent screen display name, Resend DNS verification.
21. Whether demos use `NEXT_PUBLIC_DEMO_MODE` mocked as production.
22. Real 30-day Apify/OpenRouter spend vs empty-feed incidents.
23. Whether quality migrations (stale jobs, outbound drafts, privacy opt-in, rate limits, India/DPDP) are applied in production Supabase (`13`).
24. Whether `deactivate-expired-jobs` cron last-run is healthy after the 45-day update (`13`).
25. Whether intro follow-up sweep is firing in production retention cadence (`13`).
26. When MSG91 OTP / `REQUIRE_PHONE_VERIFICATION=true` will return for beta (`13`).
27. Whether the privacy one-shot fail-closed UPDATE already ran in prod (`13`).

---

*Generated for leadership review. Application code was not modified (audit docs only).*
