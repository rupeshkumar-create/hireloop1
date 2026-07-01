-- ============================================================
-- Multi-region marketplace — replaces India-only hard locks (R4 v2)
-- Markets: IN (default), US, GB — extensible via ISO country code.
-- ============================================================

-- ── users ─────────────────────────────────────────────────────────────────────
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'IN';

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS phone_country TEXT;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'india_verified'
  ) THEN
    ALTER TABLE public.users RENAME COLUMN india_verified TO phone_verified;
  END IF;
END $$;

ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.users.market IS 'Candidate/recruiter home market (ISO 3166-1 alpha-2)';
COMMENT ON COLUMN public.users.phone_verified IS 'TRUE once phone OTP verified for their market';

-- ── candidates ──────────────────────────────────────────────────────────────
ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS market TEXT NOT NULL DEFAULT 'IN';

UPDATE public.candidates c
SET market = u.market
FROM public.users u
WHERE c.user_id = u.id AND (c.market IS NULL OR c.market = 'IN');

-- ── jobs ────────────────────────────────────────────────────────────────────
ALTER TABLE public.jobs
  DROP CONSTRAINT IF EXISTS jobs_country_code_check;

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS salary_currency TEXT NOT NULL DEFAULT 'INR';

ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS allowed_regions TEXT[] DEFAULT NULL;

COMMENT ON COLUMN public.jobs.salary_currency IS 'ISO 4217 — INR, USD, GBP, etc.';
COMMENT ON COLUMN public.jobs.allowed_regions IS 'Remote eligibility: market codes or WORLD';

-- ── companies ───────────────────────────────────────────────────────────────
ALTER TABLE public.companies
  DROP CONSTRAINT IF EXISTS companies_country_code_check;

-- ── RLS: jobs readable when active (market filter enforced in API) ────────────
DROP POLICY IF EXISTS "jobs: public read active" ON public.jobs;

CREATE POLICY "jobs: public read active"
  ON public.jobs FOR SELECT
  USING (is_active = TRUE AND deleted_at IS NULL);

-- ── Indexes ─────────────────────────────────────────────────────────────────
DROP INDEX IF EXISTS idx_jobs_active_in;

CREATE INDEX IF NOT EXISTS idx_jobs_active_market
  ON public.jobs (country_code, is_active)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_market
  ON public.users (market)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_candidates_market
  ON public.candidates (market)
  WHERE deleted_at IS NULL;

-- ── Auth trigger: phone_verified + optional signup market ───────────────────
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
  v_market TEXT;
BEGIN
  meta := COALESCE(NEW.raw_user_meta_data, '{}'::jsonb);

  v_role := COALESCE(meta->>'role', 'candidate');
  IF v_role NOT IN ('candidate', 'recruiter') THEN
    v_role := 'candidate';
  END IF;

  v_market := upper(COALESCE(meta->>'market', 'IN'));
  IF v_market NOT IN ('IN', 'US', 'GB') THEN
    v_market := 'IN';
  END IF;

  v_name := COALESCE(
    meta->>'full_name',
    meta->>'name',
    split_part(COALESCE(NEW.email, ''), '@', 1)
  );
  v_avatar := COALESCE(meta->>'avatar_url', meta->>'picture', '');

  INSERT INTO public.users (id, email, full_name, avatar_url, role, phone_verified, market)
  VALUES (NEW.id, COALESCE(NEW.email, ''), v_name, NULLIF(v_avatar, ''), v_role, FALSE, v_market)
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), public.users.full_name),
    avatar_url = COALESCE(NULLIF(EXCLUDED.avatar_url, ''), public.users.avatar_url),
    updated_at = NOW();

  RETURN NEW;
END;
$$;
