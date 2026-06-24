-- #33: behavioral signal capture for the future learned re-ranker.
-- Events: impression (job shown on feed), save, intro_request. Saves/intros are
-- captured by triggers so no API code path can forget to log them.
CREATE TABLE public.match_feedback (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_id       UUID NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
  event        TEXT NOT NULL CHECK (event IN ('impression','save','intro_request')),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mf_candidate ON public.match_feedback(candidate_id, created_at DESC);
CREATE INDEX idx_mf_job_event ON public.match_feedback(job_id, event);
ALTER TABLE public.match_feedback ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.log_save_feedback() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO public.match_feedback (candidate_id, job_id, event)
  VALUES (NEW.candidate_id, NEW.job_id, 'save');
  RETURN NEW;
END $$;
REVOKE EXECUTE ON FUNCTION public.log_save_feedback() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.log_intro_feedback() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NEW.job_id IS NOT NULL THEN
    INSERT INTO public.match_feedback (candidate_id, job_id, event)
    VALUES (NEW.candidate_id, NEW.job_id, 'intro_request');
  END IF;
  RETURN NEW;
END $$;
REVOKE EXECUTE ON FUNCTION public.log_intro_feedback() FROM PUBLIC, anon, authenticated;

CREATE TRIGGER trg_save_feedback AFTER INSERT ON public.saved_jobs
  FOR EACH ROW EXECUTE FUNCTION public.log_save_feedback();
CREATE TRIGGER trg_intro_feedback AFTER INSERT ON public.intro_requests
  FOR EACH ROW EXECUTE FUNCTION public.log_intro_feedback();
