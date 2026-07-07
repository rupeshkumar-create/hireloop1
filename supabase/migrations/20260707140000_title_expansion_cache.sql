-- Synonym expansions are stable per title — cache them so "Head of Growth"
-- costs one LLM call ever, not one per candidate.
CREATE TABLE IF NOT EXISTS public.title_expansions (
  title_norm text PRIMARY KEY,
  titles text[] NOT NULL,
  created_at timestamptz NOT NULL DEFAULT NOW()
);
ALTER TABLE public.title_expansions ENABLE ROW LEVEL SECURITY;
