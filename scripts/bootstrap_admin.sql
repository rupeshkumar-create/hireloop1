-- ============================================================
-- Bootstrap the first super-admin
-- ============================================================
--
-- Admin access in Hireloop is granted ONLY by:
--   (a) public.users.role = 'admin', or
--   (b) the operator-managed SUPER_ADMIN_EMAILS allow-list (api/.env).
--
-- It is NEVER derived from any user-editable field (the old self-asserted
-- LinkedIn-slug path was removed — see deps.get_admin_user). Because role can
-- only be elevated server-side, the very first admin must be created out-of-band
-- with this script (or by adding your email to SUPER_ADMIN_EMAILS).
--
-- USAGE (run against your Supabase/Postgres database):
--   1. Replace the email below with your verified login email.
--   2. psql "$DATABASE_URL" -f scripts/bootstrap_admin.sql
--      (or paste into the Supabase SQL editor)
--
-- The user must already exist in public.users (i.e. you've signed up once).
-- ============================================================

UPDATE public.users
SET role = 'admin',
    updated_at = NOW()
WHERE email = 'CHANGE_ME@hireloop.in'
  AND deleted_at IS NULL;

-- Verify:
SELECT id, email, role, india_verified
FROM public.users
WHERE email = 'CHANGE_ME@hireloop.in';
