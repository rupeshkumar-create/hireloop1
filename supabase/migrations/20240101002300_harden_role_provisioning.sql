-- ============================================================
-- Migration 023 — Harden auto-provisioning against role escalation
-- ============================================================
--
-- SECURITY FIX (privilege escalation):
-- The previous handle_new_user() copied `role` straight from
-- auth.users.raw_user_meta_data. That JSONB blob is populated from the
-- client-supplied `options.data` passed to supabase.auth.signUp() — i.e. it is
-- fully attacker-controlled. A user could sign up with
--   { data: { role: "admin" } }
-- and be provisioned directly into public.users with role='admin', which the
-- API's get_admin_user() then honours → full admin + super-admin access.
--
-- Fix: only the non-privileged self-select roles ('candidate', 'recruiter')
-- may come from signup metadata. 'admin' can NEVER be assigned this way — it is
-- granted exclusively server-side via the audited super-admin endpoint (which
-- requires an existing admin) or by an operator out-of-band. We also never
-- update `role` on conflict, so this trigger can't be used to elevate an
-- existing row either.
-- ============================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  meta JSONB;
  v_role TEXT;
  v_name TEXT;
  v_avatar TEXT;
BEGIN
  meta := COALESCE(NEW.raw_user_meta_data, '{}'::jsonb);

  -- Only non-privileged self-select roles may originate from signup metadata.
  -- Anything else (including 'admin') falls back to 'candidate'.
  v_role := COALESCE(meta->>'role', 'candidate');
  IF v_role NOT IN ('candidate', 'recruiter') THEN
    v_role := 'candidate';
  END IF;

  v_name := COALESCE(
    meta->>'full_name',
    meta->>'name',
    split_part(COALESCE(NEW.email, ''), '@', 1)
  );
  v_avatar := COALESCE(meta->>'avatar_url', meta->>'picture', '');

  INSERT INTO public.users (id, email, full_name, avatar_url, role, india_verified)
  VALUES (NEW.id, COALESCE(NEW.email, ''), v_name, NULLIF(v_avatar, ''), v_role, FALSE)
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), public.users.full_name),
    avatar_url = COALESCE(NULLIF(EXCLUDED.avatar_url, ''), public.users.avatar_url),
    updated_at = NOW();
  -- NOTE: role is intentionally NOT in the DO UPDATE set — never elevate here.

  RETURN NEW;
END;
$$;
