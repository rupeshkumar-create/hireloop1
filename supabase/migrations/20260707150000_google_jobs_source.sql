-- Allow google_jobs as the canonical Apify ingestion source and retire legacy values.

ALTER TABLE public.jobs DROP CONSTRAINT IF EXISTS jobs_source_check;

UPDATE public.jobs
SET source = 'google_jobs'
WHERE source IN ('apify', 'fantastic_jobs');

ALTER TABLE public.jobs
  ADD CONSTRAINT jobs_source_check
  CHECK (source IN ('google_jobs', 'ats', 'manual', 'recruiter'));
