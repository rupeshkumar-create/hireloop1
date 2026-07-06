-- Default candidate sharing settings to ON (privacy-preserving public page + recruiter discovery).

ALTER TABLE public.candidates
  ALTER COLUMN hide_contact_public SET DEFAULT TRUE,
  ALTER COLUMN share_with_recruiters SET DEFAULT TRUE,
  ALTER COLUMN public_profile_enabled SET DEFAULT TRUE;

-- Legacy factory defaults: share + publish were FALSE, hide was TRUE (never customized).
UPDATE public.candidates
SET
  share_with_recruiters = TRUE,
  public_profile_enabled = TRUE,
  hide_contact_public = TRUE,
  updated_at = NOW()
WHERE deleted_at IS NULL
  AND share_with_recruiters = FALSE
  AND public_profile_enabled = FALSE
  AND hide_contact_public = TRUE;

COMMENT ON COLUMN public.candidates.public_profile_enabled IS
  'When true, /p/{slug} is world-readable (subject to hide_contact_public). Defaults on for new candidates.';
COMMENT ON COLUMN public.candidates.share_with_recruiters IS
  'When true, registered Hireloop recruiters may see this profile in search. Defaults on for new candidates.';
