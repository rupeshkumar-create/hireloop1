-- ============================================================
-- Migration 021 — Intro chat thread
--   Once an intro is accepted, the candidate and recruiter can message each
--   other directly. The intro_request row IS the thread; messages hang off it
--   with an explicit human sender (candidate | recruiter).
-- ============================================================

CREATE TABLE public.intro_messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  intro_request_id UUID NOT NULL REFERENCES public.intro_requests(id) ON DELETE CASCADE,
  sender_type      TEXT NOT NULL CHECK (sender_type IN ('candidate', 'recruiter')),
  sender_user_id   UUID NOT NULL REFERENCES public.users(id),
  body             TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_intro_messages_thread
  ON public.intro_messages(intro_request_id, created_at);

ALTER TABLE public.intro_messages ENABLE ROW LEVEL SECURITY;

-- Either party to the parent intro can read the thread. (Writes go through the
-- service_role backend, which bypasses RLS; this protects any direct reads.)
CREATE POLICY "intro_messages: parties read"
  ON public.intro_messages FOR SELECT
  USING (
    intro_request_id IN (
      SELECT ir.id
      FROM public.intro_requests ir
      LEFT JOIN public.candidates c  ON c.id = ir.candidate_id
      LEFT JOIN public.recruiters r  ON r.id = ir.recruiter_id
      WHERE c.user_id = auth.uid() OR r.user_id = auth.uid()
    )
  );

ALTER PUBLICATION supabase_realtime ADD TABLE public.intro_messages;
