-- Recruiter package layers: inbound applicants, role intel cache, pipeline notes support

CREATE TABLE public.role_inbound_applicants (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  role_id           UUID NOT NULL REFERENCES public.roles(id) ON DELETE CASCADE,
  source            TEXT NOT NULL DEFAULT 'public_apply'
                      CHECK (source IN ('public_apply', 'recruiter_add', 'linkedin_url')),
  full_name         TEXT NOT NULL,
  email             TEXT,
  linkedin_url      TEXT,
  resume_path       TEXT,
  parsed_profile    JSONB NOT NULL DEFAULT '{}',
  match_score       REAL,
  criterion_scores  JSONB NOT NULL DEFAULT '{}',
  skills_matched    TEXT[] DEFAULT '{}',
  skills_gap        TEXT[] DEFAULT '{}',
  stage             TEXT NOT NULL DEFAULT 'search'
                      CHECK (stage IN (
                        'search', 'shortlisted', 'intro_requested',
                        'intro_made', 'interview', 'offer', 'hired', 'archived'
                      )),
  notes             TEXT,
  moved_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER role_inbound_applicants_updated_at
  BEFORE UPDATE ON public.role_inbound_applicants
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX idx_inbound_applicants_role ON public.role_inbound_applicants(role_id, stage);
CREATE UNIQUE INDEX idx_inbound_applicants_role_email
  ON public.role_inbound_applicants(role_id, lower(email))
  WHERE email IS NOT NULL AND email <> '';

ALTER TABLE public.roles
  ADD COLUMN IF NOT EXISTS jd_bias_report JSONB DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS interview_kit JSONB DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS market_intel_cache JSONB DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS market_intel_cached_at TIMESTAMPTZ;

-- RLS: recruiters manage inbound applicants for their roles
ALTER TABLE public.role_inbound_applicants ENABLE ROW LEVEL SECURITY;

CREATE POLICY "inbound_applicants: recruiter read own roles"
  ON public.role_inbound_applicants FOR SELECT
  USING (
    role_id IN (
      SELECT r.id FROM public.roles r
      JOIN public.recruiters rec ON rec.id = r.recruiter_id
      WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
    )
  );

CREATE POLICY "inbound_applicants: recruiter write own roles"
  ON public.role_inbound_applicants FOR ALL
  USING (
    role_id IN (
      SELECT r.id FROM public.roles r
      JOIN public.recruiters rec ON rec.id = r.recruiter_id
      WHERE rec.user_id = auth.uid() AND r.deleted_at IS NULL
    )
  );

CREATE POLICY "inbound_applicants: admin read all"
  ON public.role_inbound_applicants FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.users u
      WHERE u.id = auth.uid() AND u.role = 'admin' AND u.deleted_at IS NULL
    )
  );

-- Public apply: allow anonymous insert via service role only (API uses service pool)
