-- ============================================================
-- Migration 003 — Jobs, matches, agent_actions
-- ============================================================

-- ── 7. jobs ──────────────────────────────────────────────────────────────────
CREATE TABLE public.jobs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        UUID REFERENCES public.companies(id),
  title             TEXT NOT NULL,
  description       TEXT,
  requirements      TEXT,
  responsibilities  TEXT,
  location_city     TEXT,
  location_state    TEXT,
  country_code      TEXT NOT NULL DEFAULT 'IN'
                      CHECK (country_code = 'IN'),   -- India geo-lock (R4)
  is_remote         BOOLEAN DEFAULT FALSE,
  employment_type   TEXT DEFAULT 'full_time'
                      CHECK (employment_type IN ('full_time','contract','internship','part_time')),
  seniority         TEXT CHECK (seniority IN ('intern','junior','mid','senior','lead','director','vp','c_level')),
  ctc_min           INTEGER,                         -- INR per annum
  ctc_max           INTEGER,
  skills_required   TEXT[] DEFAULT '{}',
  apify_job_id      TEXT UNIQUE,                     -- Apify dedupe key
  apply_url         TEXT,                            -- Direct apply link (R from spec)
  source            TEXT DEFAULT 'apify'
                      CHECK (source IN ('apify','manual','recruiter')),
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,
  scraped_at        TIMESTAMPTZ,
  expires_at        TIMESTAMPTZ,
  raw_data          JSONB DEFAULT '{}',              -- full Apify payload
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ
);

CREATE TRIGGER jobs_updated_at
  BEFORE UPDATE ON public.jobs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_jobs_active      ON public.jobs(is_active, country_code, deleted_at);
CREATE INDEX idx_jobs_company     ON public.jobs(company_id);
CREATE INDEX idx_jobs_skills      ON public.jobs USING GIN(skills_required);
CREATE INDEX idx_jobs_title_trgm  ON public.jobs USING GIN(title gin_trgm_ops);
CREATE INDEX idx_jobs_apify       ON public.jobs(apify_job_id) WHERE apify_job_id IS NOT NULL;

-- ── 8. job_embeddings ────────────────────────────────────────────────────────
CREATE TABLE public.job_embeddings (
  job_id            UUID PRIMARY KEY REFERENCES public.jobs(id) ON DELETE CASCADE,
  jd_embedding      vector(1536),    -- full JD text embedding
  title_embedding   vector(1536),    -- title-only (faster for cold recall)
  skills_embedding  vector(1536),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_je_jd_hnsw ON public.job_embeddings
  USING hnsw (jd_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

CREATE INDEX idx_je_title_hnsw ON public.job_embeddings
  USING hnsw (title_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

CREATE INDEX idx_je_skills_hnsw ON public.job_embeddings
  USING hnsw (skills_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- ── 9. match_scores ──────────────────────────────────────────────────────────
-- Precomputed match scores — re-computed nightly via pg_cron.
CREATE TABLE public.match_scores (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id      UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id            UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  overall_score     REAL NOT NULL CHECK (overall_score BETWEEN 0 AND 1),
  skills_score      REAL CHECK (skills_score BETWEEN 0 AND 1),
  experience_score  REAL CHECK (experience_score BETWEEN 0 AND 1),
  location_score    REAL CHECK (location_score BETWEEN 0 AND 1),
  ctc_score         REAL CHECK (ctc_score BETWEEN 0 AND 1),
  explanation       TEXT,             -- plain English explanation shown to candidate
  bias_audit        JSONB DEFAULT '{}', -- DPDP bias audit fields (R14)
  computed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, job_id)
);

CREATE INDEX idx_match_candidate ON public.match_scores(candidate_id, overall_score DESC);
CREATE INDEX idx_match_job       ON public.match_scores(job_id, overall_score DESC);

-- ── 10. agent_actions ────────────────────────────────────────────────────────
-- "Aarya performed 7 actions" UI pattern (R7).
-- Every tool call from Aarya or Nitya writes a row here.
-- Frontend subscribes via Supabase Realtime.
CREATE TABLE public.agent_actions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent         TEXT NOT NULL CHECK (agent IN ('aarya', 'nitya')),
  user_id       UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  session_id    UUID NOT NULL,           -- LangGraph session/thread ID
  action_type   TEXT NOT NULL,           -- e.g. 'profile_read', 'job_search', 'match_score'
  payload       JSONB DEFAULT '{}',      -- tool input
  result        JSONB DEFAULT '{}',      -- tool output (truncated, no PII)
  duration_ms   INTEGER,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_aa_user_session ON public.agent_actions(user_id, session_id, created_at DESC);
CREATE INDEX idx_aa_agent_type   ON public.agent_actions(agent, action_type, created_at DESC);

-- Enable Supabase Realtime on agent_actions (R7)
ALTER PUBLICATION supabase_realtime ADD TABLE public.agent_actions;
