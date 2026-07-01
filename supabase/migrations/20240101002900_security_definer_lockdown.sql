-- Security advisor remediation (pre-demo hardening):
-- 1) SECURITY DEFINER functions were callable via PostgREST RPC by anon/authenticated.
--    purge_deleted_users() is DESTRUCTIVE (hard-deletes soft-deleted users) and was
--    callable by ANYONE with the public anon key. Lock all three down.
REVOKE EXECUTE ON FUNCTION public.purge_deleted_users() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
-- user_role() is used inside RLS policies for authenticated users — keep their grant,
-- but anon has no business calling it.
REVOKE EXECUTE ON FUNCTION auth.user_role() FROM PUBLIC, anon;

-- 2) Pin search_path on all flagged functions (prevents search-path hijack in
--    SECURITY DEFINER / trigger contexts).
ALTER FUNCTION public.set_updated_at() SET search_path = public;
ALTER FUNCTION auth.user_role() SET search_path = public;
ALTER FUNCTION public.purge_deleted_users() SET search_path = public;
ALTER FUNCTION public.notify_intro_requested() SET search_path = public;
