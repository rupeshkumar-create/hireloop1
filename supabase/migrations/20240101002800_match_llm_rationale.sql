-- HIR-20: persist Aarya's LLM "why you fit" rationale on match_scores so the
-- match feed doesn't regenerate it on every load (per-card LLM call → cached).
-- llm_rationale_at lets us treat a rationale as stale once the row is re-scored
-- (computed_at newer than llm_rationale_at) and regenerate lazily.

ALTER TABLE public.match_scores
  ADD COLUMN IF NOT EXISTS llm_rationale    TEXT,
  ADD COLUMN IF NOT EXISTS llm_rationale_at TIMESTAMPTZ;

COMMENT ON COLUMN public.match_scores.llm_rationale IS
  'Cached Aarya "why you fit" one-liner (HIR-20). NULL until first generated; '
  'considered stale when computed_at > llm_rationale_at.';
