-- Public shareable links for recruiter-uploaded roles (mirrors candidate public_slug pattern).

ALTER TABLE public.roles
  ADD COLUMN IF NOT EXISTS public_slug TEXT,
  ADD COLUMN IF NOT EXISTS public_listing_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_roles_public_slug
  ON public.roles (public_slug)
  WHERE public_slug IS NOT NULL AND deleted_at IS NULL;

COMMENT ON COLUMN public.roles.public_slug IS
  'URL slug for world-readable role page at /r/{public_slug}';
COMMENT ON COLUMN public.roles.public_listing_enabled IS
  'When TRUE and status=hiring, role is visible on the public listing page';

-- Backfill: roles already mirrored to the jobs feed get a public slug + listing flag.
UPDATE public.roles r
SET public_listing_enabled = TRUE,
    status = CASE WHEN r.status = 'draft' THEN 'hiring' ELSE r.status END,
    public_slug = COALESCE(
      r.public_slug,
      'r-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)
    )
FROM public.jobs j
WHERE j.role_id = r.id
  AND j.is_active = TRUE
  AND j.deleted_at IS NULL
  AND r.deleted_at IS NULL
  AND r.status IN ('hiring', 'draft')
  AND (r.public_slug IS NULL OR r.public_listing_enabled = FALSE);
