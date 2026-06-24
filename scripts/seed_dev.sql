-- ============================================================
-- Dev seed data — DO NOT run in production
-- Used by: local Supabase + CI test DB
-- ============================================================

-- Guard: only run in non-production environments
DO $$
BEGIN
  IF current_database() NOT LIKE '%test%' AND current_database() NOT LIKE '%dev%' AND current_database() NOT LIKE '%local%' THEN
    RAISE EXCEPTION 'seed_dev.sql must only run on dev/test databases. Current DB: %', current_database();
  END IF;
END $$;

-- ── Sample companies ──────────────────────────────────────────────────────────
INSERT INTO public.companies (id, name, domain, industry, size_bucket, hq_city, hq_state, country_code)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'Acme Fintech', 'acmefintech.in', 'Fintech', '51-200',   'Bengaluru', 'Karnataka', 'IN'),
  ('22222222-2222-2222-2222-222222222222', 'Zeta Health',  'zetahealth.in',  'Healthtech', '201-500', 'Mumbai',    'Maharashtra', 'IN'),
  ('33333333-3333-3333-3333-333333333333', 'Kite SaaS',    'kitesaas.io',    'B2B SaaS',   '11-50',  'Hyderabad', 'Telangana', 'IN')
ON CONFLICT (id) DO NOTHING;

-- ── Sample jobs ───────────────────────────────────────────────────────────────
INSERT INTO public.jobs (id, company_id, title, description, location_city, location_state, country_code, employment_type, seniority, ctc_min, ctc_max, skills_required, is_active)
VALUES
  (
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    '11111111-1111-1111-1111-111111111111',
    'Senior Backend Engineer',
    'Build scalable payment systems using Python and Postgres.',
    'Bengaluru', 'Karnataka', 'IN', 'full_time', 'senior',
    2000000, 3500000,
    ARRAY['python', 'fastapi', 'postgres', 'redis', 'aws'],
    TRUE
  ),
  (
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    '22222222-2222-2222-2222-222222222222',
    'Product Manager — Consumer',
    'Own the patient-facing mobile app roadmap.',
    'Mumbai', 'Maharashtra', 'IN', 'full_time', 'mid',
    1500000, 2500000,
    ARRAY['product management', 'mobile', 'healthtech', 'agile', 'data analytics'],
    TRUE
  ),
  (
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    '33333333-3333-3333-3333-333333333333',
    'Full Stack Engineer',
    'React + Node.js SaaS product for Indian SMBs.',
    'Hyderabad', 'Telangana', 'IN', 'full_time', 'junior',
    800000, 1400000,
    ARRAY['react', 'nodejs', 'typescript', 'postgres'],
    TRUE
  )
ON CONFLICT (id) DO NOTHING;

-- ── Sample hiring managers (unenriched) ───────────────────────────────────────
INSERT INTO public.hiring_managers (id, company_id, full_name, title, linkedin_url, enrich_status)
VALUES
  (
    'hm111111-1111-1111-1111-111111111111',
    '11111111-1111-1111-1111-111111111111',
    'Ananya Krishnan',
    'VP Engineering',
    'https://www.linkedin.com/in/ananya-krishnan-dev',
    'pending'
  ),
  (
    'hm222222-2222-2222-2222-222222222222',
    '22222222-2222-2222-2222-222222222222',
    'Rohit Sharma',
    'Head of Product',
    'https://www.linkedin.com/in/rohit-sharma-pm',
    'pending'
  )
ON CONFLICT (id) DO NOTHING;

-- ── Dev users (auth + public) ───────────────────────────────────────────────
-- Password for all test accounts: hireloop-dev-2026

