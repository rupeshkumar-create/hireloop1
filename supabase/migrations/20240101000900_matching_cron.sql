-- ─────────────────────────────────────────────────────────────────────────────
-- P10: Nightly embedding refresh + match score recompute
--
-- Two pg_cron jobs run in sequence after the nightly Apify ingest:
--   1. 21:00 UTC (02:30 IST) — embed all pending jobs + candidates
--   2. 22:00 UTC (03:30 IST) — recompute all match scores
--
-- Both call the FastAPI backend via pg_net.
-- Auth via X-Service-Secret header (same pattern as jobs ingest cron).
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

    -- ── Job 1: embed pending ──────────────────────────────────────────────────
    PERFORM cron.unschedule('hireloop_embed_pending')
    WHERE EXISTS (
      SELECT 1 FROM cron.job WHERE jobname = 'hireloop_embed_pending'
    );

    PERFORM cron.schedule(
      'hireloop_embed_pending',
      '0 21 * * *',    -- 21:00 UTC = 02:30 IST
      $$
        SELECT net.http_post(
          url     := current_setting('app.api_base_url') || '/api/v1/matches/embed',
          headers := jsonb_build_object(
            'Content-Type',      'application/json',
            'X-Service-Secret',  current_setting('app.service_secret')
          ),
          body    := '{}'::jsonb
        )
      $$
    );

    -- ── Job 2: recompute match scores ─────────────────────────────────────────
    PERFORM cron.unschedule('hireloop_recompute_matches')
    WHERE EXISTS (
      SELECT 1 FROM cron.job WHERE jobname = 'hireloop_recompute_matches'
    );

    PERFORM cron.schedule(
      'hireloop_recompute_matches',
      '0 22 * * *',    -- 22:00 UTC = 03:30 IST
      $$
        SELECT net.http_post(
          url     := current_setting('app.api_base_url') || '/api/v1/matches/recompute',
          headers := jsonb_build_object(
            'Content-Type',      'application/json',
            'X-Service-Secret',  current_setting('app.service_secret')
          ),
          body    := '{}'::jsonb
        )
      $$
    );

    RAISE NOTICE 'pg_cron jobs registered: embed (21:00 UTC) + recompute (22:00 UTC)';

  ELSE
    RAISE NOTICE 'pg_cron not available — skipping matching cron registration';
  END IF;
END;
$$;


-- ─────────────────────────────────────────────────────────────────────────────
-- Cleanup stale match scores (jobs expired > 30 days ago)
-- Adds to existing cleanup cron from migration 000600.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

    PERFORM cron.unschedule('hireloop_cleanup_stale_matches')
    WHERE EXISTS (
      SELECT 1 FROM cron.job WHERE jobname = 'hireloop_cleanup_stale_matches'
    );

    PERFORM cron.schedule(
      'hireloop_cleanup_stale_matches',
      '30 3 * * 0',    -- 03:30 UTC every Sunday
      $$
        DELETE FROM public.match_scores ms
        USING public.jobs j
        WHERE ms.job_id = j.id
          AND (j.expires_at < NOW() - INTERVAL '30 days' OR j.is_active = FALSE)
      $$
    );

  END IF;
END;
$$;
