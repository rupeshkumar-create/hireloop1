-- ============================================================
-- Migration — Enable RLS on P15–P24 tables left open
--
-- Tables: roles, role_versions, role_pipeline, match_audits,
--         mock_interviews, tailored_resumes, placements,
--         whatsapp_messages, dpdp_export_jobs
--
-- FastAPI uses the direct Postgres connection (bypasses RLS).
-- These policies protect against anon/authenticated Supabase
-- client access with the public anon key + user JWT.
-- ============================================================

-- ── Helper subqueries (inline — no new functions) ────────────────────────────
-- Candidate owns row:
--   candidate_id IN (
--     SELECT id FROM public.candidates
--     WHERE user_id = auth.uid() AND deleted_at IS NULL
--   )
-- Recruiter owns role:
--   role_id IN (
--     SELECT r.id FROM public.roles r
--     JOIN public.recruiters rec ON rec.id = r.recruiter_id
--     WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
--   )
-- Admin:
--   EXISTS (
--     SELECT 1 FROM public.users
--     WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
--   )

-- ── tailored_resumes (candidate PII) ─────────────────────────────────────────
ALTER TABLE public.tailored_resumes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tailored_resumes: read own"
    ON public.tailored_resumes FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "tailored_resumes: insert own"
    ON public.tailored_resumes FOR INSERT
    WITH CHECK (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "tailored_resumes: update own"
    ON public.tailored_resumes FOR UPDATE
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

-- ── mock_interviews (candidate PII) ──────────────────────────────────────────
ALTER TABLE public.mock_interviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "mock_interviews: read own"
    ON public.mock_interviews FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "mock_interviews: insert own"
    ON public.mock_interviews FOR INSERT
    WITH CHECK (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "mock_interviews: update own"
    ON public.mock_interviews FOR UPDATE
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

-- ── roles (recruiter-owned) ──────────────────────────────────────────────────
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "roles: recruiter read own"
    ON public.roles FOR SELECT
    USING (
        recruiter_id IN (
            SELECT id FROM public.recruiters
            WHERE user_id = auth.uid()
              AND deleted_at IS NULL
        )
        AND deleted_at IS NULL
    );

CREATE POLICY "roles: recruiter insert own"
    ON public.roles FOR INSERT
    WITH CHECK (
        recruiter_id IN (
            SELECT id FROM public.recruiters
            WHERE user_id = auth.uid()
              AND deleted_at IS NULL
        )
    );

CREATE POLICY "roles: recruiter update own"
    ON public.roles FOR UPDATE
    USING (
        recruiter_id IN (
            SELECT id FROM public.recruiters
            WHERE user_id = auth.uid()
              AND deleted_at IS NULL
        )
    );

CREATE POLICY "roles: admin read all"
    ON public.roles FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

-- ── role_versions (scoped via parent role) ─────────────────────────────────────
ALTER TABLE public.role_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "role_versions: recruiter read own"
    ON public.role_versions FOR SELECT
    USING (
        role_id IN (
            SELECT r.id FROM public.roles r
            JOIN public.recruiters rec ON rec.id = r.recruiter_id
            WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
        )
    );

CREATE POLICY "role_versions: recruiter insert own"
    ON public.role_versions FOR INSERT
    WITH CHECK (
        role_id IN (
            SELECT r.id FROM public.roles r
            JOIN public.recruiters rec ON rec.id = r.recruiter_id
            WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
        )
    );

CREATE POLICY "role_versions: admin read all"
    ON public.role_versions FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

-- ── role_pipeline (recruiter write; candidate read own row) ──────────────────
ALTER TABLE public.role_pipeline ENABLE ROW LEVEL SECURITY;

CREATE POLICY "role_pipeline: recruiter read own roles"
    ON public.role_pipeline FOR SELECT
    USING (
        role_id IN (
            SELECT r.id FROM public.roles r
            JOIN public.recruiters rec ON rec.id = r.recruiter_id
            WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
        )
    );

CREATE POLICY "role_pipeline: recruiter insert own roles"
    ON public.role_pipeline FOR INSERT
    WITH CHECK (
        role_id IN (
            SELECT r.id FROM public.roles r
            JOIN public.recruiters rec ON rec.id = r.recruiter_id
            WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
        )
    );

CREATE POLICY "role_pipeline: recruiter update own roles"
    ON public.role_pipeline FOR UPDATE
    USING (
        role_id IN (
            SELECT r.id FROM public.roles r
            JOIN public.recruiters rec ON rec.id = r.recruiter_id
            WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
        )
    );

CREATE POLICY "role_pipeline: candidate read own"
    ON public.role_pipeline FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

CREATE POLICY "role_pipeline: admin read all"
    ON public.role_pipeline FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

-- ── match_audits (bias review — admin only) ──────────────────────────────────
ALTER TABLE public.match_audits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "match_audits: admin read"
    ON public.match_audits FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

CREATE POLICY "match_audits: admin update"
    ON public.match_audits FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

-- ── placements (manual billing — admin only) ─────────────────────────────────
ALTER TABLE public.placements ENABLE ROW LEVEL SECURITY;

CREATE POLICY "placements: admin read"
    ON public.placements FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

CREATE POLICY "placements: admin update"
    ON public.placements FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM public.users
            WHERE id = auth.uid() AND role = 'admin' AND deleted_at IS NULL
        )
    );

-- ── whatsapp_messages (DPDP send audit — user read own) ──────────────────────
ALTER TABLE public.whatsapp_messages ENABLE ROW LEVEL SECURITY;

CREATE POLICY "whatsapp_messages: read own"
    ON public.whatsapp_messages FOR SELECT
    USING (user_id = auth.uid());

-- ── dpdp_export_jobs (DPDP export / purge queue — user read own) ─────────────
ALTER TABLE public.dpdp_export_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "dpdp_export_jobs: read own"
    ON public.dpdp_export_jobs FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "dpdp_export_jobs: insert own"
    ON public.dpdp_export_jobs FOR INSERT
    WITH CHECK (user_id = auth.uid());
