-- Expand deactivate-expired-jobs: also deactivate scraped jobs older than 45 days
-- (aligns with api/scripts/expire_stale_jobs.py). Recruiter mirrors (scraped_at NULL)
-- only deactivate via expires_at.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN

    PERFORM cron.unschedule('deactivate-expired-jobs')
    WHERE EXISTS (
      SELECT 1 FROM cron.job WHERE jobname = 'deactivate-expired-jobs'
    );

    PERFORM cron.schedule(
      'deactivate-expired-jobs',
      '30 1 * * *',
      $$
        UPDATE public.jobs
        SET is_active = FALSE, updated_at = NOW()
        WHERE is_active = TRUE
          AND deleted_at IS NULL
          AND (
                (expires_at IS NOT NULL AND expires_at < NOW())
             OR (scraped_at IS NOT NULL AND scraped_at < NOW() - INTERVAL '45 days')
          );
      $$
    );

  ELSE
    RAISE NOTICE 'pg_cron not available — skipping deactivate-expired-jobs update';
  END IF;
END;
$$;
