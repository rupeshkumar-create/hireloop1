-- Per-user Aarya chat: link conversations to auth users and mark one primary thread.

ALTER TABLE public.conversations
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES public.users(id),
  ADD COLUMN IF NOT EXISTS is_primary BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE public.conversations c
SET user_id = ca.user_id
FROM public.candidates ca
WHERE c.candidate_id = ca.id
  AND c.user_id IS NULL;

-- Mark each candidate's most recently updated Aarya thread as primary (one-time backfill).
WITH ranked AS (
  SELECT
    c.id,
    ROW_NUMBER() OVER (
      PARTITION BY c.candidate_id
      ORDER BY c.updated_at DESC NULLS LAST, c.created_at DESC
    ) AS rn
  FROM public.conversations c
  WHERE c.agent = 'aarya'
    AND c.deleted_at IS NULL
)
UPDATE public.conversations conv
SET is_primary = TRUE
FROM ranked r
WHERE conv.id = r.id
  AND r.rn = 1
  AND NOT EXISTS (
    SELECT 1
    FROM public.conversations c2
    WHERE c2.candidate_id = conv.candidate_id
      AND c2.agent = 'aarya'
      AND c2.deleted_at IS NULL
      AND c2.is_primary = TRUE
      AND c2.id <> conv.id
  );

CREATE INDEX IF NOT EXISTS idx_conversations_user_aarya
  ON public.conversations (user_id, updated_at DESC)
  WHERE deleted_at IS NULL AND agent = 'aarya';

CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_one_primary_aarya
  ON public.conversations (candidate_id)
  WHERE deleted_at IS NULL AND agent = 'aarya' AND is_primary = TRUE;

COMMENT ON COLUMN public.conversations.user_id IS
  'Auth user who owns this thread (denormalized from candidates.user_id).';
COMMENT ON COLUMN public.conversations.is_primary IS
  'Single canonical Aarya chat thread per candidate — full history lives here.';
