-- Durable background job queue (replaces fire-and-forget BackgroundTasks for critical work).

CREATE TABLE IF NOT EXISTS public.background_jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind            TEXT NOT NULL,
  payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT,
  status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
  attempts        INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 3,
  last_error      TEXT,
  worker_id       TEXT,
  run_after       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_background_jobs_claim
  ON public.background_jobs (run_after ASC)
  WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_background_jobs_kind_status
  ON public.background_jobs (kind, status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_background_jobs_idempotency_active
  ON public.background_jobs (idempotency_key)
  WHERE idempotency_key IS NOT NULL
    AND status IN ('pending', 'running');

CREATE TRIGGER background_jobs_updated_at
  BEFORE UPDATE ON public.background_jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE public.background_jobs IS
  'Durable async work queue — Apify ingest, rescoring, enrichment. Claimed with FOR UPDATE SKIP LOCKED.';