INSERT INTO auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, recovery_sent_at, last_sign_in_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
  confirmation_token, email_change, email_change_token_new, recovery_token
)
VALUES
  (
    '00000000-0000-0000-0000-000000000000',
    'c0000000-0000-0000-0000-000000000001',
    'authenticated', 'authenticated',
    'candidate@test.hireloop.in',
    crypt('hireloop-dev-2026', gen_salt('bf')),
    NOW(), NOW(), NOW(),
    '{"provider":"email","providers":["email"]}', '{"full_name":"Dev Candidate"}',
    NOW(), NOW(),
    '', '', '', ''
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    'r0000000-0000-0000-0000-000000000002',
    'authenticated', 'authenticated',
    'recruiter@test.hireloop.in',
    crypt('hireloop-dev-2026', gen_salt('bf')),
    NOW(), NOW(), NOW(),
    '{"provider":"email","providers":["email"]}', '{"full_name":"Dev Recruiter"}',
    NOW(), NOW(),
    '', '', '', ''
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    'a0000000-0000-0000-0000-000000000003',
    'authenticated', 'authenticated',
    'admin@test.hireloop.in',
    crypt('hireloop-dev-2026', gen_salt('bf')),
    NOW(), NOW(), NOW(),
    '{"provider":"email","providers":["email"]}', '{"full_name":"Dev Admin"}',
    NOW(), NOW(),
    '', '', '', ''
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO auth.identities (
  id, user_id, identity_data, provider, provider_id, last_sign_in_at, created_at, updated_at
)
VALUES
  (
    'c0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    '{"sub":"c0000000-0000-0000-0000-000000000001","email":"candidate@test.hireloop.in"}',
    'email', 'c0000000-0000-0000-0000-000000000001', NOW(), NOW(), NOW()
  ),
  (
    'r0000000-0000-0000-0000-000000000002',
    'r0000000-0000-0000-0000-000000000002',
    '{"sub":"r0000000-0000-0000-0000-000000000002","email":"recruiter@test.hireloop.in"}',
    'email', 'r0000000-0000-0000-0000-000000000002', NOW(), NOW(), NOW()
  ),
  (
    'a0000000-0000-0000-0000-000000000003',
    'a0000000-0000-0000-0000-000000000003',
    '{"sub":"a0000000-0000-0000-0000-000000000003","email":"admin@test.hireloop.in"}',
    'email', 'a0000000-0000-0000-0000-000000000003', NOW(), NOW(), NOW()
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.users (id, email, phone, full_name, role, india_verified)
VALUES
  ('c0000000-0000-0000-0000-000000000001', 'candidate@test.hireloop.in', '+919876543210', 'Dev Candidate', 'candidate', TRUE),
  ('r0000000-0000-0000-0000-000000000002', 'recruiter@test.hireloop.in', '+919876543211', 'Dev Recruiter', 'recruiter', TRUE),
  ('a0000000-0000-0000-0000-000000000003', 'admin@test.hireloop.in', '+919876543212', 'Dev Admin', 'admin', TRUE)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.candidates (
  id, user_id, headline, current_title, location_city, location_state,
  years_experience, skills, profile_complete, expected_ctc_min, expected_ctc_max
)
VALUES (
  'ca000000-0000-0000-0000-000000000001',
  'c0000000-0000-0000-0000-000000000001',
  'Senior backend engineer · Python · Bengaluru',
  'Senior Software Engineer',
  'Bengaluru', 'Karnataka',
  6,
  ARRAY['python', 'fastapi', 'postgres', 'aws'],
  TRUE,
  2200000, 4000000
)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO public.recruiters (id, user_id, company_id, title)
VALUES (
  're000000-0000-0000-0000-000000000001',
  'r0000000-0000-0000-0000-000000000002',
  '11111111-1111-1111-1111-111111111111',
  'Talent Lead'
)
ON CONFLICT (user_id) DO NOTHING;

INSERT INTO public.roles (
  id, company_id, recruiter_id, title, jd_text, status, hiring_brief, candidate_pitch
)
VALUES (
  'ro000000-0000-0000-0000-000000000001',
  '11111111-1111-1111-1111-111111111111',
  're000000-0000-0000-0000-000000000001',
  'Senior Backend Engineer',
  'Python, FastAPI, Postgres — payments platform in Bengaluru.',
  'hiring',
  'Internal brief: strong Python, fintech exposure preferred.',
  'Join Acme Fintech to build India-scale payment rails.'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.match_scores (
  candidate_id, job_id, overall_score, skills_score, experience_score,
  location_score, ctc_score, explanation
)
VALUES
  (
    'ca000000-0000-0000-0000-000000000001',
    'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    0.82, 0.88, 0.75, 0.95, 0.70,
    'Strong match (82%) — Python and FastAPI align with Acme Fintech Senior Backend role.'
  ),
  (
    'ca000000-0000-0000-0000-000000000001',
    'cccccccc-cccc-cccc-cccc-cccccccccccc',
    0.71, 0.65, 0.80, 0.85, 0.90,
    'Good match (71%) — full-stack skills fit; junior band may be below your experience.'
  )
ON CONFLICT (candidate_id, job_id) DO NOTHING;
