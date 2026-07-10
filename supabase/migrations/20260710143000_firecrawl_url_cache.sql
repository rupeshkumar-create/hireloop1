-- Firecrawl URL cache — avoid re-scraping the same apply_url within TTL.
CREATE TABLE IF NOT EXISTS public.firecrawl_url_cache (
  url_hash   TEXT PRIMARY KEY,
  url        TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'jd'
             CHECK (kind IN ('jd', 'company', 'portfolio')),
  markdown   TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_firecrawl_url_cache_expires
  ON public.firecrawl_url_cache (expires_at);

ALTER TABLE public.firecrawl_url_cache ENABLE ROW LEVEL SECURITY;

-- Service-role only (API uses service key; no client reads).
CREATE POLICY "firecrawl_cache: service only"
  ON public.firecrawl_url_cache
  FOR ALL
  USING (false)
  WITH CHECK (false);

COMMENT ON TABLE public.firecrawl_url_cache IS
  'Cached Firecrawl markdown by URL hash. Written by API service role only.';
