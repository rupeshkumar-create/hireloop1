-- Candidate relocation preference: open to roles anywhere in India.
-- When TRUE, the matching engine stops penalizing out-of-city on-site roles
-- (location sub-score) so nationwide openings rank fairly.

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS open_to_relocation BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.candidates.open_to_relocation IS
  'Candidate is open to relocating anywhere in India. Matching no longer docks '
  'out-of-city on-site roles when TRUE.';
