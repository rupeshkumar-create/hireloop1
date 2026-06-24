-- ─────────────────────────────────────────────────────────────────────────────
-- Candidate "what they're looking for"
--
-- Free-text statement of the candidate's target role / what they want next.
-- Surfaced on the profile Overview and used by Aarya to sharpen job matches.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS looking_for TEXT;

COMMENT ON COLUMN public.candidates.looking_for IS
  'Candidate-authored statement of what role / opportunity they are seeking.';
