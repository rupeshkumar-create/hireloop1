-- ============================================================
-- Migration 007 — pg_cron scheduled jobs
-- ============================================================

-- Purge soft-deleted rows after 30 days (DPDP Art 7 data minimisation)
SELECT cron.schedule(
  'purge-deleted-users',
  '0 2 * * *',   -- daily at 2am IST (UTC+5:30 offset handled by server TZ)
  $$
    DELETE FROM public.users
    WHERE deleted_at IS NOT NULL
      AND deleted_at < NOW() - INTERVAL '30 days';
  $$
);

SELECT cron.schedule(
  'purge-deleted-candidates',
  '0 2 * * *',
  $$
    DELETE FROM public.candidates
    WHERE deleted_at IS NOT NULL
      AND deleted_at < NOW() - INTERVAL '30 days';
  $$
);

-- Deactivate expired jobs daily
SELECT cron.schedule(
  'deactivate-expired-jobs',
  '30 1 * * *',
  $$
    UPDATE public.jobs
    SET is_active = FALSE, updated_at = NOW()
    WHERE expires_at IS NOT NULL
      AND expires_at < NOW()
      AND is_active = TRUE;
  $$
);

-- Clean up stale agent_actions older than 90 days (not PII, but keeps table lean)
SELECT cron.schedule(
  'cleanup-agent-actions',
  '0 3 * * 0',   -- weekly Sunday 3am
  $$
    DELETE FROM public.agent_actions
    WHERE created_at < NOW() - INTERVAL '90 days';
  $$
);

-- Clean up read notifications older than 30 days
SELECT cron.schedule(
  'cleanup-read-notifications',
  '0 3 * * *',
  $$
    DELETE FROM public.notifications
    WHERE is_read = TRUE
      AND created_at < NOW() - INTERVAL '30 days';
  $$
);
