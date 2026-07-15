-- ============================================================
-- Robustness: India DB invariants, intro claim statuses, DPDP purge
-- ============================================================

-- ── Intro statuses: sending (claim) + failed (retryable) ─────────────────────
ALTER TABLE public.intro_requests DROP CONSTRAINT IF EXISTS intro_requests_status_check;
ALTER TABLE public.intro_requests
  ADD CONSTRAINT intro_requests_status_check CHECK (status IN (
    'pending',
    'invited',
    'enriching',
    'drafting',
    'draft_ready',
    'sending',
    'sent',
    'opened',
    'accepted',
    'replied',
    'declined',
    'failed',
    'expired',
    'cancelled'
  ));

-- ── Normalize any non-IN market data before restoring CHECKs ─────────────────
UPDATE public.jobs
SET is_active = FALSE,
    country_code = 'IN',
    updated_at = NOW()
WHERE country_code IS DISTINCT FROM 'IN';

UPDATE public.companies
SET country_code = 'IN',
    updated_at = NOW()
WHERE country_code IS DISTINCT FROM 'IN';

UPDATE public.users
SET market = 'IN',
    phone_country = COALESCE(phone_country, 'IN'),
    updated_at = NOW()
WHERE market IS DISTINCT FROM 'IN';

UPDATE public.candidates
SET market = 'IN',
    updated_at = NOW()
WHERE market IS DISTINCT FROM 'IN';

-- ── Restore India-only CHECKs (R4) ───────────────────────────────────────────
ALTER TABLE public.jobs DROP CONSTRAINT IF EXISTS jobs_country_code_check;
ALTER TABLE public.jobs
  ADD CONSTRAINT jobs_country_code_check CHECK (country_code = 'IN');

ALTER TABLE public.companies DROP CONSTRAINT IF EXISTS companies_country_code_check;
ALTER TABLE public.companies
  ADD CONSTRAINT companies_country_code_check CHECK (country_code = 'IN');

ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_market_india_check;
ALTER TABLE public.users
  ADD CONSTRAINT users_market_india_check CHECK (market = 'IN');

ALTER TABLE public.candidates DROP CONSTRAINT IF EXISTS candidates_market_india_check;
ALTER TABLE public.candidates
  ADD CONSTRAINT candidates_market_india_check CHECK (market = 'IN');

-- ── Jobs RLS: active India jobs only ─────────────────────────────────────────
DROP POLICY IF EXISTS "jobs: public read active" ON public.jobs;
CREATE POLICY "jobs: public read active"
  ON public.jobs FOR SELECT
  USING (is_active = TRUE AND country_code = 'IN' AND deleted_at IS NULL);

-- ── Auth trigger: force market=IN ─────────────────────────────────────────────
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

  INSERT INTO public.users (id, email, full_name, avatar_url, role, phone_verified, market)
  VALUES (NEW.id, COALESCE(NEW.email, ''), v_name, NULLIF(v_avatar, ''), v_role, FALSE, 'IN')
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), public.users.full_name),
    avatar_url = COALESCE(NULLIF(EXCLUDED.avatar_url, ''), public.users.avatar_url),
    market = 'IN',
    updated_at = NOW();

  RETURN NEW;
END;
$$;

-- ── Soft-delete: users cannot read/update their own soft-deleted rows ────────
DROP POLICY IF EXISTS "users: read own row" ON public.users;
CREATE POLICY "users: read own row"
  ON public.users FOR SELECT
  USING (auth.uid() = id AND deleted_at IS NULL);

DROP POLICY IF EXISTS "users: update own row" ON public.users;
CREATE POLICY "users: update own row"
  ON public.users FOR UPDATE
  USING (auth.uid() = id AND deleted_at IS NULL);

-- ── Stronger DPDP purge (anonymize + soft-delete related PII) ────────────────
CREATE OR REPLACE FUNCTION public.purge_deleted_users()
RETURNS INTEGER AS $$
DECLARE
  purged INTEGER := 0;
  r RECORD;
BEGIN
  FOR r IN
    SELECT u.id AS user_id, c.id AS candidate_id
    FROM public.users u
    JOIN public.dpdp_export_jobs j ON j.user_id = u.id
    LEFT JOIN public.candidates c ON c.user_id = u.id
    WHERE j.purge_after < NOW()
      AND u.deleted_at IS NOT NULL
      AND u.email NOT LIKE 'purged-%'
  LOOP
    UPDATE public.users
    SET email = 'purged-' || r.user_id::text || '@deleted.hireschema.com',
        phone = NULL,
        full_name = 'Deleted User',
        avatar_url = NULL,
        updated_at = NOW()
    WHERE id = r.user_id;

    IF r.candidate_id IS NOT NULL THEN
      UPDATE public.candidates
      SET headline = NULL,
          summary = NULL,
          current_title = NULL,
          current_company = NULL,
          linkedin_url = NULL,
          github_url = NULL,
          portfolio_url = NULL,
          resume_url = NULL,
          resume_path = NULL,
          skills = '{}',
          linkedin_data = '{}'::jsonb,
          aarya_state = '{}'::jsonb,
          profile_enrichment = '{}'::jsonb,
          deleted_at = COALESCE(deleted_at, NOW()),
          updated_at = NOW()
      WHERE id = r.candidate_id;

      UPDATE public.messages m
      SET content = '[redacted]'
      FROM public.conversations conv
      WHERE conv.id = m.conversation_id
        AND conv.candidate_id = r.candidate_id;
    END IF;

    purged := purged + 1;
  END LOOP;

  UPDATE public.dpdp_export_jobs
  SET status = 'ready', completed_at = NOW()
  WHERE purge_after < NOW() AND status = 'pending';

  RETURN purged;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION public.purge_deleted_users IS
  'Run daily via pg_cron: SELECT public.purge_deleted_users(); Anonymizes soft-deleted users after purge_after.';
