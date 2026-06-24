-- ============================================================
-- Migration 005 — Communication, interviews, notifications
-- ============================================================

-- ── 14. conversations ────────────────────────────────────────────────────────
-- Chat history for Aarya ↔ candidate sessions (Claude/Codex-style UI).
CREATE TABLE public.conversations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id  UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  agent         TEXT NOT NULL DEFAULT 'aarya' CHECK (agent IN ('aarya', 'nitya')),
  title         TEXT,                       -- auto-generated from first message
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ
);

CREATE TRIGGER conversations_updated_at
  BEFORE UPDATE ON public.conversations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_conv_candidate ON public.conversations(candidate_id, updated_at DESC)
  WHERE deleted_at IS NULL;

-- ── 15. messages ─────────────────────────────────────────────────────────────
CREATE TABLE public.messages (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES public.conversations(id) ON DELETE CASCADE,
  role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
  content         TEXT NOT NULL,
  content_type    TEXT NOT NULL DEFAULT 'text' CHECK (content_type IN ('text', 'voice', 'tool_call', 'tool_result')),
  audio_url       TEXT,                     -- ElevenLabs TTS output URL (ephemeral, 1h)
  tool_name       TEXT,                     -- if content_type = 'tool_call'
  tool_input      JSONB,
  tool_output     JSONB,
  tokens_used     INTEGER,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_msg_conversation ON public.messages(conversation_id, created_at ASC);
CREATE INDEX idx_msg_role         ON public.messages(role, created_at DESC);

-- Enable Realtime for live chat streaming
ALTER PUBLICATION supabase_realtime ADD TABLE public.messages;

-- ── 16. voice_sessions ───────────────────────────────────────────────────────
-- 20-min AI voice call sessions (P15 / P21 mock interviews).
CREATE TABLE public.voice_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  session_type    TEXT NOT NULL CHECK (session_type IN ('career_chat', 'mock_interview')),
  status          TEXT NOT NULL DEFAULT 'scheduled'
                    CHECK (status IN ('scheduled', 'active', 'completed', 'no_show', 'cancelled')),
  scheduled_at    TIMESTAMPTZ,
  started_at      TIMESTAMPTZ,
  ended_at        TIMESTAMPTZ,
  duration_secs   INTEGER,
  transcript_url  TEXT,             -- Deepgram transcript storage path
  recording_url   TEXT,             -- audio recording (candidate consent required)
  summary         TEXT,             -- Aarya-generated session summary
  cal_booking_uid TEXT,             -- Cal.com booking UID (P07)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER voice_sessions_updated_at
  BEFORE UPDATE ON public.voice_sessions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_vs_candidate ON public.voice_sessions(candidate_id, scheduled_at DESC);

-- ── 17. notifications ────────────────────────────────────────────────────────
-- In-app + push notification queue. Also drives WhatsApp via MSG91.
CREATE TABLE public.notifications (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  type          TEXT NOT NULL,       -- 'job_match', 'intro_sent', 'intro_replied', 'interview_reminder', etc.
  title         TEXT NOT NULL,
  body          TEXT NOT NULL,
  data          JSONB DEFAULT '{}',  -- deep link payload
  channels      TEXT[] DEFAULT '{"in_app"}',  -- 'in_app' | 'whatsapp' | 'email'
  is_read       BOOLEAN NOT NULL DEFAULT FALSE,
  sent_at       TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notif_user   ON public.notifications(user_id, is_read, created_at DESC);
CREATE INDEX idx_notif_type   ON public.notifications(type, created_at DESC);

-- Enable Realtime for live notification badges
ALTER PUBLICATION supabase_realtime ADD TABLE public.notifications;

-- ── 18. job_applications ─────────────────────────────────────────────────────
-- Tracks candidate applications (direct apply via apply_url + intro path).
CREATE TABLE public.job_applications (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id  UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id        UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  intro_id      UUID REFERENCES public.intro_requests(id),  -- NULL if direct apply
  apply_type    TEXT NOT NULL CHECK (apply_type IN ('direct', 'intro', 'recruiter_referred')),
  status        TEXT NOT NULL DEFAULT 'applied'
                  CHECK (status IN ('applied','screening','interview','offer','hired','rejected','withdrawn')),
  cv_url        TEXT,                  -- tailored resume for this role (P20)
  cover_note    TEXT,
  applied_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, job_id)
);

CREATE TRIGGER job_applications_updated_at
  BEFORE UPDATE ON public.job_applications
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_app_candidate ON public.job_applications(candidate_id, applied_at DESC);
CREATE INDEX idx_app_job       ON public.job_applications(job_id, status);

-- ── 19. resumes ──────────────────────────────────────────────────────────────
-- Parsed resume versions (Affinda output, P06).
CREATE TABLE public.resumes (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  file_path       TEXT NOT NULL,        -- Supabase Storage path
  file_name       TEXT NOT NULL,
  file_size_bytes INTEGER,
  mime_type       TEXT DEFAULT 'application/pdf',
  parsed_data     JSONB DEFAULT '{}',   -- Affinda structured output
  raw_text        TEXT,                 -- plain text for embedding
  version         SMALLINT DEFAULT 1,
  is_primary      BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resumes_candidate ON public.resumes(candidate_id, created_at DESC);

-- ── 20. recruiter_searches ───────────────────────────────────────────────────
-- Nitya stores each search run here for audit and re-run.
CREATE TABLE public.recruiter_searches (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recruiter_id    UUID NOT NULL REFERENCES public.recruiters(id) ON DELETE CASCADE,
  job_id          UUID REFERENCES public.jobs(id),
  brief           TEXT,                           -- Nitya-generated hiring brief
  search_params   JSONB DEFAULT '{}',             -- structured search criteria
  candidate_ids   UUID[] DEFAULT '{}',            -- shortlisted candidate IDs
  status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','done','failed')),
  ran_at          TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER recruiter_searches_updated_at
  BEFORE UPDATE ON public.recruiter_searches
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_rs_recruiter ON public.recruiter_searches(recruiter_id, created_at DESC);
