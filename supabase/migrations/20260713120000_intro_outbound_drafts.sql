-- Approve-first follow-ups + thank-you drafts on intro_requests.
ALTER TABLE public.intro_requests
  ADD COLUMN IF NOT EXISTS followup_draft_email text,
  ADD COLUMN IF NOT EXISTS followup_draft_at timestamptz,
  ADD COLUMN IF NOT EXISTS thankyou_draft_email text,
  ADD COLUMN IF NOT EXISTS thankyou_draft_at timestamptz,
  ADD COLUMN IF NOT EXISTS thankyou_sent_at timestamptz;

COMMENT ON COLUMN public.intro_requests.followup_draft_email IS
  'JSON {subject, body_html, body_text} for 72h bump — sent only after candidate approve';
COMMENT ON COLUMN public.intro_requests.nudged_at IS
  'Set when candidate-approved follow-up is sent (not when draft is created)';

-- Sweep: draft-ready candidates (not yet drafted, not yet sent).
DROP INDEX IF EXISTS idx_intro_nudge_sweep;
CREATE INDEX IF NOT EXISTS idx_intro_followup_draft_sweep
  ON public.intro_requests (sent_at)
  WHERE status = 'sent'
    AND replied_at IS NULL
    AND nudged_at IS NULL
    AND followup_draft_at IS NULL;
