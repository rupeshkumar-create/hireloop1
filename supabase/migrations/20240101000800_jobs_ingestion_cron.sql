-- ─────────────────────────────────────────────────────────────────────────────
-- P09: Scheduled job ingestion via pg_cron + pg_net
--
-- Calls POST /api/v1/jobs/ingest/cron every night at 2:00 AM IST (= 20:30 UTC)
-- Authenticated via X-Service-Secret header.
--
-- Prerequisites:
--   • extensions: pg_cron, pg_net (enabled in 000_init_extensions)
--   • Supabase vault secret OR explicit value for service_secret
--   • API_BASE_URL Postgres variable set (or replace literal URL below)
-- ─────────────────────────────────────────────────────────────────────────────

-- Store the API base URL as a database parameter so the cron job doesn't
-- have a hardcoded URL. Set this once after applying the migration:
--
--   ALTER DATABASE postgres SET "app.api_base_url" = 'https://api.hireschema.com';
--   ALTER DATABASE postgres SET "app.service_secret" = '<your-secret>';
--
-- (These are instance-level GUCs, not sensitive in the migration itself.)

DO $$
BEGIN
  -- Only register the job if pg_cron extension is available
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

    -- Remove any existing version of this job (idempotent re-run)
    PERFORM cron.unschedule('hireloop_job_ingest_nightly')
    WHERE EXISTS (
      SELECT 1 FROM cron.job WHERE jobname = 'hireloop_job_ingest_nightly'
    );

    -- Schedule nightly at 20:30 UTC = 02:00 IST
    PERFORM cron.schedule(
      'hireloop_job_ingest_nightly',   -- job name
      '30 20 * * *',                   -- cron expression (UTC)
      $$
        SELECT net.http_post(
          url     := current_setting('app.api_base_url') || '/api/v1/jobs/ingest/cron',
          headers := jsonb_build_object(
            'Content-Type',      'application/json',
            'X-Service-Secret',  current_setting('app.service_secret')
          ),
          body    := '{}'::jsonb
        )
      $$
    );

    RAISE NOTICE 'pg_cron job "hireloop_job_ingest_nightly" scheduled (20:30 UTC daily)';

  ELSE
    RAISE NOTICE 'pg_cron not available — skipping cron job registration';
  END IF;
END;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- job_ingest_log table
-- Records each pg_net HTTP call result for debugging.
-- Populated by a separate pg_cron cleanup job (see 000600 migration).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.job_ingest_log (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    triggered_at timestamptz NOT NULL DEFAULT NOW(),
    trigger_type text        NOT NULL DEFAULT 'cron',   -- 'cron' | 'manual'
    status       text,                                   -- 'queued' | 'error'
    response     jsonb,
    error        text
);

COMMENT ON TABLE public.job_ingest_log IS
    'Audit trail for Apify job ingestion runs triggered via pg_cron or admin API.';

-- RLS: readable by service role only (no candidate data, admin-only visibility)
ALTER TABLE public.job_ingest_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_full_access_job_ingest_log"
    ON public.job_ingest_log
    USING (auth.role() = 'service_role');


-- ─────────────────────────────────────────────────────────────────────────────
-- Cleanup old ingest logs (keep 30 days)
-- Adds to the existing cron jobs from migration 000600.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

    PERFORM cron.unschedule('hireloop_cleanup_ingest_logs')
    WHERE EXISTS (
      SELECT 1 FROM cron.job WHERE jobname = 'hireloop_cleanup_ingest_logs'
    );

    PERFORM cron.schedule(
      'hireloop_cleanup_ingest_logs',
      '0 3 * * *',   -- 03:00 UTC daily (after ingest finishes)
      $$
        DELETE FROM public.job_ingest_log
        WHERE triggered_at < NOW() - INTERVAL '30 days'
      $$
    );

  END IF;
END;
$$;
