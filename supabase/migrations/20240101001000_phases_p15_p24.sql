-- ============================================================
-- Migration 010 — Phases P15–P24 supporting tables
-- Recruiter roles, pipeline, mock interviews, tailored resumes,
-- placements (manual billing), notification prefs, WhatsApp audit
-- ============================================================

-- ── Recruiter roles (P16) ────────────────────────────────────────────────────
CREATE TABLE public.roles (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id            UUID NOT NULL REFERENCES public.companies(id),
  recruiter_id          UUID NOT NULL REFERENCES public.recruiters(id) ON DELETE CASCADE,
  title                 TEXT NOT NULL,
  jd_text               TEXT,
  jd_structured         JSONB DEFAULT '{}',
  comp_min              INTEGER,
  comp_max              INTEGER,
  location_city         TEXT,
  location_state        TEXT,
  remote_policy         TEXT CHECK (remote_policy IN ('onsite', 'hybrid', 'remote', 'flex')),
  must_haves            JSONB DEFAULT '[]',
  nice_to_haves         JSONB DEFAULT '[]',
  evaluation_criteria   JSONB DEFAULT '[]',
  hiring_brief          TEXT,
  candidate_pitch       TEXT,
  calibration_candidates JSONB DEFAULT '[]',
  status                TEXT NOT NULL DEFAULT 'draft'
                          CHECK (status IN ('draft', 'hiring', 'paused', 'closed')),
  version               INTEGER NOT NULL DEFAULT 1,
  calendly_url          TEXT,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at            TIMESTAMPTZ
);

CREATE TRIGGER roles_updated_at
  BEFORE UPDATE ON public.roles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_roles_recruiter ON public.roles(recruiter_id, status)
  WHERE deleted_at IS NULL;
CREATE INDEX idx_roles_company ON public.roles(company_id);

-- ── Role version history (P16) ───────────────────────────────────────────────
CREATE TABLE public.role_versions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id       UUID NOT NULL REFERENCES public.roles(id) ON DELETE CASCADE,
  version       INTEGER NOT NULL,
  snapshot      JSONB NOT NULL,
  created_by    UUID REFERENCES public.users(id),
  restore_of    INTEGER,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (role_id, version)
);

-- ── Pipeline stages per role (P18) ───────────────────────────────────────────
CREATE TABLE public.role_pipeline (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id         UUID NOT NULL REFERENCES public.roles(id) ON DELETE CASCADE,
  candidate_id    UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  stage           TEXT NOT NULL DEFAULT 'search'
                    CHECK (stage IN (
                      'search', 'shortlisted', 'intro_requested',
                      'intro_made', 'interview', 'offer', 'hired', 'archived'
                    )),
  match_score     REAL,
  criterion_scores JSONB DEFAULT '{}',
  notes           TEXT,
  is_public_search BOOLEAN DEFAULT FALSE,
  activity_status TEXT DEFAULT 'active'
                    CHECK (activity_status IN ('active', 'amber', 'dormant')),
  moved_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (role_id, candidate_id)
);

CREATE TRIGGER role_pipeline_updated_at
  BEFORE UPDATE ON public.role_pipeline
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_pipeline_role ON public.role_pipeline(role_id, stage);
ALTER PUBLICATION supabase_realtime ADD TABLE public.role_pipeline;

