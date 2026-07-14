-- One candidate + one browser upload attempt must produce exactly one resume.

ALTER TABLE public.resumes
  ADD COLUMN IF NOT EXISTS upload_idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_resumes_candidate_upload_idempotency
  ON public.resumes (candidate_id, upload_idempotency_key)
  WHERE upload_idempotency_key IS NOT NULL;
