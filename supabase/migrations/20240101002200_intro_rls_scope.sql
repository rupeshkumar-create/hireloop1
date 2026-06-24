-- ============================================================
-- Migration 022 — Scope recruiter intro reads to their own rows
--   The original policy let ANY recruiter read EVERY intro_request
--   (auth.user_role() = 'recruiter'). Now that intro_requests carries a
--   recruiter_id, scope reads to the owning recruiter. This also makes
--   Realtime postgres_changes deliver only the recruiter's own intros.
--   (The FastAPI backend uses the service_role key and bypasses RLS.)
-- ============================================================

DROP POLICY IF EXISTS "intro_requests: recruiter read" ON public.intro_requests;

CREATE POLICY "intro_requests: recruiter read own"
  ON public.intro_requests FOR SELECT
  USING (
    recruiter_id IN (
      SELECT id FROM public.recruiters WHERE user_id = auth.uid()
    )
  );
