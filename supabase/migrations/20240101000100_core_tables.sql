-- ============================================================
-- Migration 002 — Core tables
-- Users, candidates, companies, recruiters, consent_log
-- ============================================================

-- ── Helper: updated_at trigger ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── 1. users ─────────────────────────────────────────────────────────────────
-- Maps 1:1 with auth.users (Supabase Auth). Thin profile layer.
CREATE TABLE public.users (
  id            UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email         TEXT UNIQUE NOT NULL,
  phone         TEXT UNIQUE,                         -- +91 only, verified via MSG91
  full_name     TEXT,
  avatar_url    TEXT,
  role          TEXT NOT NULL DEFAULT 'candidate'    -- 'candidate' | 'recruiter' | 'admin'
                  CHECK (role IN ('candidate', 'recruiter', 'admin')),
  india_verified BOOLEAN NOT NULL DEFAULT FALSE,     -- TRUE once +91 OTP verified
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ                          -- soft-delete (DPDP Art 7)
);

CREATE TRIGGER users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_users_email    ON public.users(email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_phone    ON public.users(phone) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role     ON public.users(role)  WHERE deleted_at IS NULL;

-- ── 2. consent_log ───────────────────────────────────────────────────────────
-- DPDP Act 2023 §6 — every data collection event must be logged.
CREATE TABLE public.consent_log (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  purpose     TEXT NOT NULL,     -- e.g. 'profile_creation', 'job_matching', 'hm_intro'
  granted     BOOLEAN NOT NULL,
  ip_address  INET,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_consent_user    ON public.consent_log(user_id, created_at DESC);
CREATE INDEX idx_consent_purpose ON public.consent_log(purpose, created_at DESC);

-- ── 3. candidates ────────────────────────────────────────────────────────────
CREATE TABLE public.candidates (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
  headline          TEXT,                            -- e.g. "Senior SWE @ Flipkart"
  summary           TEXT,                            -- AI-generated or user-written
  current_title     TEXT,
  current_company   TEXT,
  location_city     TEXT,
  location_state    TEXT,
  years_experience  SMALLINT CHECK (years_experience >= 0 AND years_experience <= 60),
  notice_period_days SMALLINT DEFAULT 30,
  expected_ctc_min  INTEGER,                         -- INR per annum
  expected_ctc_max  INTEGER,
  current_ctc       INTEGER,
  skills            TEXT[] DEFAULT '{}',             -- normalised skill slugs
  linkedin_url      TEXT,
  github_url        TEXT,
  portfolio_url     TEXT,
  resume_url        TEXT,                            -- signed Supabase Storage URL (ephemeral)
  resume_path       TEXT,                            -- Supabase Storage path (permanent)
  linkedin_data     JSONB DEFAULT '{}',              -- raw LinkedIn OAuth profile
  aarya_state       JSONB DEFAULT '{}',              -- LangGraph checkpoint for Aarya agent
  profile_complete  BOOLEAN NOT NULL DEFAULT FALSE,
  is_active         BOOLEAN NOT NULL DEFAULT TRUE,   -- FALSE = paused / not looking
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ
);

CREATE TRIGGER candidates_updated_at
  BEFORE UPDATE ON public.candidates
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_candidates_user       ON public.candidates(user_id);
CREATE INDEX idx_candidates_active     ON public.candidates(is_active, deleted_at);
CREATE INDEX idx_candidates_skills     ON public.candidates USING GIN(skills);
CREATE INDEX idx_candidates_linkedin   ON public.candidates(linkedin_data) WHERE linkedin_data != '{}';

-- ── 4. candidate_embeddings ──────────────────────────────────────────────────
-- Separate table so we can rebuild embeddings without touching candidate PII.
CREATE TABLE public.candidate_embeddings (
  candidate_id      UUID PRIMARY KEY REFERENCES public.candidates(id) ON DELETE CASCADE,
  profile_embedding vector(1536),     -- OpenRouter text-embedding-3-small (1536-dim)
  skills_embedding  vector(1536),
  resume_embedding  vector(1536),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW indexes for cosine similarity (R12 — never L2)
CREATE INDEX idx_ce_profile_hnsw ON public.candidate_embeddings
  USING hnsw (profile_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

CREATE INDEX idx_ce_skills_hnsw  ON public.candidate_embeddings
  USING hnsw (skills_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

CREATE INDEX idx_ce_resume_hnsw  ON public.candidate_embeddings
  USING hnsw (resume_embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 200);

-- ── 5. companies ─────────────────────────────────────────────────────────────
CREATE TABLE public.companies (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name              TEXT NOT NULL,
  domain            TEXT UNIQUE,
  logo_url          TEXT,
  industry          TEXT,
  size_bucket       TEXT CHECK (size_bucket IN ('1-10','11-50','51-200','201-500','501-1000','1000+')),
  hq_city           TEXT,
  hq_state          TEXT,
  country_code      TEXT NOT NULL DEFAULT 'IN'
                      CHECK (country_code = 'IN'),   -- India geo-lock (R4)
  linkedin_url      TEXT,
  about             TEXT,
  apify_data        JSONB DEFAULT '{}',              -- raw Apify company scrape
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ
);

CREATE TRIGGER companies_updated_at
  BEFORE UPDATE ON public.companies
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_companies_name   ON public.companies USING GIN(name gin_trgm_ops);
CREATE INDEX idx_companies_domain ON public.companies(domain) WHERE deleted_at IS NULL;

-- ── 6. recruiters ────────────────────────────────────────────────────────────
CREATE TABLE public.recruiters (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
  company_id    UUID REFERENCES public.companies(id),
  title         TEXT,
  bio           TEXT,
  nitya_state   JSONB DEFAULT '{}',     -- LangGraph checkpoint for Nitya agent
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ
);

CREATE TRIGGER recruiters_updated_at
  BEFORE UPDATE ON public.recruiters
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
