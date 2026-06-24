-- DPDP 30-day purge job for soft-deleted users (P23)

CREATE OR REPLACE FUNCTION public.purge_deleted_users()
RETURNS INTEGER AS $$
DECLARE
  purged INTEGER := 0;
BEGIN
  UPDATE public.users u
  SET email = 'purged-' || u.id::text || '@deleted.hireloop.in',
      phone = NULL,
      full_name = 'Deleted User',
      avatar_url = NULL
  FROM public.dpdp_export_jobs j
  WHERE j.user_id = u.id
    AND j.purge_after < NOW()
    AND u.deleted_at IS NOT NULL
    AND u.email NOT LIKE 'purged-%';

  GET DIAGNOSTICS purged = ROW_COUNT;

  UPDATE public.dpdp_export_jobs
  SET status = 'ready', completed_at = NOW()
  WHERE purge_after < NOW() AND status = 'pending';

  RETURN purged;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION public.purge_deleted_users IS
  'Run daily via pg_cron: SELECT public.purge_deleted_users();';
