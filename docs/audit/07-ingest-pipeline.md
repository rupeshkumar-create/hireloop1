# 07 — Job Ingest Pipeline

End-to-end documentation of triggers, Apify, dedup, cache, embedding workers, failure modes, and cost estimate.

---

## Triggers

| Trigger | Entry | Notes |
|---|---|---|
| Nightly cron | `pg_cron` `30 20 * * *` UTC → POST `/api/v1/jobs/ingest/cron` | `20240101000800_jobs_ingestion_cron.sql`; handler `routes/jobs.py` (~157–180) enqueues `JOB_INGEST` idempotency `job_ingest:cron` |
| Manual/admin | `POST /api/v1/jobs/ingest` + `X-Service-Secret` | `jobs.py` (~117–151) |
| Find new | `POST /api/v1/matches/find-new` → `AARYA_AUTO_INGEST` (+ optional `CAREER_PATH_INGEST`), `force_refresh=True` | `matches.py` (~1946–2007) |
| Career path | Prioritize / find-jobs → `CAREER_PATH_INGEST` | `routes/career.py` (~452–467, ~716–718) |
| Aarya auto-ingest | Resume apply / onboarding / thin feed; empty search if flag | `aarya/tools.py:_auto_ingest_for_candidate` (~657–733); `auto_ingest_on_empty_search` default **false** (`config.py`) |
| CLI | `api/scripts/run_ingest.py`, `ingest_ats.py` | Not part of nightly cron |

Docstring on ingester mentioning “background task on first startup” (`job_ingester.py` header) is stale relative to cron + queue.

---

## Apify actor and parameters

**Active actor:** `johnvc/Google-Jobs-Scraper`
Defaults: `jobs_scraper.py` (~119–120), `config.apify_jobs_actor`.

**Input** (`_build_google_jobs_input`, ~229–251):

- `query`, `location`
- `country=in`, `language=en`, `google_domain=google.co.in`
- `num_results`, `max_pagination=3`, `cleanup_results`, `max_delay`
- optional `include_lrad` / `lrad_value=40`

**Run pattern:** up to 10 queries × 5 locations, sequential actor runs (~193–214).
**Poll:** 10s interval, max 600s (~291–321).
**Cost comment in code:** `~$0.50 / 1,000 listings` (`jobs_scraper.py:10`).

**Important:** `time_range` is accepted by `scrape()` (~185) but **never passed** into `_build_google_jobs_input`. Nightly `24h` / candidate `7d` settings are effectively unused by the Google actor.

**Legacy config still present but ignored:** Fantastic / LinkedIn job actors in `.env.example` / `config.py`; `JobIngester.ingest` is Google-only (`job_ingester.py` ~700–701, ~784–785).

---

## Upsert and three-level dedup

Order in `_upsert_jobs` (`job_ingester.py` ~1216–1365):

1. **`apify_job_id`** — `SELECT … WHERE apify_job_id = $1` (~1247–1250); insert/update by that key.
2. **Fingerprint** — `canonical_job_fingerprint(company, title, location, description[:200])` → `sha256(raw)[:32]` (`job_search_buckets.py:155-170`):

