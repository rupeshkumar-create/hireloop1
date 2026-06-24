-- Prioritized career path title — set when candidate picks one of their top paths.

ALTER TABLE public.career_paths
  ADD COLUMN IF NOT EXISTS prioritized_title TEXT;

COMMENT ON COLUMN public.career_paths.prioritized_title IS
  'Target role title the candidate chose to prioritize for job search.';
