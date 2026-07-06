-- Expand supported home markets beyond IN/US/GB (global audience v1).

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  meta JSONB;
  v_role TEXT;
  v_name TEXT;
  v_avatar TEXT;
  v_market TEXT;
BEGIN
  meta := COALESCE(NEW.raw_user_meta_data, '{}'::jsonb);

  v_role := COALESCE(meta->>'role', 'candidate');
  IF v_role NOT IN ('candidate', 'recruiter') THEN
    v_role := 'candidate';
  END IF;

  v_market := upper(COALESCE(meta->>'market', 'IN'));
  IF v_market NOT IN ('IN', 'US', 'GB', 'AT', 'DE', 'FR', 'AE', 'AU', 'CA', 'CH', 'NL', 'SG') THEN
    v_market := 'IN';
  END IF;

  v_name := COALESCE(
    meta->>'full_name',
    meta->>'name',
    split_part(COALESCE(NEW.email, ''), '@', 1)
  );
  v_avatar := COALESCE(meta->>'avatar_url', meta->>'picture', '');

  INSERT INTO public.users (id, email, full_name, avatar_url, role, phone_verified, market)
  VALUES (NEW.id, COALESCE(NEW.email, ''), v_name, NULLIF(v_avatar, ''), v_role, FALSE, v_market)
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), public.users.full_name),
    avatar_url = COALESCE(NULLIF(EXCLUDED.avatar_url, ''), public.users.avatar_url),
    updated_at = NOW();

  RETURN NEW;
END;
$$;