```python
parts = [
    (company_name or "").strip().lower(),
    (title or "").strip().lower(),
    (location or "").strip().lower(),
    (description_prefix or "")[:200].strip().lower(),
]
raw = "|".join(parts)
return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

   Fingerprint hit → `_upsert_job_source` only (skip description rewrite).

3. **`apply_url`** — `WHERE apply_url = $1` → skip entirely (~1270–1279).

Per-row exceptions → warn + skip (~1361–1363).

---

## 24h query-skip cache

- `INGEST_DEDUPE_HOURS = 24` (`job_ingester.py:47`)
- Table `job_ingest_runs`: skip same `query_norm` + `location_norm` + `source='google_jobs'` within 24h (~740–780)
- `force_refresh=True` bypasses
- Success recorded only when `inserted+updated > 0` (~843–860)
- Zero-result runs **not** recorded (can retry)

---

## Background embedding workers

| Concern | Implementation |
|---|---|
| Queue | `public.background_jobs` |
| Worker | In-process `run_background_worker` (`main.py` lifespan) |
| Claim | `FOR UPDATE SKIP LOCKED` (`background_jobs.py` ~156–180) |
| Concurrency | Interactive ≤2; heavy (ingest/embed) **1 lane** (~74–88, ~876–912) |
| Retry | Exponential 30s → max 900s; default `max_attempts=3` |
| Idempotency | Unique `idempotency_key` while pending/running |
| Stuck running | Reclaim after **20 min** |
| Post-ingest | `MATCH_EMBED_ALL` delayed +5m, daily key (~566–575) |
| Model | `openai/text-embedding-3-small`, batch **20**, 1536-dim (`embeddings.py`) |
| Abort | OpenRouter **402** → `InsufficientCreditsError`, stop batch |

Kinds: `JOB_EMBED`, `MATCH_EMBED_*`, `RESUME_EMBED_SCORE`, plus ingest kinds.

---

## Failure modes

| Scenario | Behavior |
|---|---|
| Malformed Apify item | `normalise` returns `None` if missing title/market (`jobs_scraper.py` ~341–364); skipped |
| Actor non-2xx / FAILED/ABORTED/TIMED-OUT | Raise `RuntimeError` (~277–279, ~314–315) → background job retry |
| All sources failed | Raise — no silent empty success (`job_ingester.py` ~799–809) |
| Apify rate-limit / 403 rental lapse | Surfaces as exception + job retry; comment notes 403 on lapsed rental |
| Deprecated actor | Would fail at run API; no automatic actor failover in code |
| OpenRouter credits | Embed path aborts batch; scoring may continue lexically |

### Second sources?

| Source | Status |
|---|---|
| Greenhouse / Lever ATS | `services/ats/ats_source.py` via **`scripts/ingest_ats.py`** — **not** on nightly cron; config lists empty by default |
| Firecrawl | JD backfill / company intel queue kinds; free HTML enrich during ingest with `allow_firecrawl=False` for sync path; async Firecrawl when thin JD |
| Fantastic / LinkedIn job actors | Config only — **ignored** |

---

## Cost estimate per 1,000 jobs ingested

| Component | Basis | Estimate |
|---|---|---|
| Apify Google Jobs | Code comment `~$0.50 / 1,000 listings` | **~$0.50 / 1k jobs** |
| Embeddings | `text-embedding-3-small` via OpenRouter; ~title+JD+skills text per job | OpenAI public list ~$0.02 / 1M tokens. Assume ~1–2k tokens/job → **~$0.02–$0.04 / 1k jobs** (order-of-magnitude) |
| Optional JD LLM enrich | Capped `_MAX_JD_ENRICH_PER_INGEST = 20` per ingest run | Depends on model; nightly enrich cap keeps this small vs scrape |
| Optional Firecrawl backfill | Per thin JD | **Not included** in base 1k estimate |

**Combined ballpark (Apify + embeddings only): ~$0.52–$0.55 per 1,000 inserted/updated jobs**, plus wasted spend on deduped/skipped rows when scrape returns dupes.

### Assumptions (marked)

1. Apify comment is accurate for current `johnvc` pricing (not verified against Apify console today).
2. Average job embedding input ~1–2k tokens (titles+truncated truncated paths not measured).
3. OpenRouter markup over OpenAI list price ignored (may be higher).
4. Does not include Apify scrape of rows later **deduped** (you pay scrape, not DB insert).
5. Does not include candidate-targeted multi-query runs (`max_results_per_query=20`, up to 5 variants) which can multiply cost per candidate refresh.
6. Does not include nightly × metro location matrix full cost (queries × locations × `$0.50/1k`).

---

## Discrepancies

1. README / `.cursorrules` say LinkedIn Jobs Scraper; code is Google Jobs.
2. `job_ingest_log` table + cleanup cron exist; writers use `job_ingest_runs`.
3. `time_range` settings documented for freshness but unused by actor input.
4. Find-new can enqueue **both** `AARYA_AUTO_INGEST` and `CAREER_PATH_INGEST` → duplicate Apify spend risk.

---

## Unverified — needs human confirmation

1. Live Apify plan pricing vs the $0.50/1k comment.
2. Whether cron GUCs are set so nightly ingest actually runs in Supabase Cloud.
3. Current OpenRouter embedding $/1M for the project’s account.
