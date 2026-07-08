-- ============================================================
-- Fix intro chat Realtime for recruiters.
--
-- public.recruiters has RLS enabled but had no SELECT policy, so joins used by
-- intro_messages / intro_requests Realtime policies never matched recruiters.
-- Without a visible recruiters row, postgres_changes INSERT events were filtered
-- out for recruiter JWTs — candidates still saw their side; recruiters did not.
-- ============================================================

CREATE POLICY "recruiters: read own"
  ON public.recruiters FOR SELECT
  USING (user_id = auth.uid() AND deleted_at IS NULL);

-- Ensure intro_requests stay in the Realtime publication so inbox lists refresh
-- when the other party sends (post_message bumps updated_at).
DO $$
BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.intro_requests;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
