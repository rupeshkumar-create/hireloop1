-- P0-P2: Hybrid retrieval schema — FTS, job_sources, buckets, score versioning

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Full-text search on jobs ─────────────────────────────────────────────────
ALTER TABLE public.jobs
  ADD COLUMN IF NOT EXISTS search_tsv tsvector,
  ADD COLUMN IF NOT EXISTS role_id text,
  ADD COLUMN IF NOT EXISTS canonical_fingerprint text,
  ADD COLUMN IF NOT EXISTS job_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS enrichment_status text NOT NULL DEFAULT 'provisional',
  ADD COLUMN IF NOT EXISTS last_seen_at timestamptz,
  ADD COLUMN IF NOT EXISTS valid_through timestamptz;

-- Populate search_tsv for existing rows
UPDATE public.jobs SET search_tsv =
  setweight(to_tsvector('simple', coalesce(title, '')), 'A')
  || setweight(to_tsvector('simple', coalesce(array_to_string(skills_required, ' '), '')), 'B')
  || setweight(to_tsvector('simple', coalesce(left(description, 8000), '')), 'C')
WHERE search_tsv IS NULL;

CREATE OR REPLACE FUNCTION public.jobs_search_tsv_trigger() RETURNS trigger AS $$
BEGIN
  NEW.search_tsv :=
    setweight(to_tsvector('simple', coalesce(NEW.title, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(array_to_string(NEW.skills_required, ' '), '')), 'B')
    || setweight(to_tsvector('simple', coalesce(left(NEW.description, 8000), '')), 'C');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS jobs_search_tsv_update ON public.jobs;
CREATE TRIGGER jobs_search_tsv_update
  BEFORE INSERT OR UPDATE OF title, skills_required, description ON public.jobs
  FOR EACH ROW EXECUTE FUNCTION public.jobs_search_tsv_trigger();

CREATE INDEX IF NOT EXISTS jobs_search_tsv_gin
  ON public.jobs USING GIN (search_tsv);

CREATE INDEX IF NOT EXISTS jobs_title_trgm_gin
  ON public.jobs USING GIN (lower(title) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS jobs_role_id_idx
  ON public.jobs (role_id) WHERE deleted_at IS NULL AND is_active = TRUE;

CREATE INDEX IF NOT EXISTS jobs_canonical_fingerprint_idx
  ON public.jobs (canonical_fingerprint) WHERE canonical_fingerprint IS NOT NULL;

-- ── job_sources: multiple apply URLs per canonical job ─────────────────────
CREATE TABLE IF NOT EXISTS public.job_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  provider text NOT NULL DEFAULT 'google_jobs',
  provider_job_id text,
  source_name text,
  source_url text,
  apply_url text,
  is_direct_apply boolean NOT NULL DEFAULT false,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS job_sources_provider_job_uidx
  ON public.job_sources (provider, provider_job_id)
  WHERE provider_job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS job_sources_job_id_idx ON public.job_sources (job_id);

ALTER TABLE public.job_sources ENABLE ROW LEVEL SECURITY;

-- ── Shared inventory buckets ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.job_search_buckets (
  bucket_key text PRIMARY KEY,
  role_id text NOT NULL,
  market text NOT NULL,
  location_norm text NOT NULL DEFAULT 'any',
  language text NOT NULL DEFAULT 'en',
  active_job_count integer NOT NULL DEFAULT 0,
  last_success_at timestamptz,
  last_run_at timestamptz,
  query_plan_version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS job_search_buckets_role_market_idx
  ON public.job_search_buckets (role_id, market);

ALTER TABLE public.job_search_buckets ENABLE ROW LEVEL SECURITY;

-- ── Score versioning on match_scores ─────────────────────────────────────────
ALTER TABLE public.match_scores
  ADD COLUMN IF NOT EXISTS candidate_intent_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS job_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS retrieval_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS ranking_model_version text NOT NULL DEFAULT 'v2_feature_rerank',
  ADD COLUMN IF NOT EXISTS retrieval_score real,
  ADD COLUMN IF NOT EXISTS occupation_score real,
  ADD COLUMN IF NOT EXISTS title_score real,
  ADD COLUMN IF NOT EXISTS required_skill_score real,
  ADD COLUMN IF NOT EXISTS responsibility_score real,
  ADD COLUMN IF NOT EXISTS seniority_score real,
  ADD COLUMN IF NOT EXISTS industry_score real,
  ADD COLUMN IF NOT EXISTS freshness_score real,
  ADD COLUMN IF NOT EXISTS source_quality_score real,
  ADD COLUMN IF NOT EXISTS score_confidence real,
  ADD COLUMN IF NOT EXISTS retrieval_sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS explanation_json jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Candidate profile versioning
ALTER TABLE public.candidates
  ADD COLUMN IF NOT EXISTS profile_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS intent_version integer NOT NULL DEFAULT 1;

-- Candidate behavior events (extend impressions)
ALTER TABLE public.candidate_job_impressions
  ADD COLUMN IF NOT EXISTS event_type text NOT NULL DEFAULT 'impression';

CREATE INDEX IF NOT EXISTS candidate_job_impressions_event_idx
  ON public.candidate_job_impressions (candidate_id, job_id, event_type);

COMMENT ON COLUMN public.jobs.role_id IS 'Canonical occupation family from occupation_taxonomy';
COMMENT ON COLUMN public.jobs.canonical_fingerprint IS 'Cross-source dedup hash';
COMMENT ON COLUMN public.match_scores.ranking_model_version IS 'Reranker version for invalidation';
