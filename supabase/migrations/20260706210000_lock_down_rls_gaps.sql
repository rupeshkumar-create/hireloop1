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
--    the API), so revoke. Guarded: these functions were created outside the
--    migration chain, so scratch databases (CI) may not have them.
DO $$
BEGIN
  IF to_regprocedure('public.is_super_admin()') IS NOT NULL THEN
    REVOKE EXECUTE ON FUNCTION public.is_super_admin() FROM anon, authenticated;
  END IF;
  IF to_regprocedure('public.user_role()') IS NOT NULL THEN
    REVOKE EXECUTE ON FUNCTION public.user_role() FROM anon, authenticated;
  END IF;
  -- 3. Pin search_path on the trigger helper flagged by the linter.
  IF to_regprocedure('public.set_updated_at()') IS NOT NULL THEN
    ALTER FUNCTION public.set_updated_at() SET search_path = public;
  END IF;
END
$$;
