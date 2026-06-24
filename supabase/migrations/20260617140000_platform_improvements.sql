-- Platform robustness: onboarding gate, intro draft_ready status.

ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_candidates_onboarding_complete
  ON public.candidates (user_id)
  WHERE deleted_at IS NULL AND onboarding_complete = FALSE;

-- Candidate can preview Nitya draft before Gmail send.
ALTER TABLE public.intro_requests DROP CONSTRAINT IF EXISTS intro_requests_status_check;
ALTER TABLE public.intro_requests
  ADD CONSTRAINT intro_requests_status_check CHECK (status IN (
    'pending',
    'invited',
    'enriching',
    'drafting',
    'draft_ready',
    'sent',
    'opened',
    'accepted',
    'replied',
    'declined',
    'expired',
    'cancelled'
  ));
