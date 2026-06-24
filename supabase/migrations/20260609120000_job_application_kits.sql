-- Per-job application assets: cover letter, interview prep, tailored resume link.

CREATE TABLE IF NOT EXISTS public.job_application_kits (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    job_id              UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    cover_letter        TEXT,
    interview_prep      TEXT,
    tailored_resume_id  UUID REFERENCES public.tailored_resumes(id) ON DELETE SET NULL,
    mock_interview_id   UUID REFERENCES public.mock_interviews(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_job_application_kits_candidate
    ON public.job_application_kits (candidate_id, updated_at DESC);

ALTER TABLE public.job_application_kits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "job_application_kits: read own"
    ON public.job_application_kits FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "job_application_kits: insert own"
    ON public.job_application_kits FOR INSERT
    WITH CHECK (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "job_application_kits: update own"
    ON public.job_application_kits FOR UPDATE
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );
