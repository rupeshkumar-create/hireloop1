-- ============================================================
-- Migration 020 — Two-sided intros
--   • Recruiters post jobs into the candidate-facing feed
--   • Intros become bidirectional (candidate→recruiter, recruiter→candidate)
--     in addition to the legacy candidate→external-HM path
--   • Unregistered recruiters get an email-CTA invite (recruiter_invites)
-- ============================================================

-- ── 1. Link recruiter-posted jobs into the candidate `jobs` feed ──────────────
-- A recruiter "posts a job" by publishing a row into the same jobs table the
-- candidate match feed reads from (source='recruiter'), linked back to them.
ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS recruiter_id UUID REFERENCES public.recruiters(id),
  ADD COLUMN IF NOT EXISTS role_id      UUID REFERENCES public.roles(id);

CREATE INDEX IF NOT EXISTS idx_jobs_recruiter
  ON public.jobs(recruiter_id)
  WHERE recruiter_id IS NOT NULL AND deleted_at IS NULL;

-- ── 2. recruiter_invites ──────────────────────────────────────────────────────
-- When a candidate requests an intro for a job whose recruiter is NOT registered
-- yet, we mint an invite with a one-time token and email a CTA. On signup the
-- recruiter is linked back and the pending intro is activated.
CREATE TABLE IF NOT EXISTS public.recruiter_invites (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT NOT NULL,
  token         TEXT NOT NULL UNIQUE,
  invited_name  TEXT,
  company_id    UUID REFERENCES public.companies(id),
  job_id        UUID REFERENCES public.jobs(id),
  role_id       UUID REFERENCES public.roles(id),
  candidate_id  UUID REFERENCES public.candidates(id) ON DELETE CASCADE,
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','sent','accepted','expired','cancelled')),
  recruiter_id  UUID REFERENCES public.recruiters(id),  -- set once accepted
  sent_at       TIMESTAMPTZ,
  accepted_at   TIMESTAMPTZ,
  expires_at    TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER recruiter_invites_updated_at
  BEFORE UPDATE ON public.recruiter_invites
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_recruiter_invites_email
  ON public.recruiter_invites(email) WHERE status IN ('pending','sent');
CREATE INDEX IF NOT EXISTS idx_recruiter_invites_token
  ON public.recruiter_invites(token);

-- ── 3. Make intro_requests bidirectional ──────────────────────────────────────
-- Legacy rows are candidate→external-HM (hiring_manager_id NOT NULL). We relax
-- that and add a `direction` plus recruiter/role/invite targets.
ALTER TABLE public.intro_requests
  ALTER COLUMN hiring_manager_id DROP NOT NULL;

ALTER TABLE public.intro_requests
  ADD COLUMN IF NOT EXISTS recruiter_id UUID REFERENCES public.recruiters(id),
  ADD COLUMN IF NOT EXISTS role_id      UUID REFERENCES public.roles(id),
  ADD COLUMN IF NOT EXISTS invite_id    UUID REFERENCES public.recruiter_invites(id),
  ADD COLUMN IF NOT EXISTS direction    TEXT NOT NULL DEFAULT 'candidate_to_hm'
                             CHECK (direction IN (
                               'candidate_to_hm',         -- legacy: external HM email
                               'candidate_to_recruiter',  -- candidate → registered recruiter (in-app)
                               'recruiter_to_candidate'   -- recruiter → candidate (in-app)
                             )),
  ADD COLUMN IF NOT EXISTS message      TEXT;             -- optional note from initiator

-- Extend the status vocabulary for the in-app + invite flows.
ALTER TABLE public.intro_requests DROP CONSTRAINT IF EXISTS intro_requests_status_check;
ALTER TABLE public.intro_requests
  ADD CONSTRAINT intro_requests_status_check CHECK (status IN (
    'pending',     -- requested, awaiting the other side
    'invited',     -- recruiter not registered yet → email CTA sent
    'enriching',   -- Nitya running HM enrichment (candidate_to_hm)
    'drafting',    -- Nitya composing email (candidate_to_hm)
    'sent',        -- email sent from candidate's Gmail (candidate_to_hm)
    'opened',      -- HM opened email
    'accepted',    -- recipient accepted → chat may open
    'replied',     -- HM replied
    'declined',    -- declined or bounced
    'expired',     -- invite lapsed
    'cancelled'    -- initiator cancelled
  ));

-- Every intro must point at exactly one kind of target.
ALTER TABLE public.intro_requests DROP CONSTRAINT IF EXISTS intro_requests_target_present;
ALTER TABLE public.intro_requests
  ADD CONSTRAINT intro_requests_target_present CHECK (
    hiring_manager_id IS NOT NULL
    OR recruiter_id IS NOT NULL
    OR invite_id IS NOT NULL
  );

-- Replace the rigid 3-col unique with direction-scoped partial uniques so the
-- same candidate can't double-request the same target, while still allowing
-- both directions to coexist.
ALTER TABLE public.intro_requests
  DROP CONSTRAINT IF EXISTS intro_requests_candidate_id_job_id_hiring_manager_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_intro_candidate_hm
  ON public.intro_requests(candidate_id, job_id, hiring_manager_id)
  WHERE hiring_manager_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_intro_candidate_recruiter
  ON public.intro_requests(candidate_id, job_id, recruiter_id)
  WHERE recruiter_id IS NOT NULL AND direction = 'candidate_to_recruiter';

CREATE UNIQUE INDEX IF NOT EXISTS uniq_intro_recruiter_candidate
  ON public.intro_requests(recruiter_id, candidate_id, role_id)
  WHERE direction = 'recruiter_to_candidate';

CREATE INDEX IF NOT EXISTS idx_intro_recruiter
  ON public.intro_requests(recruiter_id, status, created_at DESC)
  WHERE recruiter_id IS NOT NULL;

-- ── 4. NOTIFY trigger carries the new fields ──────────────────────────────────
CREATE OR REPLACE FUNCTION notify_intro_requested()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify(
    'intro_requests',
    json_build_object(
      'id',           NEW.id,
      'candidate_id', NEW.candidate_id,
      'job_id',       NEW.job_id,
      'hm_id',        NEW.hiring_manager_id,
      'recruiter_id', NEW.recruiter_id,
      'direction',    NEW.direction,
      'status',       NEW.status
    )::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── 5. RLS ────────────────────────────────────────────────────────────────────
-- Backend uses the service_role key (bypasses RLS). Enable RLS so the table is
-- closed by default; add a narrow read policy for the invited recruiter.
ALTER TABLE public.recruiter_invites ENABLE ROW LEVEL SECURITY;

CREATE POLICY "recruiter_invites: invitee reads own"
  ON public.recruiter_invites FOR SELECT
  USING (
    email = (SELECT email FROM public.users WHERE id = auth.uid())
    OR recruiter_id IN (
      SELECT id FROM public.recruiters WHERE user_id = auth.uid()
    )
  );

ALTER PUBLICATION supabase_realtime ADD TABLE public.recruiter_invites;
