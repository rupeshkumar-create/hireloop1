-- Application intelligence: multi-dim fit, dossiers, outcomes, profile enrichment.

ALTER TABLE public.match_scores
    ADD COLUMN IF NOT EXISTS culture_score REAL,
    ADD COLUMN IF NOT EXISTS career_alignment_score REAL,
    ADD COLUMN IF NOT EXISTS fit_recommendation TEXT
        CHECK (fit_recommendation IS NULL OR fit_recommendation IN ('apply', 'stretch', 'skip')),
    ADD COLUMN IF NOT EXISTS salary_benchmark JSONB,
    ADD COLUMN IF NOT EXISTS triage_notes TEXT;

ALTER TABLE public.job_application_kits
    ADD COLUMN IF NOT EXISTS ats_report JSONB,
    ADD COLUMN IF NOT EXISTS dossier JSONB,
    ADD COLUMN IF NOT EXISTS reviewer_notes TEXT;

ALTER TABLE public.mock_interviews
    ADD COLUMN IF NOT EXISTS job_id UUID REFERENCES public.jobs(id) ON DELETE SET NULL;

ALTER TABLE public.candidates
    ADD COLUMN IF NOT EXISTS profile_enrichment JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS public.application_outcomes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    job_id              UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    stage               TEXT NOT NULL
        CHECK (stage IN (
            'applied', 'screening', 'interview', 'offer',
            'rejected', 'ghosted', 'withdrawn'
        )),
    notes               TEXT,
    dossier_snapshot    JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_application_outcomes_candidate
    ON public.application_outcomes (candidate_id, updated_at DESC);

ALTER TABLE public.application_outcomes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "application_outcomes: read own"
    ON public.application_outcomes FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "application_outcomes: insert own"
    ON public.application_outcomes FOR INSERT
    WITH CHECK (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "application_outcomes: update own"
    ON public.application_outcomes FOR UPDATE
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );
