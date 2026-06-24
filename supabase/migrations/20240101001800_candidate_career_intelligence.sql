-- ── Candidate Career Intelligence ────────────────────────────────────────────
-- Stores the computed 24-layer Career Intelligence profile (archetype, scores,
-- predictions, mobility, hidden signals, etc.) produced by
-- services/career_intelligence/engine.py. Kept separate from career_profile
-- (raw resume/LinkedIn-derived facts) and career_analysis (path recommendation)
-- so each can be refreshed independently.

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS career_intelligence JSONB NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS career_intelligence_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_candidates_career_intelligence
  ON public.candidates USING GIN (career_intelligence);
