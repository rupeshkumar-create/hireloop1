-- Anonymous visitor chat on published candidate portfolios (/p/{slug}).

CREATE TABLE IF NOT EXISTS public.public_profile_chats (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id       UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  visitor_session_id UUID NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, visitor_session_id)
);

CREATE INDEX IF NOT EXISTS idx_public_profile_chats_candidate
  ON public.public_profile_chats (candidate_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.public_profile_chat_messages (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id    UUID NOT NULL REFERENCES public.public_profile_chats(id) ON DELETE CASCADE,
  role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content    TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_public_profile_chat_messages_chat
  ON public.public_profile_chat_messages (chat_id, created_at ASC);

ALTER TABLE public.public_profile_chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.public_profile_chat_messages ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.public_profile_chats IS
  'One thread per visitor session on a published candidate portfolio.';
COMMENT ON TABLE public.public_profile_chat_messages IS
  'Messages in anonymous portfolio chat (Aarya answers about the candidate).';
