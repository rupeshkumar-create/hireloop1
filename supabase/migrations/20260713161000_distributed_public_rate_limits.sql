-- Shared abuse counters for public, cost-bearing endpoints across API replicas.
-- Only an HMAC digest is stored; raw visitor IP addresses never enter this table.
CREATE TABLE IF NOT EXISTS public.api_rate_limits (
  identity_hash TEXT NOT NULL,
  bucket TEXT NOT NULL,
  window_start TIMESTAMPTZ NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 1 CHECK (request_count > 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (identity_hash, bucket, window_start)
);

CREATE INDEX IF NOT EXISTS idx_api_rate_limits_expiry
  ON public.api_rate_limits (window_start);

ALTER TABLE public.api_rate_limits ENABLE ROW LEVEL SECURITY;
-- No client policy: API service connections are the only intended callers.

