-- ============================================================
-- Migration 004 — Intro handshake tables + HM enrichment
-- ============================================================

-- ── 11. hiring_managers ──────────────────────────────────────────────────────
-- HM profiles enriched by Nitya via Apify waterfall (P12).
-- HMs are NOT registered users — they're external contacts.
CREATE TABLE public.hiring_managers (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID REFERENCES public.companies(id),
  full_name       TEXT NOT NULL,
  title           TEXT,
  email           TEXT,
  email_verified  BOOLEAN DEFAULT FALSE,   -- TRUE after NeverBounce verify
  linkedin_url    TEXT UNIQUE,
  phone           TEXT,
  enrichment_data JSONB DEFAULT '{}',      -- Apify waterfall output
  enrich_status   TEXT DEFAULT 'pending'
                    CHECK (enrich_status IN ('pending','in_progress','done','failed')),
  last_enriched   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at      TIMESTAMPTZ
);

CREATE TRIGGER hm_updated_at
  BEFORE UPDATE ON public.hiring_managers
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_hm_email    ON public.hiring_managers(email) WHERE deleted_at IS NULL AND email IS NOT NULL;
CREATE INDEX idx_hm_company  ON public.hiring_managers(company_id);
CREATE INDEX idx_hm_linkedin ON public.hiring_managers(linkedin_url) WHERE linkedin_url IS NOT NULL;

-- ── 12. intro_requests ───────────────────────────────────────────────────────
-- The intro handshake table (R5). ONLY mechanism for Aarya → Nitya comms.
-- Postgres LISTEN/NOTIFY fires on INSERT to wake Nitya.
CREATE TABLE public.intro_requests (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id      UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id            UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  hiring_manager_id UUID NOT NULL REFERENCES public.hiring_managers(id),
  status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN (
                        'pending',          -- candidate clicked "Request Intro"
                        'enriching',        -- Nitya running HM enrichment
                        'drafting',         -- Nitya composing email
                        'sent',             -- email sent from candidate's Gmail
                        'opened',           -- HM opened email (tracked via pixel/webhook)
                        'replied',          -- HM replied
                        'declined',         -- HM declined or bounced
                        'cancelled'         -- candidate cancelled
                      )),
  gmail_token_id    UUID,                   -- FK to gmail_tokens (candidate's OAuth token)
  draft_email       TEXT,                   -- Nitya-drafted email body (shown to candidate before send)
  sent_at           TIMESTAMPTZ,
  opened_at         TIMESTAMPTZ,
  replied_at        TIMESTAMPTZ,
  error_message     TEXT,                   -- if status='failed'
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, job_id, hiring_manager_id)
);

CREATE TRIGGER intro_requests_updated_at
  BEFORE UPDATE ON public.intro_requests
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_intro_candidate ON public.intro_requests(candidate_id, created_at DESC);
CREATE INDEX idx_intro_status    ON public.intro_requests(status, created_at DESC);

-- NOTIFY trigger: wakes Nitya agent when a new intro is requested (R5)
CREATE OR REPLACE FUNCTION notify_intro_requested()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify(
    'intro_requests',
    json_build_object(
      'id',           NEW.id,
      'candidate_id', NEW.candidate_id,
      'job_id',       NEW.job_id,
      'hm_id',        NEW.hiring_manager_id
    )::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER intro_notify
  AFTER INSERT ON public.intro_requests
  FOR EACH ROW EXECUTE FUNCTION notify_intro_requested();

-- Enable Realtime on intro_requests so candidate UI updates live
ALTER PUBLICATION supabase_realtime ADD TABLE public.intro_requests;

-- ── 13. gmail_tokens ─────────────────────────────────────────────────────────
-- Stores candidate Gmail OAuth tokens for cold outreach (R9).
-- Encrypted at rest via Postgres column-level encryption (Phase hardening).
CREATE TABLE public.gmail_tokens (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    UUID NOT NULL UNIQUE REFERENCES public.candidates(id) ON DELETE CASCADE,
  access_token    TEXT NOT NULL,     -- encrypted
  refresh_token   TEXT NOT NULL,     -- encrypted
  token_expiry    TIMESTAMPTZ NOT NULL,
  email           TEXT NOT NULL,     -- the Gmail address (must match candidate.user.email)
  scopes          TEXT[] DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER gmail_tokens_updated_at
  BEFORE UPDATE ON public.gmail_tokens
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
