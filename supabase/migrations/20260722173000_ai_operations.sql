-- User-safe lifecycle projection for durable external-AI work.
-- Private payloads and worker details remain in public.background_jobs.

CREATE TABLE public.ai_operations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  candidate_id UUID REFERENCES public.candidates(id) ON DELETE CASCADE,
  recruiter_id UUID REFERENCES public.recruiters(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  resource_type TEXT,
  resource_id UUID,
  background_job_id UUID REFERENCES public.background_jobs(id) ON DELETE SET NULL,
  retry_of UUID REFERENCES public.ai_operations(id) ON DELETE SET NULL,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL,
  progress_percent SMALLINT NOT NULL DEFAULT 0,
  stage TEXT NOT NULL,
  message TEXT NOT NULL,
  result_type TEXT,
  result_id UUID,
  error_code TEXT,
  error_message TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  CONSTRAINT ai_operations_actor_shape
    CHECK (candidate_id IS NULL OR recruiter_id IS NULL),
  CONSTRAINT ai_operations_status_valid
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
  CONSTRAINT ai_operations_progress_bounds
    CHECK (progress_percent BETWEEN 0 AND 100),
  CONSTRAINT ai_operations_attempts_nonnegative
    CHECK (attempts >= 0),
  CONSTRAINT ai_operations_lifecycle_shape
    CHECK (
      (status IN ('queued', 'running') AND completed_at IS NULL)
      OR (status = 'succeeded' AND progress_percent = 100 AND completed_at IS NOT NULL)
      OR (status IN ('failed', 'cancelled') AND completed_at IS NOT NULL)
    )
);

CREATE INDEX idx_ai_operations_owner_status_recency
  ON public.ai_operations (user_id, status, created_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX idx_ai_operations_background_job
  ON public.ai_operations (background_job_id)
  WHERE background_job_id IS NOT NULL;

CREATE INDEX idx_ai_operations_expiry_cleanup
  ON public.ai_operations (expires_at)
  WHERE expires_at IS NOT NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX idx_ai_operations_active_idempotency
  ON public.ai_operations (idempotency_key)
  WHERE status IN ('queued', 'running') AND deleted_at IS NULL;

CREATE TRIGGER ai_operations_updated_at
  BEFORE UPDATE ON public.ai_operations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.ai_operations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "ai_operations: read own"
  ON public.ai_operations FOR SELECT
  USING (auth.uid() = user_id AND deleted_at IS NULL);

CREATE POLICY "ai_operations: admin read all"
  ON public.ai_operations FOR SELECT
  USING (
    deleted_at IS NULL
    AND EXISTS (
      SELECT 1
      FROM public.users
      WHERE id = auth.uid()
        AND role = 'admin'
        AND deleted_at IS NULL
    )
  );

COMMENT ON TABLE public.ai_operations IS
  'User-safe lifecycle projection for durable AI work; queue payloads remain private.';
