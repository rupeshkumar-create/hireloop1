-- Stop paying twice for identical work.
--
-- 1. resume_parse_cache: the same CV file re-uploaded (very common — retries,
--    re-onboarding, A/B testing edits) re-ran the full LLM parse every time.
--    Keyed by content hash + parser version, so parser upgrades naturally
--    invalidate old entries. Rows are pruned after 30 days by the worker
--    sweep (bounded retention — the cache is keyed by hash, not user, so it
--    cannot be purged per-account on DPDP deletion; the TTL bounds it instead).
CREATE TABLE IF NOT EXISTS public.resume_parse_cache (
  content_hash text NOT NULL,
  parser_version int NOT NULL,
  parsed jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT NOW(),
  PRIMARY KEY (content_hash, parser_version)
);
ALTER TABLE public.resume_parse_cache ENABLE ROW LEVEL SECURITY;

-- 2. job_ingest_runs: the same search query + location was re-scraped on
--    every trigger (kickoff, empty search, pool top-up), burning Apify /
--    Fantastic credits for near-identical result sets. This ledger lets the
--    ingester skip queries that ran recently.
CREATE TABLE IF NOT EXISTS public.job_ingest_runs (
  query_norm text NOT NULL,
  location_norm text NOT NULL,
  source text NOT NULL DEFAULT 'apify',
  last_run_at timestamptz NOT NULL DEFAULT NOW(),
  jobs_found int,
  PRIMARY KEY (query_norm, location_norm, source)
);
ALTER TABLE public.job_ingest_runs ENABLE ROW LEVEL SECURITY;
