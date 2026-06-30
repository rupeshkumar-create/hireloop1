-- Learning roadmaps: per-job, AI-generated personal learning plan rendered as a
-- self-contained interactive HTML "app". Mirrors public.tailored_resumes.

CREATE TABLE IF NOT EXISTS public.learning_roadmaps (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id    UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id          UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  summary_line    TEXT,
  status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
  error_message   TEXT,
  html_content    TEXT,
  file_path       TEXT NOT NULL DEFAULT 'pending',
  expires_at      TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '90 days'),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (candidate_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_learning_roadmaps_candidate
  ON public.learning_roadmaps(candidate_id);

-- RLS on (CLAUDE.md R: every table). The backend uses a privileged role and
-- bypasses RLS; ownership is enforced in-app via candidates.user_id joins.
ALTER TABLE public.learning_roadmaps ENABLE ROW LEVEL SECURITY;
