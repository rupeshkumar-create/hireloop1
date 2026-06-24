-- ── Candidate structured career profile ──────────────────────────────────────
-- Stores the rich resume/LinkedIn-derived profile used by Aarya for career
-- pathing, gap analysis, and job matching. Flat candidate columns stay as
-- query-friendly compatibility fields.

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS career_profile JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS career_analysis JSONB NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_candidates_career_profile
  ON public.candidates USING GIN (career_profile);

CREATE INDEX IF NOT EXISTS idx_candidates_career_analysis
  ON public.candidates USING GIN (career_analysis);
