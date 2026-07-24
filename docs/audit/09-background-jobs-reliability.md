# 09 — Background Jobs & Reliability

Every asynchronous path, cron schedule, retry/dead-letter behavior, failure modes, and observability gaps.

---

## Mechanism — `background_jobs`

**Table:** `public.background_jobs` (`20240101003100_background_jobs.sql`)
**Service:** `api/src/hireloop_api/services/background_jobs.py`

| Step | Function / behavior |
|---|---|
| Enqueue | `enqueue_job` — pending row; skip if active `idempotency_key` |
| Poll | `run_background_worker` every `background_worker_poll_seconds` (~2s default) |
| Claim | `claim_next_job` — `FOR UPDATE SKIP LOCKED` |
| Priority | Interactive kinds preferred; heavy kinds (ingest/embed) single-threaded |
| Success | `status='completed'` |
| Failure | Backoff re-queue (30s → max 900s) or `status='failed'` + `last_error` |
| Stuck | Reclaim `running` older than **20 minutes** |
| Sidecars | Every ~15m: intro follow-ups, retention; TTL cleanup for caches/rate limits |

**Dead-letter:** permanent `failed` status — **no separate DLQ table**. Admin list: `GET /api/v1/admin/background-jobs` (`admin.py`).

**Process placement:** Same uvicorn process as HTTP (`main.py:lifespan`). Single worker comment — replicas would duplicate pollers.

### Job kinds (representative)

`career_path_ingest`, `pool_ingest`, `aarya_auto_ingest`, `resume_embed_score`, `resume_parse`, `nitya_intro_draft`, `career_intelligence_update`, `career_path_update`, `profile_completeness`, `tailored_resume`, `career_path_resumes`, `learning_roadmap`, `application_kit`, `match_embed_all`, `match_recompute_all`, `match_embed_candidate`, `job_embed`, `job_score`, `job_ingest`, `linkdapi_enrich`, `hm_enrich`, `interview_reminder`, `aarya_weekly_digest`, `aarya_daily_digest`, `firecrawl_jd_backfill`, `firecrawl_company_intel`.

### Nitya LISTEN (separate from table queue)

`NityaWorker` LISTENs on `intro_requests` in the same process. Durable twin: `NITYA_INTRO_DRAFT` with advisory lock coordination.

---

## Cron schedules (Supabase pg_cron)

| Job name | Schedule (UTC) | Purpose |
|---|---|---|
| `hireloop_job_ingest_nightly` | `30 20 * * *` | HTTP ingest |
| `hireloop_embed_pending` | `0 21 * * *` | Embed pending |
| `hireloop_recompute_matches` | `0 22 * * *` | Recompute matches |
| `hireloop_cleanup_ingest_logs` | `0 3 * * *` | Cleanup `job_ingest_log` |
| `hireloop_cleanup_stale_matches` | `30 3 * * 0` | Stale scores |
| `purge-deleted-users` / candidates | `0 2 * * *` | Hard delete soft-deleted |
| `deactivate-expired-jobs` | `30 1 * * *` (+ later migration) | Deactivate |
| `cleanup-agent-actions` | `0 3 * * 0` | 90d cleanup |
| `cleanup-read-notifications` | `0 3 * * *` | 30d |

Sources: `20240101000600_cron_jobs.sql`, `008`, `009`, `20260713100000_*`.

---

## Worker dies mid-job

1. Row left `status='running'`.
2. After 20 minutes, reclaim logic retries or fails permanently (`background_jobs.py` ~823–872).
3. Shutdown: stop event → cancel worker task → drain (`main.py` ~122–129).
4. Intro send race mitigated by atomic `claim_intro_for_send` (`nitya/tools.py` ~283–306).

**Visibility hole:** jobs stuck &lt;20m look “running” with no progress; process death during Apify wait can burn a long window before reclaim.

---

## Monitoring, alerting, structured logging

| Signal | What exists |
|---|---|
| Structlog | JSON in prod/staging (`main.py`); events like `job_ingestion_*`, `background_job_*`, `nitya_*` |
| Sentry | Optional `SENTRY_DSN`; production logs **error** if missing |
| Health | `/api/v1/health`, `/ready`; `/deep` checks Apify/OpenRouter reachability — **not** ingest freshness |
| Admin | `GET /admin/ingestion` — active jobs + 6h refresh count (`admin.py` ~140–164) |
| Railway logs | API stdout (ops platform — not in-repo) |

**No in-repo pager/alerting rule** for “ingest stale” or “background_jobs failed spike”.

---

## How would anyone know if ingest silently stopped for three days?

**Today — poorly.** Discovery paths are manual:

1. Notice empty/stale candidate feeds.
2. Open admin ingestion UI and see zero refreshes in 6h window (still not “3 days”).
3. Query SQL: `SELECT max(last_run_at) FROM job_ingest_runs` or `SELECT max(scraped_at) FROM jobs WHERE source='google_jobs'`.
4. Scroll Railway logs for missing `job_ingestion_*` / failed `job_ingest:cron`.
5. Check whether idempotency key `job_ingest:cron` left a stuck pending/running row **blocking** nightly enqueue until reclaim/fail.

**Missing:** alert on `job_ingest_runs.last_run_at` age; writer to `job_ingest_log` for cron audit (table exists unused); SLOs on Apify success rate.

---

## Idempotency guarantees (concrete)

| Kind pattern | Guarantee |
|---|---|
| Cron ingest | Idempotency `job_ingest:cron` — **at most one active** cron job; also a stuck-row risk |
| Candidate embed | Keys like match_embed_candidate:{id} (pattern in enqueue sites) |
| Nitya draft | Per intro enqueue + advisory lock |
| Ingest query skip | 24h `job_ingest_runs` (orthogonal to queue idempotency) |
| Job row upsert | Dedup apify_id / fingerprint / apply_url |

Not all handlers are fully idempotent at the side-effect level (e.g. external email sends use separate claim paths).

---

## Discrepancies

1. `job_ingest_log` audited by cron cleanup but **unwritten** by API — freshness metrics must use `job_ingest_runs` / `jobs.scraped_at`.
2. Docs implying dedicated worker fleet vs in-process single replica.
3. PHASE_TRACKER / health deep check do not substitute for ingest SLOs.

---

## Unverified — needs human confirmation

1. Live `cron.job` rows and last run status in Supabase.
2. Whether Sentry DSN is set in Railway production.
3. Whether anyone watches Railway logs on a schedule.
