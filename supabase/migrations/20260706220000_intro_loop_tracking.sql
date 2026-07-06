-- Close the intro loop: Gmail thread tracking + 72h nudge bookkeeping.
-- The send response already returns id/threadId; storing them lets the
-- follow-up sweep bump the same thread and (later, scope permitting)
-- detect replies. nudged_at ensures at most one automatic follow-up.
ALTER TABLE public.intro_requests
  ADD COLUMN IF NOT EXISTS gmail_message_id text,
  ADD COLUMN IF NOT EXISTS gmail_thread_id text,
  ADD COLUMN IF NOT EXISTS gmail_subject text,
  ADD COLUMN IF NOT EXISTS nudged_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_intro_nudge_sweep
  ON public.intro_requests (sent_at)
  WHERE status = 'sent' AND replied_at IS NULL AND nudged_at IS NULL;