-- ── Per-criterion match audits (P23 bias audit) ───────────────────────────────
CREATE TABLE public.match_audits (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  match_score_id  UUID REFERENCES public.match_scores(id) ON DELETE CASCADE,
  role_id         UUID REFERENCES public.roles(id) ON DELETE CASCADE,
  candidate_id    UUID REFERENCES public.candidates(id) ON DELETE CASCADE,
  criterion       TEXT NOT NULL,
  llm_score       REAL,
  llm_reasoning   TEXT,
  bias_flags      JSONB DEFAULT '{}',
  model_version   TEXT,
  reviewed        BOOLEAN DEFAULT FALSE,
  reviewer_notes  TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_match_audits_review ON public.match_audits(reviewed, created_at DESC);

-- ── Mock interviews (P21) ────────────────────────────────────────────────────
CREATE TABLE public.mock_interviews (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id      UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  conversation_id   UUID REFERENCES public.conversations(id),
  role_target       TEXT,
  interview_type    TEXT NOT NULL DEFAULT 'recruiter_screen'
                      CHECK (interview_type IN ('recruiter_screen', 'technical', 'behavioral')),
  seniority         TEXT,
  mode              TEXT NOT NULL DEFAULT 'chat'
                      CHECK (mode IN ('chat', 'voice')),
  status            TEXT NOT NULL DEFAULT 'in_progress'
                      CHECK (status IN ('in_progress', 'completed', 'cancelled')),
  transcript        TEXT,
  feedback          JSONB DEFAULT '{}',
  confidence_score  REAL,
  report_path       TEXT,
  duration_secs     INTEGER,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at      TIMESTAMPTZ
);

CREATE INDEX idx_mock_candidate ON public.mock_interviews(candidate_id, created_at DESC);

-- ── Tailored resumes (P20) ─────────────────────────────────────────────────────
CREATE TABLE public.tailored_resumes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  template        TEXT NOT NULL DEFAULT 'modern'
                    CHECK (template IN ('modern', 'classic', 'minimal')),
  file_path       TEXT NOT NULL,
  summary_line    TEXT,
  status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
  error_message   TEXT,
  html_content    TEXT,
  expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tailored_candidate ON public.tailored_resumes(candidate_id, created_at DESC);
CREATE UNIQUE INDEX idx_tailored_unique ON public.tailored_resumes(candidate_id, job_id);

-- ── Placements — manual billing until P22 (v2) ───────────────────────────────
CREATE TABLE public.placements (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id           UUID REFERENCES public.roles(id),
  candidate_id      UUID NOT NULL REFERENCES public.candidates(id),
  company_id        UUID REFERENCES public.companies(id),
  intro_request_id  UUID REFERENCES public.intro_requests(id),
  status            TEXT NOT NULL DEFAULT 'hired_unbilled'
                      CHECK (status IN (
                        'hired_unbilled', 'invoiced', 'paid',
                        'guarantee_period', 'completed', 'refunded'
                      )),
  hired_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  start_date        DATE,
  ctc_inr           BIGINT,
  placement_fee_inr BIGINT,
  gst_inr           BIGINT,
  admin_notes       TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER placements_updated_at
  BEFORE UPDATE ON public.placements
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Notification preferences (P19) ─────────────────────────────────────────────
ALTER TABLE public.users
  ADD COLUMN IF NOT EXISTS notification_prefs JSONB DEFAULT '{
    "job_match": {"email": true, "whatsapp": true, "in_app": true},
    "intro_status": {"email": true, "whatsapp": true, "in_app": true},
    "interview_reminder": {"email": true, "whatsapp": true, "in_app": true},
    "daily_digest": {"email": true, "whatsapp": false, "in_app": true},
    "mock_interview": {"email": true, "whatsapp": true, "in_app": true}
  }'::jsonb;

-- ── WhatsApp send audit (P19 DPDP) ───────────────────────────────────────────
CREATE TABLE public.whatsapp_messages (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  template_name TEXT NOT NULL,
  purpose       TEXT NOT NULL,
  phone         TEXT NOT NULL,
  payload       JSONB DEFAULT '{}',
  msg91_id      TEXT,
  status        TEXT NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'sent', 'delivered', 'failed', 'read')),
  error_message TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_wa_user ON public.whatsapp_messages(user_id, created_at DESC);

-- ── Data export jobs (P23 DPDP) ──────────────────────────────────────────────
CREATE TABLE public.dpdp_export_jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
  file_path     TEXT,
  requested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at  TIMESTAMPTZ,
  purge_after   TIMESTAMPTZ
);

-- Extend conversations for recruiter (Nitya intake)
ALTER TABLE public.conversations
  ALTER COLUMN candidate_id DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS recruiter_id UUID REFERENCES public.recruiters(id),
  ADD COLUMN IF NOT EXISTS role_id UUID REFERENCES public.roles(id);

ALTER TABLE public.conversations
  ADD CONSTRAINT conversations_owner_check CHECK (
    candidate_id IS NOT NULL OR recruiter_id IS NOT NULL
  );
