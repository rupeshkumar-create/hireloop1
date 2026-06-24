-- ============================================================
-- Migration 008 — Supabase Storage buckets
-- All buckets are PRIVATE (signed URLs only, 1h expiry).
-- ============================================================

-- ── Resumes bucket ────────────────────────────────────────────────────────────
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'resumes',
  'resumes',
  FALSE,                          -- private
  10485760,                       -- 10MB max
  ARRAY['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
) ON CONFLICT (id) DO NOTHING;

-- ── Profile photos bucket ─────────────────────────────────────────────────────
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'avatars',
  'avatars',
  FALSE,                          -- private
  2097152,                        -- 2MB max
  ARRAY['image/jpeg', 'image/png', 'image/webp']
) ON CONFLICT (id) DO NOTHING;

-- ── Tailored resume PDFs (generated, P20) ────────────────────────────────────
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'tailored-resumes',
  'tailored-resumes',
  FALSE,
  10485760,
  ARRAY['application/pdf']
) ON CONFLICT (id) DO NOTHING;

-- ── RLS policies for storage ─────────────────────────────────────────────────

-- Resumes: candidates can read/write their own
CREATE POLICY "resumes: candidate upload"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'resumes'
    AND auth.uid() IS NOT NULL
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "resumes: candidate read own"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'resumes'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Service role reads all (API needs to access resumes for parsing)
CREATE POLICY "resumes: service read all"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'resumes' AND auth.role() = 'service_role');

-- Avatars: candidates can read/write their own
CREATE POLICY "avatars: upload own"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "avatars: read own"
  ON storage.objects FOR SELECT
  USING (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );
