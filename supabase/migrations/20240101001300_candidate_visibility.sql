-- ─────────────────────────────────────────────────────────────────────────────
-- Candidate profile visibility
--
-- Controls how a candidate's profile is shared with companies:
--   open_to_matches  → shared where Aarya sees a strong fit (default)
--   exceptional_only → shared only for exceptional-fit roles
--   private          → never shared automatically
--
-- Used by the matching/sharing pipeline to decide whether a candidate appears
-- in recruiter-facing search results.
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type WHERE typname = 'candidate_visibility'
  ) THEN
    CREATE TYPE candidate_visibility AS ENUM (
      'open_to_matches',
      'exceptional_only',
      'private'
    );
  END IF;
END$$;

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS visibility candidate_visibility
    NOT NULL DEFAULT 'open_to_matches';

COMMENT ON COLUMN public.candidates.visibility IS
  'How the candidate profile is shared with companies (DPDP: candidate-controlled).';
