-- Shared phone-OTP state — replaces the in-process dict so OTP (hash, expiry,
-- attempts, resend cooldown) is consistent across API workers and survives
-- restarts (HIR-46). Ephemeral, server-written only.

CREATE TABLE IF NOT EXISTS public.otp_verifications (
  phone        TEXT PRIMARY KEY,
  otp_hash     TEXT NOT NULL,
  expires_at   TIMESTAMPTZ NOT NULL,
  attempts     SMALLINT NOT NULL DEFAULT 0,
  last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_expires_at ON public.otp_verifications(expires_at);

-- Service-role only: enable RLS with no policies so anon/authenticated roles get
-- no access; the API (service role) bypasses RLS. OTP codes never reach clients.
ALTER TABLE public.otp_verifications ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.otp_verifications IS
  'Ephemeral phone-OTP state (hash, expiry, attempts, resend cooldown). Shared '
  'across API workers/restarts; replaces the in-process dict.';
