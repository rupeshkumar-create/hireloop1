-- Shared job pools per canonical senior career path (scrape once, serve many).

CREATE TABLE IF NOT EXISTS public.career_path_definitions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT UNIQUE NOT NULL,
  display_title   TEXT NOT NULL,
  search_titles   TEXT[] NOT NULL DEFAULT '{}',
  min_years       INT,
  is_senior       BOOLEAN NOT NULL DEFAULT TRUE,
  market          TEXT NOT NULL DEFAULT 'IN',
  pool_min_jobs   INT NOT NULL DEFAULT 20,
  last_ingested_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.career_path_pool_jobs (
  career_path_definition_id UUID NOT NULL
    REFERENCES public.career_path_definitions(id) ON DELETE CASCADE,
  job_id                    UUID NOT NULL
    REFERENCES public.jobs(id) ON DELETE CASCADE,
  added_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source                    TEXT,
  PRIMARY KEY (career_path_definition_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_career_path_pool_jobs_definition
  ON public.career_path_pool_jobs (career_path_definition_id, added_at DESC);

ALTER TABLE public.career_paths
  ADD COLUMN IF NOT EXISTS career_path_definition_id UUID
    REFERENCES public.career_path_definitions(id) ON DELETE SET NULL;

-- Seed canonical senior paths (India market v1).
INSERT INTO public.career_path_definitions (slug, display_title, search_titles, is_senior, market)
VALUES
  (
    'head-of-sales',
    'Head of Sales',
    ARRAY['Head of Sales', 'VP Sales', 'Director Sales', 'Chief Revenue Officer', 'SVP Sales'],
    TRUE, 'IN'
  ),
  (
    'head-of-marketing',
    'Head of Marketing',
    ARRAY['Head of Marketing', 'VP Marketing', 'Director Marketing', 'CMO', 'Chief Marketing Officer'],
    TRUE, 'IN'
  ),
  (
    'head-of-growth',
    'Head of Growth',
    ARRAY['Head of Growth', 'VP Growth', 'Director Growth', 'Growth Lead', 'Head of GTM'],
    TRUE, 'IN'
  ),
  (
    'head-of-product',
    'Head of Product',
    ARRAY['Head of Product', 'VP Product', 'Director Product', 'Chief Product Officer'],
    TRUE, 'IN'
  ),
  (
    'engineering-manager',
    'Engineering Manager',
    ARRAY['Engineering Manager', 'Head of Engineering', 'VP Engineering', 'Director Engineering'],
    TRUE, 'IN'
  )
ON CONFLICT (slug) DO NOTHING;

COMMENT ON TABLE public.career_path_definitions IS
  'Canonical career paths with shared scraped job pools for senior roles.';
COMMENT ON TABLE public.career_path_pool_jobs IS
  'Jobs scraped once per definition; reused for candidates on the same path.';
