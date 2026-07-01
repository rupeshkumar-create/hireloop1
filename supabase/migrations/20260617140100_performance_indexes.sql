-- Performance indexes for job feed and agent actions (multi-market).

CREATE INDEX IF NOT EXISTS idx_jobs_active_market
  ON public.jobs (country_code, is_active)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_match_scores_candidate_score
  ON public.match_scores (candidate_id, overall_score DESC);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
  ON public.messages (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_actions_session_created
  ON public.agent_actions (session_id, created_at DESC);

