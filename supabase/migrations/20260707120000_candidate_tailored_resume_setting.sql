-- Per-candidate opt-in for AI tailored resumes (off by default).

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS tailored_resume_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.candidates.tailored_resume_enabled IS
  'When true, Aarya may generate per-job and per-path tailored resumes. Off by default.';
