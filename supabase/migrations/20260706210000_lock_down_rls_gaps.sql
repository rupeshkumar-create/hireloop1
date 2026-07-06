-- Security lint remediation (Supabase advisors, 2026-07-06):
-- 1. Three tables were exposed via PostgREST with RLS disabled. The API talks
--    to Postgres as a privileged role (bypasses RLS), so enabling RLS with no
--    policies simply denies anon/authenticated REST access — which is correct:
--    these tables are internal.
ALTER TABLE public.background_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.career_path_definitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.career_path_pool_jobs ENABLE ROW LEVEL SECURITY;

-- 2. SECURITY DEFINER helpers were executable by anon/authenticated via
--    /rest/v1/rpc — nothing client-side calls them (admin gating happens in
--    the API), so revoke.
REVOKE EXECUTE ON FUNCTION public.is_super_admin() FROM anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.user_role() FROM anon, authenticated;

-- 3. Pin search_path on the trigger helper flagged by the linter.
ALTER FUNCTION public.set_updated_at() SET search_path = public;
