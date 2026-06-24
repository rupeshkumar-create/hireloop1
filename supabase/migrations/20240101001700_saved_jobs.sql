-- ── Saved jobs (bookmark for later) ───────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.saved_jobs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    job_id       UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    saved_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_saved_jobs_candidate_saved_at
    ON public.saved_jobs (candidate_id, saved_at DESC);

ALTER TABLE public.saved_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "saved_jobs: read own"
    ON public.saved_jobs FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "saved_jobs: insert own"
    ON public.saved_jobs FOR INSERT
    WITH CHECK (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "saved_jobs: delete own"
    ON public.saved_jobs FOR DELETE
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );
