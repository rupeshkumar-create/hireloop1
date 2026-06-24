-- ============================================================
-- Migration 006 — Row Level Security (RLS) policies
-- Every table gets RLS. No table is open by default.
-- ============================================================

-- ── Enable RLS on all tables ──────────────────────────────────────────────────
ALTER TABLE public.users               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.consent_log         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidates          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.candidate_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.companies           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recruiters          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.jobs                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_embeddings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.match_scores        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_actions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hiring_managers     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.intro_requests      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gmail_tokens        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_sessions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.job_applications    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resumes             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recruiter_searches  ENABLE ROW LEVEL SECURITY;

-- ── Helper: get current user's role ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION auth.user_role()
RETURNS TEXT AS $$
  SELECT role FROM public.users WHERE id = auth.uid() AND deleted_at IS NULL LIMIT 1;
$$ LANGUAGE sql SECURITY DEFINER STABLE;

-- ── users ─────────────────────────────────────────────────────────────────────
CREATE POLICY "users: read own row"
  ON public.users FOR SELECT
  USING (id = auth.uid());

CREATE POLICY "users: update own row"
  ON public.users FOR UPDATE
  USING (id = auth.uid());

CREATE POLICY "users: admin read all"
  ON public.users FOR SELECT
  USING (auth.user_role() = 'admin');

-- ── consent_log ───────────────────────────────────────────────────────────────
CREATE POLICY "consent_log: read own"
  ON public.consent_log FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "consent_log: insert own"
  ON public.consent_log FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- ── candidates ────────────────────────────────────────────────────────────────
CREATE POLICY "candidates: read own"
  ON public.candidates FOR SELECT
  USING (user_id = auth.uid() AND deleted_at IS NULL);

CREATE POLICY "candidates: update own"
  ON public.candidates FOR UPDATE
  USING (user_id = auth.uid());

CREATE POLICY "candidates: insert own"
  ON public.candidates FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- Recruiters can read active candidate profiles (for Nitya pipeline)
CREATE POLICY "candidates: recruiter read active"
  ON public.candidates FOR SELECT
  USING (
    auth.user_role() = 'recruiter'
    AND is_active = TRUE
    AND deleted_at IS NULL
  );

-- ── companies ─────────────────────────────────────────────────────────────────
CREATE POLICY "companies: public read"
  ON public.companies FOR SELECT
  USING (deleted_at IS NULL);

CREATE POLICY "companies: recruiter write own"
  ON public.companies FOR INSERT
  WITH CHECK (auth.user_role() IN ('recruiter', 'admin'));

-- ── jobs ──────────────────────────────────────────────────────────────────────
CREATE POLICY "jobs: public read active"
  ON public.jobs FOR SELECT
  USING (is_active = TRUE AND country_code = 'IN' AND deleted_at IS NULL);

CREATE POLICY "jobs: recruiter/admin write"
  ON public.jobs FOR INSERT
  WITH CHECK (auth.user_role() IN ('recruiter', 'admin'));

-- ── match_scores ──────────────────────────────────────────────────────────────
CREATE POLICY "match_scores: read own"
  ON public.match_scores FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

-- ── agent_actions ─────────────────────────────────────────────────────────────
CREATE POLICY "agent_actions: read own"
  ON public.agent_actions FOR SELECT
  USING (user_id = auth.uid());

-- ── intro_requests ────────────────────────────────────────────────────────────
CREATE POLICY "intro_requests: candidate read own"
  ON public.intro_requests FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "intro_requests: candidate insert"
  ON public.intro_requests FOR INSERT
  WITH CHECK (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "intro_requests: recruiter read"
  ON public.intro_requests FOR SELECT
  USING (auth.user_role() = 'recruiter');

-- ── gmail_tokens ──────────────────────────────────────────────────────────────
CREATE POLICY "gmail_tokens: read own"
  ON public.gmail_tokens FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "gmail_tokens: write own"
  ON public.gmail_tokens FOR INSERT
  WITH CHECK (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

-- ── conversations + messages ──────────────────────────────────────────────────
CREATE POLICY "conversations: read own"
  ON public.conversations FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
    AND deleted_at IS NULL
  );

CREATE POLICY "messages: read own conversation"
  ON public.messages FOR SELECT
  USING (
    conversation_id IN (
      SELECT c.id FROM public.conversations c
      JOIN public.candidates ca ON ca.id = c.candidate_id
      WHERE ca.user_id = auth.uid() AND c.deleted_at IS NULL
    )
  );

-- ── notifications ─────────────────────────────────────────────────────────────
CREATE POLICY "notifications: read own"
  ON public.notifications FOR SELECT
  USING (user_id = auth.uid());

CREATE POLICY "notifications: update own (mark read)"
  ON public.notifications FOR UPDATE
  USING (user_id = auth.uid());

-- ── job_applications ──────────────────────────────────────────────────────────
CREATE POLICY "job_applications: read own"
  ON public.job_applications FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "job_applications: insert own"
  ON public.job_applications FOR INSERT
  WITH CHECK (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

-- ── resumes ───────────────────────────────────────────────────────────────────
CREATE POLICY "resumes: read own"
  ON public.resumes FOR SELECT
  USING (
    candidate_id IN (
      SELECT id FROM public.candidates WHERE user_id = auth.uid()
    )
  );

-- ── recruiter_searches ────────────────────────────────────────────────────────
CREATE POLICY "recruiter_searches: read own"
  ON public.recruiter_searches FOR SELECT
  USING (
    recruiter_id IN (
      SELECT id FROM public.recruiters WHERE user_id = auth.uid()
    )
  );

-- ── Service role bypass ───────────────────────────────────────────────────────
-- The FastAPI backend uses the service_role key which bypasses RLS.
-- This is intentional — the API enforces its own auth checks.
-- NEVER expose the service_role key to the frontend.
