-- ── Career paths ─────────────────────────────────────────────────────────────
-- An AI-generated career trajectory for a candidate. Aarya reads the candidate's
-- profile (skills, experience, current title) and produces a path: the current
-- role, a short narrative, a sequence of next steps, and the concrete target
-- role titles used to drive Apify-backed job discovery.
--
-- History is kept (one row per generation); the latest row (max created_at,
-- deleted_at IS NULL) is the candidate's current path.

CREATE TABLE IF NOT EXISTS public.career_paths (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id     UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
    "current_role"   TEXT,
    summary          TEXT,
    -- steps: [{title, level, timeframe, rationale, skills_to_build: []}]
    steps            JSONB NOT NULL DEFAULT '[]',
    -- Concrete role titles used as job-search queries (Apify + DB filter)
    target_titles    TEXT[] NOT NULL DEFAULT '{}',
    -- India cities to scope the search; empty → nationwide
    target_locations TEXT[] NOT NULL DEFAULT '{}',
    model            TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at       TIMESTAMPTZ
);

-- Fast "latest path for candidate" lookups.
CREATE INDEX IF NOT EXISTS idx_career_paths_candidate_created
    ON public.career_paths (candidate_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_career_paths_steps
    ON public.career_paths USING GIN (steps);

-- ── RLS ───────────────────────────────────────────────────────────────────────
ALTER TABLE public.career_paths ENABLE ROW LEVEL SECURITY;

-- Candidate can read their own paths.
CREATE POLICY "career_paths: read own"
    ON public.career_paths FOR SELECT
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

-- Candidate can create paths for themselves.
CREATE POLICY "career_paths: insert own"
    ON public.career_paths FOR INSERT
    WITH CHECK (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

-- Candidate can update/soft-delete their own paths.
CREATE POLICY "career_paths: update own"
    ON public.career_paths FOR UPDATE
    USING (
        candidate_id IN (
            SELECT id FROM public.candidates
            WHERE user_id = auth.uid() AND deleted_at IS NULL
        )
    );

-- Admins can read all paths (observability / support).
-- Inline role check: auth.user_role() is not available on all Supabase projects.
CREATE POLICY "career_paths: admin read all"
    ON public.career_paths FOR SELECT
    USING (
        EXISTS (
            SELECT 1
            FROM public.users
            WHERE id = auth.uid()
              AND role = 'admin'
              AND deleted_at IS NULL
        )
    );
