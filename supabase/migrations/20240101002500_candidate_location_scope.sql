-- Candidate job-location scope: how wide a geography to surface roles from.
-- Generalises the boolean open_to_relocation into four levels. The matching
-- engine uses it to score the location component (see _location_score).
--   city    → only the candidate's city ranks well
--   state   → same state acceptable
--   country → anywhere in India (India-first default for relocators)
--   global  → no location penalty at all

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS location_scope TEXT NOT NULL DEFAULT 'city'
    CHECK (location_scope IN ('city', 'state', 'country', 'global'));

-- Backfill from the existing relocation flag so behaviour is preserved:
-- open_to_relocation = TRUE meant "anywhere in India" → country.
UPDATE public.candidates
SET location_scope = 'country'
WHERE open_to_relocation IS TRUE AND location_scope = 'city';

COMMENT ON COLUMN public.candidates.location_scope IS
  'Job-feed geography: city | state | country | global. Drives the location '
  'sub-score in matching. open_to_relocation is kept in sync (country/global = true).';
