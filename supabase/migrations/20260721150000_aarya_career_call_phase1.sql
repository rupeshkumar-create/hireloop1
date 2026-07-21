-- Aarya trustworthy career call: durable lifecycle and typed coverage state.
--
-- Production preflight (run before applying this migration):
-- 1. Check public.voice_sessions for recording_url IS NOT NULL. Decide the
--    retention outcome explicitly before adding the no-recording constraint.
-- 2. Check for candidates with more than one active career_chat session and
--    reconcile those rows explicitly before creating the unique index.
-- This migration intentionally does not delete or reconcile existing data.

ALTER TABLE public.conversations
  ADD CONSTRAINT conversations_id_candidate_unique UNIQUE (id, candidate_id);

ALTER TABLE public.voice_sessions
  ADD COLUMN IF NOT EXISTS conversation_id UUID,
  ADD COLUMN IF NOT EXISTS consent_version TEXT,
  ADD COLUMN IF NOT EXISTS transcript_version INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS completion_reason TEXT
    CHECK (completion_reason IS NULL OR completion_reason IN (
      'candidate_ended',
      'time_limit',
      'coverage_complete',
      'interrupted',
      'cancelled'
    )),
  ADD COLUMN IF NOT EXISTS extraction_status TEXT NOT NULL DEFAULT 'not_started'
    CHECK (extraction_status IN (
      'not_started',
      'queued',
      'processing',
      'review_pending',
      'failed'
    ));

ALTER TABLE public.voice_sessions
  ADD CONSTRAINT voice_sessions_id_candidate_unique UNIQUE (id, candidate_id),
  ADD CONSTRAINT voice_sessions_conversation_candidate_fk
    FOREIGN KEY (conversation_id, candidate_id)
    REFERENCES public.conversations(id, candidate_id)
    ON DELETE SET NULL (conversation_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_sessions_active_candidate
  ON public.voice_sessions(candidate_id)
  WHERE session_type = 'career_chat' AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_voice_sessions_conversation
  ON public.voice_sessions(conversation_id)
  WHERE conversation_id IS NOT NULL;

CREATE TABLE public.career_interview_states (
  session_id UUID PRIMARY KEY,
  candidate_id UUID NOT NULL
    REFERENCES public.candidates(id) ON DELETE CASCADE,
  state JSONB NOT NULL,
  state_version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT career_interview_states_session_candidate_fk
    FOREIGN KEY (session_id, candidate_id)
    REFERENCES public.voice_sessions(id, candidate_id) ON DELETE CASCADE
);

CREATE TRIGGER career_interview_states_updated_at
  BEFORE UPDATE ON public.career_interview_states
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_career_interview_states_candidate
  ON public.career_interview_states(candidate_id, updated_at DESC);

ALTER TABLE public.career_interview_states ENABLE ROW LEVEL SECURITY;

CREATE POLICY "career_interview_states: candidate read own"
  ON public.career_interview_states FOR SELECT
  USING (
    candidate_id IN (
      SELECT id
      FROM public.candidates
      WHERE user_id = auth.uid() AND deleted_at IS NULL
    )
  );

CREATE POLICY "career_interview_states: admin read all"
  ON public.career_interview_states FOR SELECT
  USING (
    EXISTS (
      SELECT 1
      FROM public.users
      WHERE id = auth.uid()
        AND role = 'admin'
        AND deleted_at IS NULL
    )
  );

ALTER TABLE public.voice_sessions
  ADD CONSTRAINT voice_sessions_no_default_recording
  CHECK (recording_url IS NULL);
