-- Backfill onboarding_complete for legacy candidates who already activated.

UPDATE public.candidates c
SET onboarding_complete = TRUE,
    updated_at = NOW()
WHERE c.deleted_at IS NULL
  AND c.onboarding_complete = FALSE
  AND (
    c.profile_complete = TRUE
    OR EXISTS (
      SELECT 1
      FROM public.resumes r
      WHERE r.candidate_id = c.id
    )
  )
  AND NULLIF(TRIM(c.current_title), '') IS NOT NULL
  AND (
    cardinality(c.skills) > 0
    OR NULLIF(TRIM(c.looking_for), '') IS NOT NULL
  );
