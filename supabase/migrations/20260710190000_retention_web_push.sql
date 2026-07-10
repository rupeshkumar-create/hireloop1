-- R1/R3 retention: web push subscription stub (VAPID wired in Phase 3+)
-- Candidates can register endpoints for match alerts without email.

CREATE TABLE IF NOT EXISTS public.web_push_subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_web_push_subscriptions_user
  ON public.web_push_subscriptions (user_id);

ALTER TABLE public.web_push_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "web_push_subscriptions: read own"
  ON public.web_push_subscriptions FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "web_push_subscriptions: insert own"
  ON public.web_push_subscriptions FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "web_push_subscriptions: delete own"
  ON public.web_push_subscriptions FOR DELETE
  USING (auth.uid() = user_id);

CREATE TRIGGER web_push_subscriptions_updated_at
  BEFORE UPDATE ON public.web_push_subscriptions
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
