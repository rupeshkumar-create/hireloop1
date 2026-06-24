-- Candidate job-search preference: filter remote vs on-site roles.

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS remote_preference TEXT NOT NULL DEFAULT 'any'
    CHECK (remote_preference IN ('any', 'remote_only', 'onsite_only'));

COMMENT ON COLUMN public.candidates.remote_preference IS
  'Job feed filter: any | remote_only | onsite_only (non-remote / office roles).';
