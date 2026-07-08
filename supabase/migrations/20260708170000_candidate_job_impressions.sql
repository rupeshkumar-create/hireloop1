-- Candidate job impressions + last visit timestamp (retention: "New for you")

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS last_visit_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_candidates_last_visit_at
  ON public.candidates (last_visit_at DESC);

CREATE TABLE IF NOT EXISTS public.candidate_job_impressions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id  UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id        UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  seen_count    INTEGER NOT NULL DEFAULT 1 CHECK (seen_count >= 1),
  source        TEXT NOT NULL DEFAULT 'matches' CHECK (source IN ('matches','chat','job_detail')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, job_id)
);

CREATE TRIGGER candidate_job_impressions_updated_at
  BEFORE UPDATE ON public.candidate_job_impressions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_cji_candidate_last_seen
  ON public.candidate_job_impressions (candidate_id, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_cji_candidate_first_seen
  ON public.candidate_job_impressions (candidate_id, first_seen_at DESC);

ALTER TABLE public.candidate_job_impressions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "candidate_job_impressions: read own"
  ON public.candidate_job_impressions FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates
      WHERE user_id = auth.uid() AND deleted_at IS NULL
    )
  );

CREATE POLICY "candidate_job_impressions: insert own"
  ON public.candidate_job_impressions FOR INSERT
  WITH CHECK (
    candidate_id IN (
      SELECT id FROM public.candidates
      WHERE user_id = auth.uid() AND deleted_at IS NULL
    )
  );

CREATE POLICY "candidate_job_impressions: update own"
  ON public.candidate_job_impressions FOR UPDATE
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates
      WHERE user_id = auth.uid() AND deleted_at IS NULL
    )
  );

