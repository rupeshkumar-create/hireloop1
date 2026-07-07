-- A Customer Success Manager candidate had no matching pool and (before the
-- resolver fix) fell into the Engineering Manager pool via the generic token
-- "manager". Give the CS function its own canonical pool.
INSERT INTO public.career_path_definitions
  (slug, display_title, search_titles, is_senior, market)
SELECT
  'customer-success',
  'Customer Success Manager',
  ARRAY[
    'Customer Success Manager',
    'Senior Customer Success Manager',
    'Client Success Manager',
    'Customer Experience Manager',
    'Head of Customer Success'
  ],
  FALSE,
  'IN'
WHERE NOT EXISTS (
  SELECT 1 FROM public.career_path_definitions
  WHERE slug = 'customer-success' AND market = 'IN'
);
