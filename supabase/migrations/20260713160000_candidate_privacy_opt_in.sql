-- Candidate sharing is explicit opt-in. Previous defaults published profiles
-- and exposed them to recruiter search without a distinct user action.
ALTER TABLE public.candidates
  ALTER COLUMN hide_contact_public SET DEFAULT TRUE,
  ALTER COLUMN share_with_recruiters SET DEFAULT FALSE,
  ALTER COLUMN public_profile_enabled SET DEFAULT FALSE;

-- Fail closed for the beta reset. Candidates can re-enable either surface from
-- Profile, which writes a dedicated consent_log event.
UPDATE public.candidates
SET share_with_recruiters = FALSE,
    public_profile_enabled = FALSE,
    updated_at = NOW()
WHERE deleted_at IS NULL;

DROP POLICY IF EXISTS "candidates: recruiter read active" ON public.candidates;
CREATE POLICY "candidates: recruiter read opted in"
  ON public.candidates FOR SELECT
  USING (
    EXISTS (
      SELECT 1
      FROM public.users
      WHERE id = auth.uid()
        AND role = 'recruiter'
        AND deleted_at IS NULL
    )
    AND is_active = TRUE
    AND share_with_recruiters = TRUE
    AND visibility <> 'private'
    AND deleted_at IS NULL
  );

COMMENT ON COLUMN public.candidates.public_profile_enabled IS
  'World-readable profile switch. False until the candidate explicitly publishes.';
COMMENT ON COLUMN public.candidates.share_with_recruiters IS
  'Recruiter discovery switch. False until the candidate explicitly opts in.';
