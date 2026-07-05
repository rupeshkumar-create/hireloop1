-- Candidate display currency, public profile sharing, and per-path resumes.

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS display_currency TEXT NOT NULL DEFAULT 'auto',
  ADD COLUMN IF NOT EXISTS public_slug TEXT,
  ADD COLUMN IF NOT EXISTS public_profile_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS hide_contact_public BOOLEAN NOT NULL DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS share_with_recruiters BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_public_slug
  ON public.candidates (public_slug)
  WHERE public_slug IS NOT NULL AND deleted_at IS NULL;

COMMENT ON COLUMN public.candidates.display_currency IS
  'Salary display preference: auto (from market/resume) or INR/USD/GBP/EUR.';
COMMENT ON COLUMN public.candidates.public_slug IS
  'Opaque slug for the candidate public profile URL (/p/{slug}).';
COMMENT ON COLUMN public.candidates.public_profile_enabled IS
  'When true, /p/{slug} is world-readable (subject to hide_contact_public).';
COMMENT ON COLUMN public.candidates.hide_contact_public IS
  'When true, email/phone are omitted from the public profile page.';
COMMENT ON COLUMN public.candidates.share_with_recruiters IS
  'When true, registered Hireloop recruiters may see this profile in search.';

CREATE TABLE IF NOT EXISTS public.career_path_resumes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  career_path_id  UUID REFERENCES public.career_paths(id) ON DELETE SET NULL,
  path_title      TEXT NOT NULL,
  html_content    TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, path_title)
);

CREATE INDEX IF NOT EXISTS idx_career_path_resumes_candidate
  ON public.career_path_resumes (candidate_id, updated_at DESC);

ALTER TABLE public.career_path_resumes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "career_path_resumes: read own"
  ON public.career_path_resumes FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates
      WHERE user_id = auth.uid() AND deleted_at IS NULL
    )
  );

CREATE POLICY "career_path_resumes: service role all"
  ON public.career_path_resumes FOR ALL
  USING (auth.role() = 'service_role');
